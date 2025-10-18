#!/usr/bin/env python3
"""
Demo script showcasing the gtpmatch module features with some example code using it.
"""

import gtpmatch


def main():
    print("gtpmatch demo - Go bot matching library")
    print("=" * 50)

    # Demo game with GnuGo
    print("\n🎮 Playing demo game (9x9, limited to 10 moves):")
    try:
        with gtpmatch.launch_bot("GnuGo-Black", "gnugo --mode gtp --quiet") as black_bot, \
             gtpmatch.launch_bot("GnuGo-White", "gnugo --mode gtp --quiet") as white_bot:

            # Configure for fast play
            black_bot.send_command("time_settings 0 1 1")
            white_bot.send_command("time_settings 0 1 1")

            # Play a quick demo game
            game = gtpmatch.play_game(black_bot, white_bot, board_size=9, komi=6.5, max_moves=10)

            print(f"Game finished with {len(game.moves)} moves")
            print(f"Result: {game.result.value}")
            print(f"Winner: {game.winner()}")
            print(f"Score: {game.final_score()}")

            # Show last few moves
            print("\nMoves:")
            for i, move in enumerate(game.moves, 1):
                print(f"  Move {i}: {move.color.value} {move.vertex}")

            # Demo SGF export
            sgf_content = game.get_sgf()
            print(f"\nSGF preview: {sgf_content}...")

            # Save to file
            game.save_sgf("demo_game.sgf")
            print("Game saved to demo_game.sgf")

    except Exception as e:
        print(f"Demo game failed: {e}")

    # Demo handicap game
    print("\nPlaying handicap game (9x9, 3-stone handicap):")
    try:
        with gtpmatch.launch_bot("GnuGo-Black", "gnugo --mode gtp --quiet") as black_bot, \
             gtpmatch.launch_bot("GnuGo-White", "gnugo --mode gtp --quiet") as white_bot:

            # Configure for fast play
            black_bot.send_command("time_settings 0 1 1")
            white_bot.send_command("time_settings 0 1 1")

            # Play handicap game - black gets 3 stones, white moves first
            handicap_game = gtpmatch.play_game(
                black_bot,
                white_bot,
                board_size=9,
                komi=0.5,  # Reduced komi for handicap game
                max_moves=15,
                handicap_or_startpos=3
            )

            print(f"Handicap game finished with {len(handicap_game.moves)} moves")
            print(f"Setup stones: {len(handicap_game.setup_moves)} black stones")
            print(f"Result: {handicap_game.result.value}")
            print(f"Winner: {handicap_game.winner()}")

            # Show setup moves
            print("\nHandicap stones:")
            for i, move in enumerate(handicap_game.setup_moves, 1):
                print(f"  Setup {i}: {move.color.value} {move.vertex}")

            # Show first few regular moves
            print("\nFirst few moves:")
            for i, move in enumerate(handicap_game.moves[:5], 1):
                print(f"  Move {i}: {move.color.value} {move.vertex}")

            # Save handicap game
            handicap_game.save_sgf("demo_handicap_game.sgf")
            print("Handicap game saved to demo_handicap_game.sgf")

    except Exception as e:
        print(f"Handicap game failed: {e}")

    # Demo custom starting position
    print("\nPlaying game with custom starting position:")
    try:
        with gtpmatch.launch_bot("GnuGo-Black", "gnugo --mode gtp --quiet") as black_bot, \
             gtpmatch.launch_bot("GnuGo-White", "gnugo --mode gtp --quiet") as white_bot:

            # Configure for fast play
            black_bot.send_command("time_settings 0 1 1")
            white_bot.send_command("time_settings 0 1 1")

            # Create a custom starting position with mixed colors
            custom_setup = [
                gtpmatch.Move(gtpmatch.Color.BLACK, "D4"),
                gtpmatch.Move(gtpmatch.Color.WHITE, "D6"),
                gtpmatch.Move(gtpmatch.Color.BLACK, "F4"),
                gtpmatch.Move(gtpmatch.Color.WHITE, "F6"),
            ]

            # Play game with custom setup, white to move first
            custom_game = gtpmatch.play_game(
                black_bot,
                white_bot,
                board_size=9,
                komi=6.5,
                max_moves=12,
                color_to_move=gtpmatch.Color.WHITE,
                handicap_or_startpos=custom_setup
            )

            print(f"Custom game finished with {len(custom_game.moves)} moves")
            print(f"Setup stones: {len(custom_game.setup_moves)} mixed stones")
            print(f"Result: {custom_game.result.value}")

            # Show custom setup
            print("\nCustom setup stones:")
            for i, move in enumerate(custom_game.setup_moves, 1):
                print(f"  Setup {i}: {move.color.value} {move.vertex}")

            # Show regular moves
            print("\nRegular moves:")
            for i, move in enumerate(custom_game.moves[:8], 1):
                print(f"  Move {i}: {move.color.value} {move.vertex}")

            # Save custom game
            custom_game.save_sgf("demo_custom_game.sgf")
            print("Custom game saved to demo_custom_game.sgf")

    except Exception as e:
        print(f"Custom game failed: {e}")

    print("\nDemo completed! Check the generated SGF files.")


if __name__ == "__main__":
    main()
