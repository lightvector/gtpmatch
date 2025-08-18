#!/usr/bin/env python3
"""
Demo script showcasing the gtpmatch module features.
"""

import gtpmatch

def main():
    print("🔥 gtpmatch demo - Advanced Go bot matching")
    print("=" * 50)

    # Demo coordinate conversion
    print("\n📍 Coordinate system demo:")
    test_coords = ["D4", "A1", "T19", "J4", "AA1", "AB5", "pass"]
    for coord in test_coords:
        try:
            sgf_point = gtpmatch.gtp_vertex_to_sgf_point(coord, 30)
            back_to_gtp = gtpmatch.sgf_point_to_gtp_vertex(sgf_point, 30)
            print(f"  {coord:>4} → {sgf_point} → {back_to_gtp}")
        except ValueError as e:
            print(f"  {coord:>4} → ERROR: {e}")

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
            print("\nLast few moves:")
            for i, move in enumerate(game.moves[-5:], 1):
                print(f"  Move {len(game.moves)-5+i}: {move.color.value} {move.vertex}")

            # Demo SGF export
            sgf_content = game.get_sgf()
            print(f"\nSGF preview: {sgf_content}...")

            # Save to file
            game.save_sgf("demo_game.sgf")
            print("Game saved to demo_game.sgf")

    except Exception as e:
        print(f"Demo game failed: {e}")

    print("\n✅ Demo complete!")

if __name__ == "__main__":
    main()
