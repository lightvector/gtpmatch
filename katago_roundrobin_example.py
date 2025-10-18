#!/usr/bin/env python3
"""
Round-robin tournament script specialized for KataGo bots using the gtpmatch library.

This script runs a round-robin tournament where each bot plays against every other bot
twice (once as black, once as white) for multiple rounds. It supports:
- Multiple KataGo instances with different configurations
- Random rule variations (Japanese, Chinese, etc.)
- Optional forced openings from SGF files
- Automatic SGF and log output
"""

import logging
import os
import sys
import random
from pathlib import Path
from typing import Any

import sgfmill.sgf

import gtpmatch
import sgf_utils


def get_katago_command(
    name: str,
    exe: str,
    config: str,
    model: str,
    logs_dir: Path,
    override: str | None = None,
) -> list[str]:
    """
    Get the command line for a KataGo player with the given configuration.

    Args:
        name: Arbitrary name for the player
        exe: Path to KataGo executable
        config: Path to GTP config file
        model: Path to neural network model
        logs_dir: Directory for log files
        override: Optional configuration overrides
    """
    log_subdir = logs_dir / ("bot_" + "".join(c for c in name if c.isalnum() or c in '_-'))
    log_config = f"logDir={log_subdir}"

    if override is not None:
        full_override = f"{log_config},{override}"
    else:
        full_override = log_config

    return [str(exe), "gtp", "-config", str(config), "-model", str(model), "-override-config", full_override]


def main():
    ###################################################################################
    # CONFIGURATION - MODIFY THIS SECTION FOR YOUR SETUP
    ###################################################################################

    # Where to output SGFs and logs
    sgfs_dir = Path("./my_roundrobin/sgfs")
    logs_dir = Path("./my_roundrobin/logs")

    # Tournament settings
    board_size = 19
    move_limit = 800

    # Each round, each player will play every other player twice, once as black and once as white.
    num_rounds = 1000000000  # Set large number to run indefinitely

    # Force games to start with particular openings, for greater variety or for testing
    # Set to None for no forced openings
    # Set to path of an SGF file to load all possible opening sequences from that sgf's move tree.
    opening_sgf_path: Path | None = None  # Example: Path("path/to/openings.sgf")
    # Set to True to use only leaf nodes in the SGF, False to use all nodes in the tree
    opening_leaves_only: bool = False

    # Add all the players who will be in the round-robin
    player_commands: dict[str, list[str]] = {}

    model = Path("/path/to/some/model/to/use.bin.gz")
    config = Path("./gtp.cfg")
    exe = Path("./katago")

    player_commands["mybot"] = get_katago_command(
        name="mybot", exe=exe, config=config, model=model, logs_dir=logs_dir
    )
    player_commands["myotherbot"] = get_katago_command(
        name="myotherbot", exe=exe, config=config, model=model, logs_dir=logs_dir, override="numSearchThreads=8,maxVisits=12345"
    )

    ###################################################################################
    # END OF CONFIGURATION
    ###################################################################################

    # Create output directories
    sgfs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Set up logging
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logs_dir / "log.log", format='%(asctime)s %(message)s', level=logging.INFO)
    console = logging.StreamHandler()
    logging.getLogger('').addHandler(console)

    # Load openings from SGF if specified
    loaded_openings = None
    if opening_sgf_path is not None:
        logging.info(f"Loading openings from SGF: {opening_sgf_path}")
        loaded_openings = sgf_utils.load_openings_from_sgf(opening_sgf_path, opening_leaves_only)
        mode = "leaf nodes only" if opening_leaves_only else "all nodes"
        logging.info(f"Loaded {len(loaded_openings)} opening sequences from SGF ({mode})")

    # Incrementing counter for naming the SGF files for output
    game_output_number = 0

    # Main tournament loop
    for round_num in range(num_rounds):

        # Create all pairings for this round
        player_names = list(player_commands.keys())
        pairs = []
        for player_name_w in player_names:
            for player_name_b in player_names:
                if player_name_w != player_name_b:
                    pairs.append((player_name_w, player_name_b))

        # Randomize game order to avoid bias if interrupted
        random.shuffle(pairs)

        # Run all games in the round
        for game_num, (player_name_w, player_name_b) in enumerate(pairs):
            try:
                # Launch both bots
                with gtpmatch.launch_bot(player_name_b, player_commands[player_name_b]) as black_bot, \
                     gtpmatch.launch_bot(player_name_w, player_commands[player_name_w]) as white_bot:

                    # Clear caches to ensure re-randomized evaluations
                    # Not actually needed if you launch the bots fresh as we do in this script,
                    # but good to have if you switch to playing multiple games with the same bot.
                    black_bot.send_command("clear_cache", raise_on_failure=False)
                    white_bot.send_command("clear_cache", raise_on_failure=False)

                    # Apply random rules and get appropriate komi
                    choice = random.choice([1, 2, 3, 4, 1, 2])
                    if choice == 1:
                        rules = "Japanese"
                        for bot in [black_bot, white_bot]:
                            bot.send_command("kata-set-rules japanese", raise_on_failure=False)
                        komi = 6.5
                    elif choice == 2:
                        rules = "Chinese"
                        for bot in [black_bot, white_bot]:
                            bot.send_command("kata-set-rules chinese-ogs", raise_on_failure=False)
                        komi = 7.0
                    elif choice == 3:
                        rules = "Chinese-With-Group-Tax"
                        for bot in [black_bot, white_bot]:
                            bot.send_command("kata-set-rules stone-scoring", raise_on_failure=False)
                            bot.send_command("kata-set-rule ko POSITIONAL", raise_on_failure=False)
                        komi = 7.0
                    else:
                        rules = "Tromp-Taylor-With-Button"
                        for bot in [black_bot, white_bot]:
                            bot.send_command("kata-set-rules tromp-taylor", raise_on_failure=False)
                            bot.send_command("kata-set-rule hasButton true", raise_on_failure=False)
                        komi = 7.0

                    # Determine forced opening if any
                    forced_opening_moves = None
                    color_to_move = gtpmatch.Color.BLACK
                    if loaded_openings:
                        forced_opening_moves = random.choice(loaded_openings)
                        if len(forced_opening_moves) > 0 and forced_opening_moves[-1].color == gtpmatch.Color.BLACK:
                            color_to_move = gtpmatch.Color.WHITE

                    # Play the game
                    logging.info(f"Round {round_num}, Game {game_num}, {player_name_w} (w) vs {player_name_b} (b) {rules=}")
                    game = gtpmatch.play_game(
                        black_bot=black_bot,
                        white_bot=white_bot,
                        board_size=board_size,
                        komi=komi,
                        max_moves=move_limit,
                        color_to_move=color_to_move,
                        handicap_or_startpos=forced_opening_moves
                    )

                    game.rules = rules

                    logging.info(f"Num moves: {len(game.moves)}")
                    if game.winner():
                        logging.info(f"Winner: {game.winner()}")
                    if game.final_score():
                        logging.info(f"Score: {game.final_score()}")

                    # Find next available filename
                    while True:
                        sgf_path = sgfs_dir / f"{game_output_number}.sgf"
                        if not sgf_path.exists():
                            break
                        game_output_number += 1

                    # Save the game
                    game.save_sgf(sgf_path)
                    logging.info(f"Wrote {sgf_path}")
                    game_output_number += 1

            except Exception as e:
                logging.error(f"Game failed: {e}")
                continue


if __name__ == "__main__":
    main()
