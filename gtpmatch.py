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

import sgfmill.sgf
import sgfmill.sgf_moves

# GTP coordinate system: letters A-Z (skipping I), then AA, AB, AC, etc.
GTP_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def gtp_vertex_to_sgfmill_point(
    vertex: str,
    board_size: int,
) -> tuple[int, int] | None:
    """
    Convert GTP vertex format to sgfmill point format.

    Args:
        vertex: GTP vertex like "D4", "AA10", or "pass"
        board_size: Size of the board

    Returns:
        sgfmill point as (row, col) tuple, or None for pass

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

    # Convert to sgfmill coordinates (0-based, row 0 is BOTTOM, unlike GTP where 1 is the bottom)
    # Yes, sgfmill's coordinates are vertically flippped compared to sgf file format where e.g. "aa" is the TOP.
    # So we don't invert here, we just convert to zero-indexed.
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
    point: str,
    board_size: int,
) -> str:
    """
    Convert SGF point format to GTP vertex format.

    Args:
        point: SGF point as sgf raw str e.g. "qr", "ac", etc.
        board_size: Size of the board

    Returns:
        GTP vertex like "D4", "AA10", or "pass"

    Raises:
        ValueError: If point is outside board bounds
    """
    if point == "" or point == "tt":
        return "pass"

    col = ord(point[0]) - ord('a')
    row = ord(point[1]) - ord('a')
    move_coord = (row, col)

    if not (0 <= row < board_size and 0 <= col < board_size):
        raise ValueError(f"SGF point {point} is outside {board_size}x{board_size} board bounds")

    gtp_row = board_size-row
    col_letters = _format_gtp_columns(col)

    return f"{col_letters}{gtp_row}"

def sgfmill_point_to_gtp_vertex(
    point: tuple[int, int] | None,
    board_size: int,
) -> str:
    """
    Convert sgfmill point format to GTP vertex format.

    Args:
        point: sgfmill point as (row, col) tuple, or None for pass
        board_size: Size of the board

    Returns:
        GTP vertex like "D4", "AA10", or "pass"

    Raises:
        ValueError: If point is outside board bounds
    """
    if point is None:
        return "pass"

    sgf_row, sgf_col = point

    if not (0 <= sgf_row < board_size and 0 <= sgf_col < board_size):
        raise ValueError(f"sgfmill point {point} is outside {board_size}x{board_size} board bounds")

    # Convert to GTP coordinates
    # See gtp_vertex_to_sgfmill_point comment about sgf_row. Avoid flip here similarly.
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
        status = None
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

        if (status is None or status == '?') and raise_on_failure:
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
    setup_moves: list[Move] = None  # Handicap or starting position moves

    def _create_sgf_game(self) -> 'sgfmill.sgf.Sgf_game':
        """Create and populate an SGF game object."""
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

        # Add setup stones to root node if any
        if self.setup_moves:
            black_points = []
            white_points = []
            for move in self.setup_moves:
                if not _is_valid_move(move.vertex, self.board_size):
                    raise ValueError(f"Invalid setup move in SGF export: {move.vertex}")
                if move.vertex.lower() in ("pass", "resign"):
                    raise ValueError(f"Setup moves cannot be pass or resign: {move.vertex}")

                point = gtp_vertex_to_sgfmill_point(move.vertex, self.board_size)
                if point is not None:
                    if move.color == Color.BLACK:
                        black_points.append(point)
                    else:
                        white_points.append(point)

            if black_points or white_points:
                root.set_setup_stones(black_points, white_points, [])

        # Add regular moves
        for move in self.moves:
            # Since we validate moves during play_game, all moves should be valid
            if not _is_valid_move(move.vertex, self.board_size):
                raise ValueError(f"Invalid move found in game record during SGF export: {move.vertex}")

            if move.vertex.lower() == "resign":
                # Resignation is handled in game result, not as a move
                continue

            point = gtp_vertex_to_sgfmill_point(move.vertex, self.board_size)
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
        else:
            return GameResult.DRAW, None, "0"
    else:
        # Different winners
        logging.warning(f"Bots disagree on winner: black bot says {black_score}, white bot says {white_score}")
        return GameResult.UNKNOWN, None, "?"


def _is_valid_move(vertex: str, board_size: int) -> bool:
    """
    Check if a move vertex is valid.

    Args:
        vertex: GTP vertex format like "D4", "pass", or "resign"
        board_size: Size of the board

    Returns:
        True if the move is valid (can be converted to SGF or is pass/resign)
    """
    vertex_lower = vertex.lower()
    if vertex_lower in ("pass", "resign"):
        return True

    try:
        gtp_vertex_to_sgfmill_point(vertex, board_size)
        return True
    except ValueError:
        return False


def _get_fixed_handicap_positions(
    handicap: int,
    board_size: int,
) -> list[tuple[int, int]]:
    """
    Get fixed handicap stone positions for a given handicap and board size.

    Args:
        handicap: Number of handicap stones (2-9)
        board_size: Size of the board

    Returns:
        List of (row, col) positions in SGF coordinates

    Raises:
        ValueError: If handicap is invalid for the board size
    """
    if handicap < 2 or handicap > 9:
        raise ValueError(f"Handicap must be between 2 and 9, got {handicap}")

    if board_size < 7:
        raise ValueError(f"No handicap supported for boards smaller than 7x7")

    if board_size == 7 and handicap > 4:
        raise ValueError(f"Maximum 4 handicap stones for 7x7 board")

    if board_size % 2 == 0 and handicap > 4:
        raise ValueError(f"Maximum 4 handicap stones for even-sized boards")

    # Calculate edge distance: 4th line for boards >= 13, 3rd line for smaller
    edge_dist = 2 if board_size < 13 else 3

    # Corner positions
    positions = [
        (edge_dist, edge_dist),  # D4 equivalent
        (board_size - 1 - edge_dist, board_size - 1 - edge_dist),  # Q16 equivalent
    ]

    if handicap >= 3:
        positions.append((edge_dist, board_size - 1 - edge_dist))  # D16 equivalent

    if handicap >= 4:
        positions.append((board_size - 1 - edge_dist, edge_dist))  # Q4 equivalent

    if handicap >= 5:
        # Center position (only for odd-sized boards)
        if board_size % 2 == 1:
            center = board_size // 2
            positions.append((center, center))  # K10 equivalent
        else:
            raise ValueError(f"Cannot place center stone on even-sized board")

    if handicap >= 6:
        # Side positions
        center = board_size // 2
        positions.extend(
            [
                (edge_dist, center),  # D10 equivalent
                (board_size - 1 - edge_dist, center),  # Q10 equivalent
            ]
        )

    if handicap >= 7:
        # Already have center from handicap 5
        pass

    if handicap >= 8:
        # More side positions
        center = board_size // 2
        positions.extend(
            [
                (center, edge_dist),  # K4 equivalent
                (center, board_size - 1 - edge_dist),  # K16 equivalent
            ]
        )

    if handicap >= 9:
        # Center stone already added for handicap 5
        pass

    return positions[:handicap]


def _validate_game_parameters(
    board_size: int,
    komi: float,
    max_moves: int | None,
    handicap_or_startpos: int | list[Move] | None,
) -> None:
    """Validate game parameters and raise ValueError if invalid."""
    if not isinstance(board_size, int) or board_size < 1 or board_size > 99:
        raise ValueError(f"board_size must be an integer between 1 and 99, got {board_size}")

    if not isinstance(komi, (int, float)) or komi < -100 or komi > 100:
        raise ValueError(f"komi must be a number between -100 and 100, got {komi}")

    if max_moves is not None and (not isinstance(max_moves, int) or max_moves < 1):
        raise ValueError(f"max_moves must be a positive integer or None, got {max_moves}")

    if handicap_or_startpos is not None:
        if isinstance(handicap_or_startpos, int):
            if handicap_or_startpos < 2 or handicap_or_startpos > 9:
                raise ValueError(f"handicap must be between 2 and 9, got {handicap_or_startpos}")
        elif isinstance(handicap_or_startpos, list):
            if not all(isinstance(move, Move) for move in handicap_or_startpos):
                raise ValueError("startpos must be a list of Move objects")
        else:
            raise ValueError("handicap_or_startpos must be int, list[Move], or None")


def _setup_bots(
    black_bot: Bot,
    white_bot: Bot,
    board_size: int,
    komi: float,
    handicap_or_startpos: int | list[Move] | None = None,
) -> list[Move]:
    """
    Set up both bots for the game.

    Returns:
        List of setup moves that were placed on the board
    """
    setup_moves = []

    for bot in [black_bot, white_bot]:
        bot.send_command("clear_board")
        bot.send_command(f"boardsize {board_size}")
        bot.send_command(f"komi {komi}")

    if handicap_or_startpos is not None:
        if isinstance(handicap_or_startpos, int):
            # Fixed handicap placement
            positions = _get_fixed_handicap_positions(handicap_or_startpos, board_size)
            for row, col in positions:
                vertex = sgfmill_point_to_gtp_vertex((row, col), board_size)
                setup_moves.append(Move(Color.BLACK, vertex))
                for bot in [black_bot, white_bot]:
                    bot.send_command(f"play black {vertex}")
        elif isinstance(handicap_or_startpos, list):
            # Custom starting position - validate each move
            for move in handicap_or_startpos:
                if not _is_valid_move(move.vertex, board_size):
                    raise ValueError(f"Invalid setup move: {move.vertex}")
                if move.vertex.lower() in ("pass", "resign"):
                    raise ValueError(f"Setup moves cannot be pass or resign: {move.vertex}")
                setup_moves.append(move)
                for bot in [black_bot, white_bot]:
                    bot.send_command(f"play {move.color.value} {move.vertex}")

    return setup_moves


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
    color_to_move: Color | None = None,
    handicap_or_startpos: int | list[Move] | None = None,
    verbose: bool = False,
) -> FinishedGame:
    """
    Play a game between two bots.

    Args:
        black_bot: Bot playing black stones
        white_bot: Bot playing white stones
        board_size: Size of the Go board (default 19)
        komi: Komi value for white (default 6.5)
        max_moves: Maximum number of moves (default: board_size^2 * 5)
        color_to_move: Color to move first (default: Color.BLACK)
        handicap_or_startpos: Either handicap stones count or starting positions

    Returns:
        A FinishedGame object with the game result
    """
    _validate_game_parameters(board_size, komi, max_moves, handicap_or_startpos)

    if max_moves is None:
        max_moves = board_size * board_size * 5

    setup_moves = _setup_bots(black_bot, white_bot, board_size, komi, handicap_or_startpos)

    moves: list[Move] = []

    # Determine starting color
    if color_to_move is not None:
        current_color = color_to_move
    elif isinstance(handicap_or_startpos, int) and handicap_or_startpos >= 2:
        # Traditional handicap: white moves first
        current_color = Color.WHITE
    else:
        # Default: black moves first
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

            if verbose:
                print(f"Move {len(moves)+1}: {current_color} {vertex}")

            if not vertex:
                vertex = "pass"

            # Validate the move before processing
            if not _is_valid_move(vertex, board_size):
                logging.warning(f"Bot {current_bot.name} generated invalid move: {vertex}")
                return FinishedGame(
                    black_bot_name=black_bot.name,
                    white_bot_name=white_bot.name,
                    board_size=board_size,
                    komi=komi,
                    moves=moves,
                    result=GameResult.ILLEGAL_MOVE,
                    winner_name=None,
                    setup_moves=setup_moves
                )

            if vertex.lower() == "resign":
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
                    score=score,
                    setup_moves=setup_moves
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
                winner_name=None,
                setup_moves=setup_moves
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
                    winner_name=winner_name,
                    setup_moves=setup_moves
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
            winner_name=None,
            setup_moves=setup_moves
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
        score=score,
        setup_moves=setup_moves
    )
