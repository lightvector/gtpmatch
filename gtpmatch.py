"""
Lightweight Python module for running games between two Go bots using GTP.

This module provides a simple interface to launch GTP-compatible Go bots,
have them play games against each other, and save the results to SGF files.
"""

import logging
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

# Constants
BOT_QUIT_TIMEOUT = 5  # seconds
BOT_TERMINATE_TIMEOUT = 5  # seconds

try:
    import sgfmill.sgf
    import sgfmill.sgf_moves
except ImportError:
    sgfmill = None

# GTP coordinate system: letters A-Z (skipping I), then AA, AB, AC, etc.
GTP_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def gtp_vertex_to_sgf_point(
    vertex: str,
    board_size: int,
) -> tuple[int, int] | None:
    """
    Convert GTP vertex format to SGF point format.

    Args:
        vertex: GTP vertex like "D4", "AA10", or "pass"
        board_size: Size of the board

    Returns:
        SGF point as (row, col) tuple, or None for pass

    Raises:
        ValueError: If vertex format is invalid or outside board bounds
    """
    if vertex.lower() == "pass":
        return None

    vertex = vertex.upper().strip()
    if not vertex:
        raise ValueError("Empty vertex string")

    # Split into letters and numbers more efficiently
    alpha_part = ""
    numeric_start = 0
    for i, char in enumerate(vertex):
        if char.isalpha():
            alpha_part += char
            numeric_start = i + 1
        else:
            break

    if not alpha_part or numeric_start >= len(vertex):
        raise ValueError(f"Invalid GTP vertex format: {vertex}")

    # Parse row number
    try:
        row_num = int(vertex[numeric_start:])
        if row_num < 1:
            raise ValueError(f"Row number must be positive: {row_num}")
    except ValueError as e:
        raise ValueError(f"Invalid row number in vertex {vertex}: {e}")

    # Convert column letters to column index
    col = _parse_gtp_columns(alpha_part)

    # Convert to SGF coordinates (0-based, row 0 is top, unlike GTP where 1 is the bottom)
    # Unfortunately, sgfmill's coordnates are ALSO flipped, so if we're using sgfmill for serialization,
    # then 0 is the bottom. So we don't invert here, we just convert to zero-indexed.
    sgf_row = row_num - 1
    sgf_col = col

    if sgf_row < 0 or sgf_row >= board_size or sgf_col >= board_size:
        raise ValueError(f"GTP vertex {vertex} is outside {board_size}x{board_size} board bounds")

    return (sgf_row, sgf_col)


def _parse_gtp_columns(col_letters: str) -> int:
    """Parse GTP column letters (A-Z, AA-ZZ, etc.) to column index."""
    if len(col_letters) == 1:
        col = GTP_LETTERS.find(col_letters)
        if col == -1:
            raise ValueError(f"Invalid GTP column letter: {col_letters}")
        return col
    elif len(col_letters) == 2:
        # AA, AB, AC, etc.
        first_letter = GTP_LETTERS.find(col_letters[0])
        second_letter = GTP_LETTERS.find(col_letters[1])
        if first_letter == -1 or second_letter == -1:
            raise ValueError(f"Invalid GTP column letters: {col_letters}")
        return len(GTP_LETTERS) + first_letter * len(GTP_LETTERS) + second_letter
    else:
        raise ValueError(f"GTP column format not supported (max 2 letters): {col_letters}")


def sgf_point_to_gtp_vertex(
    point: tuple[int, int] | None,
    board_size: int,
) -> str:
    """
    Convert SGF point format to GTP vertex format.

    Args:
        point: SGF point as (row, col) tuple, or None for pass
        board_size: Size of the board

    Returns:
        GTP vertex like "D4", "AA10", or "pass"

    Raises:
        ValueError: If point is outside board bounds
    """
    if point is None:
        return "pass"

    sgf_row, sgf_col = point

    # Validate coordinates
    if not (0 <= sgf_row < board_size and 0 <= sgf_col < board_size):
        raise ValueError(f"SGF point {point} is outside {board_size}x{board_size} board bounds")

    # Convert to GTP coordinates
    # See gtp_vertex_to_sgf_point comment about sgf_row. Avoid flip here similarly.
    gtp_row = sgf_row + 1
    col_letters = _format_gtp_columns(sgf_col)

    return f"{col_letters}{gtp_row}"


def _format_gtp_columns(col_index: int) -> str:
    """Convert column index to GTP column letters."""
    if col_index < len(GTP_LETTERS):
        return GTP_LETTERS[col_index]
    else:
        # AA, AB, AC, etc.
        remaining = col_index - len(GTP_LETTERS)
        first_letter = remaining // len(GTP_LETTERS)
        second_letter = remaining % len(GTP_LETTERS)
        if first_letter >= len(GTP_LETTERS):
            raise ValueError(f"Column index {col_index} too large for supported GTP format")
        return GTP_LETTERS[first_letter] + GTP_LETTERS[second_letter]


class Color(Enum):
    """Go stone colors."""
    BLACK = "black"
    WHITE = "white"

    def opposite(self) -> 'Color':
        """Return the opposite color."""
        return Color.WHITE if self == Color.BLACK else Color.BLACK


class GameResult(Enum):
    """Possible game results."""
    BLACK_WIN = "B"
    WHITE_WIN = "W"
    DRAW = "draw"
    UNKNOWN = "unknown"
    ILLEGAL_MOVE = "illegal"
    UNFINISHED = "unfinished"


class GTPError(Exception):
    """Exception raised when a GTP command fails."""
    pass


class Bot:
    """A running Go bot that communicates via GTP."""
    def __init__(
        self,
        name: str,
        process: subprocess.Popen,
    ):
        self.name = name
        self._process = process

    def send_command(
        self,
        command: str,
        raise_on_failure: bool = True,
    ) -> str:
        """
        Send a GTP command to the bot and return the response.

        Args:
            command: The GTP command to send
            raise_on_failure: Whether to raise GTPError on command failure

        Returns:
            The response from the bot

        Raises:
            GTPError: If the command fails and raise_on_failure is True
        """
        if self._process.poll() is not None:
            raise GTPError(f"Bot {self.name} process has terminated")

        cmd_line = f"{command}\n"
        self._process.stdin.write(cmd_line.encode('utf-8'))
        self._process.stdin.flush()
        response_lines = []
        while True:
            line = self._process.stdout.readline().decode('utf-8').rstrip('\r\n')
            if line == "":
                break
            if line.startswith('=') or line.startswith('?'):
                # This is the status line
                status = line[0]
                content = line[1:].strip()
                if content:
                    response_lines.append(content)
                break
            response_lines.append(line)

        # Continue reading until blank line
        while True:
            line = self._process.stdout.readline().decode('utf-8').rstrip('\r\n')
            if line == "":
                break
            response_lines.append(line)

        response = '\n'.join(response_lines)

        if status == '?' and raise_on_failure:
            raise GTPError(f"Command '{command}' failed: {response}")

        return response

    def terminate(self):
        """Terminate the bot process."""
        if self._process.poll() is None:
            try:
                self.send_command("quit", raise_on_failure=False)
                self._process.wait(timeout=BOT_QUIT_TIMEOUT)
            except (GTPError, subprocess.TimeoutExpired):
                self._process.terminate()
                try:
                    self._process.wait(timeout=BOT_TERMINATE_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self._process.kill()


@contextmanager
def launch_bot(
    name: str,
    command: str | list[str],
) -> Iterator[Bot]:
    """
    Launch a GTP bot as a context manager.

    Args:
        name: Human-readable name/label for the bot
        command: Command line to launch the bot (string or list of args)

    Yields:
        A Bot object for communicating with the launched bot

    The bot process will be terminated when exiting the context.
    """
    if isinstance(command, str):
        cmd_args = command.split()
    else:
        cmd_args = command

    process = subprocess.Popen(
        cmd_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,  # We handle encoding ourselves
        bufsize=0
    )

    bot = Bot(name, process)

    try:
        # Verify the bot is responsive
        bot.send_command("protocol_version")
        yield bot
    finally:
        bot.terminate()


@dataclass
class Move:
    """A move in a Go game."""
    color: Color
    vertex: str  # GTP vertex format like "D4" or "pass"


@dataclass
class FinishedGame:
    """A completed Go game with its history and result."""

    black_bot_name: str
    white_bot_name: str
    board_size: int
    komi: float
    moves: list[Move]
    result: GameResult
    winner_name: str | None
    score: str | None = None  # e.g., "B+3.5", "W+R", "B+", etc.

    def _create_sgf_game(self) -> 'sgfmill.sgf.Sgf_game':
        """Create and populate an SGF game object."""
        if sgfmill is None:
            raise ImportError("sgfmill library is required to generate SGF")

        game = sgfmill.sgf.Sgf_game(size=self.board_size)

        # Set game properties
        root = game.get_root()
        root.set("PB", self.black_bot_name)
        root.set("PW", self.white_bot_name)
        root.set("KM", str(self.komi))
        root.set("SZ", self.board_size)

        # Set result
        if self.score:
            root.set("RE", self.score)
        elif self.result == GameResult.BLACK_WIN:
            root.set("RE", "B+")
        elif self.result == GameResult.WHITE_WIN:
            root.set("RE", "W+")
        elif self.result == GameResult.DRAW:
            root.set("RE", "0")
        elif self.result in (GameResult.ILLEGAL_MOVE, GameResult.UNKNOWN):
            root.set("RE", "?")
        # For UNFINISHED games, don't set RE tag at all

        # Add moves
        for move in self.moves:
            try:
                point = gtp_vertex_to_sgf_point(move.vertex, self.board_size)
            except ValueError:
                continue  # Skip invalid moves

            color_char = move.color.value[0].lower()
            game.extend_main_sequence()
            node = game.get_last_node()
            node.set_move(color_char, point)

        return game

    def save_sgf(
        self,
        filepath: str | Path,
    ) -> None:
        """
        Save the game to an SGF file.

        Args:
            filepath: Path where to save the SGF file
        """
        game = self._create_sgf_game()
        with open(filepath, 'wb') as f:
            f.write(game.serialise())

    def get_sgf(self) -> str:
        """
        Get the game as an SGF string.

        Returns:
            The SGF representation as a string
        """
        game = self._create_sgf_game()
        return game.serialise().decode('utf-8')

    def winner(self) -> str | None:
        """Return the name of the winning bot, or None if draw/unknown."""
        return self.winner_name

    def final_score(self) -> str | None:
        """Return the final score string if available, e.g. 'B+3.5', 'W+R'."""
        return self.score


def _parse_score_result(score_str: str) -> tuple[GameResult, str | None, str | None]:
    """
    Parse a score string and return result, winner name placeholder, and cleaned score.

    Args:
        score_str: Score string like "B+3.5", "W+R", "0", etc.

    Returns:
        Tuple of (GameResult, winner_placeholder, cleaned_score)
        winner_placeholder is "black" or "white" or None
    """
    score = score_str.upper()
    if score.startswith('B+'):
        return GameResult.BLACK_WIN, "black", score
    elif score.startswith('W+'):
        return GameResult.WHITE_WIN, "white", score
    elif score == "0":
        return GameResult.DRAW, None, score
    else:
        return GameResult.UNKNOWN, None, "?"


def _resolve_score_disagreement(black_score: str, white_score: str) -> tuple[GameResult, str | None, str]:
    """
    Resolve disagreement between bot scores.

    Args:
        black_score: Score reported by black bot
        white_score: Score reported by white bot

    Returns:
        Tuple of (GameResult, winner_placeholder, final_score)
    """
    black_result, black_winner, _ = _parse_score_result(black_score)
    white_result, white_winner, _ = _parse_score_result(white_score)

    if black_winner == white_winner:
        # Same winner, different scores
        logging.warning(f"Bots disagree on score: black bot says {black_score}, white bot says {white_score}")
        if black_winner == "black":
            return GameResult.BLACK_WIN, "black", "B+"
        elif black_winner == "white":
            return GameResult.WHITE_WIN, "white", "W+"
        else:  # Draw
            return GameResult.DRAW, None, "0"
    else:
        # Different winners
        logging.warning(f"Bots disagree on winner: black bot says {black_score}, white bot says {white_score}")
        return GameResult.UNKNOWN, None, "?"


def _validate_game_parameters(
    board_size: int,
    komi: float,
    max_moves: int | None,
) -> None:
    """Validate game parameters and raise ValueError if invalid."""
    if not isinstance(board_size, int) or board_size < 1 or board_size > 99:
        raise ValueError(f"board_size must be an integer between 1 and 99, got {board_size}")

    if not isinstance(komi, (int, float)) or komi < -100 or komi > 100:
        raise ValueError(f"komi must be a number between -100 and 100, got {komi}")

    if max_moves is not None and (not isinstance(max_moves, int) or max_moves < 1):
        raise ValueError(f"max_moves must be a positive integer or None, got {max_moves}")


def _setup_bots(
    black_bot: Bot,
    white_bot: Bot,
    board_size: int,
    komi: float,
) -> None:
    """Set up both bots for the game."""
    for bot in [black_bot, white_bot]:
        bot.send_command("clear_board")
        bot.send_command(f"boardsize {board_size}")
        bot.send_command(f"komi {komi}")


def _get_bot_score(
    bot: Bot,
    bot_name: str,
) -> str | None:
    """
    Get final score from a bot if it supports scoring.

    Returns:
        Score string or None if bot doesn't support scoring or returns unknown
    """
    try:
        commands = bot.send_command("list_commands", raise_on_failure=False)
        if "final_score" in commands.lower():
            score_response = bot.send_command("final_score", raise_on_failure=False)
            if score_response and score_response.strip().lower() != "unknown":
                return score_response.strip()
    except Exception as e:
        logging.debug(f"Failed to get score from {bot_name}: {e}")
    return None


def _determine_final_result(
    black_bot: Bot,
    white_bot: Bot,
) -> tuple[GameResult, str | None, str | None]:
    """
    Determine final game result by asking both bots for scores.

    Returns:
        Tuple of (GameResult, winner_name, score_string)
    """
    black_score = _get_bot_score(black_bot, black_bot.name)
    white_score = _get_bot_score(white_bot, white_bot.name)

    if black_score and white_score:
        black_score = black_score.upper()
        white_score = white_score.upper()

        if black_score == white_score:
            # Both bots agree
            result, winner_placeholder, score = _parse_score_result(black_score)
            winner_name = black_bot.name if winner_placeholder == "black" else (
                white_bot.name if winner_placeholder == "white" else None
            )
            return result, winner_name, score
        else:
            # Bots disagree
            result, winner_placeholder, score = _resolve_score_disagreement(black_score, white_score)
            winner_name = black_bot.name if winner_placeholder == "black" else (
                white_bot.name if winner_placeholder == "white" else None
            )
            return result, winner_name, score

    elif black_score:
        # Only black bot provided a score
        result, winner_placeholder, score = _parse_score_result(black_score.upper())
        winner_name = black_bot.name if winner_placeholder == "black" else (
            white_bot.name if winner_placeholder == "white" else None
        )
        return result, winner_name, score

    elif white_score:
        # Only white bot provided a score
        result, winner_placeholder, score = _parse_score_result(white_score.upper())
        winner_name = black_bot.name if winner_placeholder == "black" else (
            white_bot.name if winner_placeholder == "white" else None
        )
        return result, winner_name, score

    # No scores available
    return GameResult.UNKNOWN, None, None


def play_game(
    black_bot: Bot,
    white_bot: Bot,
    board_size: int = 19,
    komi: float = 6.5,
    max_moves: int | None = None,
) -> FinishedGame:
    """
    Play a game between two bots.

    Args:
        black_bot: Bot playing black stones
        white_bot: Bot playing white stones
        board_size: Size of the Go board (default 19)
        komi: Komi value for white (default 6.5)
        max_moves: Maximum number of moves (default: board_size^2 * 5)

    Returns:
        A FinishedGame object with the game result
    """
    _validate_game_parameters(board_size, komi, max_moves)

    if max_moves is None:
        max_moves = board_size * board_size * 5

    _setup_bots(black_bot, white_bot, board_size, komi)

    moves: list[Move] = []
    current_color = Color.BLACK
    consecutive_passes = 0

    while consecutive_passes < 2 and len(moves) < max_moves:
        if current_color == Color.BLACK:
            current_bot = black_bot
            other_bot = white_bot
        else:
            current_bot = white_bot
            other_bot = black_bot

        try:
            response = current_bot.send_command(f"genmove {current_color.value}")
            vertex = response.strip()

            if not vertex:
                vertex = "pass"
            elif vertex.lower() == "resign":
                # Handle resignation
                opposite_color = current_color.opposite()
                result = GameResult.WHITE_WIN if opposite_color == Color.WHITE else GameResult.BLACK_WIN
                winner_name = white_bot.name if opposite_color == Color.WHITE else black_bot.name
                score = f"{opposite_color.value[0].upper()}+R"
                return FinishedGame(
                    black_bot_name=black_bot.name,
                    white_bot_name=white_bot.name,
                    board_size=board_size,
                    komi=komi,
                    moves=moves,
                    result=result,
                    winner_name=winner_name,
                    score=score
                )

        except GTPError as e:
            # Bot failed to generate move, end game as unfinished
            logging.warning(f"Bot {current_bot.name} failed to generate move: {e}")
            return FinishedGame(
                black_bot_name=black_bot.name,
                white_bot_name=white_bot.name,
                board_size=board_size,
                komi=komi,
                moves=moves,
                result=GameResult.UNFINISHED,
                winner_name=None
            )

        move = Move(current_color, vertex)
        moves.append(move)

        if vertex.lower() == "pass":
            consecutive_passes += 1
        else:
            consecutive_passes = 0

        if vertex.lower() != "pass":
            try:
                other_bot.send_command(f"play {current_color.value} {vertex}")
            except GTPError as e:
                # Other bot rejected the move, treat as illegal move claim
                logging.warning(f"Bot {other_bot.name} rejected move {vertex} by {current_bot.name}: {e}")
                result = GameResult.ILLEGAL_MOVE
                winner_name = None
                return FinishedGame(
                    black_bot_name=black_bot.name,
                    white_bot_name=white_bot.name,
                    board_size=board_size,
                    komi=komi,
                    moves=moves,
                    result=result,
                    winner_name=winner_name
                )

        current_color = current_color.opposite()

    # Check if game ended due to move limit
    if len(moves) >= max_moves:
        return FinishedGame(
            black_bot_name=black_bot.name,
            white_bot_name=white_bot.name,
            board_size=board_size,
            komi=komi,
            moves=moves,
            result=GameResult.UNFINISHED,
            winner_name=None
        )

    # Game ended normally, get scores from both bots
    result, winner_name, score = _determine_final_result(black_bot, white_bot)

    return FinishedGame(
        black_bot_name=black_bot.name,
        white_bot_name=white_bot.name,
        board_size=board_size,
        komi=komi,
        moves=moves,
        result=result,
        winner_name=winner_name,
        score=score
    )
