"""
Tests for the gtpmatch module.
"""

import tempfile
from pathlib import Path
import pytest
import gtpmatch


def test_bot_launch_and_basic_communication():
    """Test launching a bot and basic GTP communication."""
    with gtpmatch.launch_bot("TestGnuGo", "gnugo --mode gtp --quiet") as bot:
        assert bot.name == "TestGnuGo"

        # Test basic command
        response = bot.send_command("protocol_version")
        assert response.strip() in ["1", "2"]

        # Test boardsize command
        response = bot.send_command("boardsize 9")
        # Should succeed (empty response is ok)

        # Test clear board
        response = bot.send_command("clear_board")


def test_bot_command_failure():
    """Test bot command failure handling."""
    with gtpmatch.launch_bot("TestGnuGo", "gnugo --mode gtp --quiet") as bot:
        # Test invalid command with raise_on_failure=True (default)
        with pytest.raises(gtpmatch.GTPError):
            bot.send_command("invalid_command_xyz")

        # Test invalid command with raise_on_failure=False
        response = bot.send_command("invalid_command_xyz", raise_on_failure=False)
        # Should not raise, just return the error response


def test_play_simple_game():
    """Test playing a simple game between two gnugo instances."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure bots for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Play a quick game on 9x9 board
        game = gtpmatch.play_game(bot1, bot2, board_size=9, komi=6.5)

        # Verify game properties
        assert game.black_bot_name == "GnuGo1"
        assert game.white_bot_name == "GnuGo2"
        assert game.board_size == 9
        assert game.komi == 6.5
        assert len(game.moves) > 0

        # Game should have ended (either by result or consecutive passes)
        pass_count = sum(1 for move in game.moves[-2:] if move.vertex.lower() == "pass")
        has_result = game.result != gtpmatch.GameResult.UNKNOWN
        assert pass_count >= 2 or has_result


def test_game_move_recording():
    """Test that moves are properly recorded during a game."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for very fast play to limit game length
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        game = gtpmatch.play_game(bot1, bot2, board_size=9, komi=6.5)

        # Check that moves alternate colors
        for i, move in enumerate(game.moves):
            expected_color = gtpmatch.Color.BLACK if i % 2 == 0 else gtpmatch.Color.WHITE
            assert move.color == expected_color

        # Check that moves are valid GTP format (letter+number or "pass")
        for move in game.moves:
            vertex = move.vertex.lower()
            if vertex != "pass":
                assert len(vertex) >= 2
                assert vertex[0].isalpha()
                assert vertex[1:].isdigit()


def test_sgf_export():
    """Test SGF file export functionality."""
    # Create a minimal finished game
    moves = [
        gtpmatch.Move(gtpmatch.Color.BLACK, "D4"),
        gtpmatch.Move(gtpmatch.Color.WHITE, "D6"),
        gtpmatch.Move(gtpmatch.Color.BLACK, "pass"),
        gtpmatch.Move(gtpmatch.Color.WHITE, "pass"),
    ]

    game = gtpmatch.FinishedGame(
        black_bot_name="TestBot1",
        white_bot_name="TestBot2",
        board_size=9,
        komi=6.5,
        moves=moves,
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="TestBot1"
    )

    # Test SGF export
    with tempfile.NamedTemporaryFile(suffix=".sgf", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        game.save_sgf(tmp_path)

        # Verify file was created and has content
        assert tmp_path.exists()
        content = tmp_path.read_text()
        assert len(content) > 0

        # Basic SGF format checks
        assert content.startswith("(;")
        assert content.rstrip().endswith(")")
        assert "PB[TestBot1]" in content
        assert "PW[TestBot2]" in content
        assert "SZ[9]" in content
        assert "KM[6.5]" in content

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_winner_method():
    """Test the winner() method on FinishedGame."""
    # Test black win
    game_black_win = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="Bot1"
    )
    assert game_black_win.winner() == "Bot1"

    # Test white win
    game_white_win = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.WHITE_WIN,
        winner_name="Bot2"
    )
    assert game_white_win.winner() == "Bot2"

    # Test draw
    game_draw = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.DRAW,
        winner_name=None
    )
    assert game_draw.winner() is None


def test_bot_command_list_format():
    """Test that bot launching works with command as list."""
    with gtpmatch.launch_bot("TestGnuGo", ["gnugo", "--mode", "gtp", "--quiet"]) as bot:
        response = bot.send_command("protocol_version")
        assert response.strip() in ["1", "2"]


def test_different_board_sizes():
    """Test playing games on different board sizes."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Test 7x7 board
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        game = gtpmatch.play_game(bot1, bot2, board_size=7, komi=0.5)
        assert game.board_size == 7
        assert game.komi == 0.5


def test_coordinate_conversion():
    """Test GTP to SGF coordinate conversion helpers."""
    # Test basic coordinates - corrected to match actual SGF coordinate system
    assert gtpmatch.gtp_vertex_to_sgf_point("D4", 19) == (3, 3)  # D4: row 4 (0-indexed = 3), col D (0-indexed = 3)
    assert gtpmatch.gtp_vertex_to_sgf_point("A1", 19) == (0, 0)  # A1: row 1 (0-indexed = 0), col A (0-indexed = 0)
    assert gtpmatch.gtp_vertex_to_sgf_point("T19",
                                            19) == (18, 18)  # T19: row 19 (0-indexed = 18), col T (0-indexed = 18)
    assert gtpmatch.gtp_vertex_to_sgf_point("pass", 19) is None

    # Test skipping I
    assert gtpmatch.gtp_vertex_to_sgf_point("J4", 19) == (3, 8)  # J is the 9th letter (index 8), row 4 (0-indexed = 3)

    # Test extended coordinates for large boards
    assert gtpmatch.gtp_vertex_to_sgf_point("AA1",
                                            30) == (0, 25)  # AA is 26th column (0-indexed = 25), row 1 (0-indexed = 0)
    assert gtpmatch.gtp_vertex_to_sgf_point("AB1",
                                            30) == (0, 26)  # AB is 27th column (0-indexed = 26), row 1 (0-indexed = 0)

    # Test reverse conversion
    assert gtpmatch.sgf_point_to_gtp_vertex((3, 3), 19) == "D4"
    assert gtpmatch.sgf_point_to_gtp_vertex((0, 0), 19) == "A1"
    assert gtpmatch.sgf_point_to_gtp_vertex((18, 18), 19) == "T19"
    assert gtpmatch.sgf_point_to_gtp_vertex(None, 19) == "pass"

    # Test large board reverse conversion
    assert gtpmatch.sgf_point_to_gtp_vertex((0, 25), 30) == "AA1"
    assert gtpmatch.sgf_point_to_gtp_vertex((0, 26), 30) == "AB1"

    # Test error cases
    with pytest.raises(ValueError):
        gtpmatch.gtp_vertex_to_sgf_point("invalid", 19)
    with pytest.raises(ValueError):
        gtpmatch.gtp_vertex_to_sgf_point("A", 19)
    with pytest.raises(ValueError):
        gtpmatch.gtp_vertex_to_sgf_point("A25", 19)  # Outside board


def test_get_sgf_string():
    """Test getting SGF as string without saving to file."""
    moves = [
        gtpmatch.Move(gtpmatch.Color.BLACK, "D4"),
        gtpmatch.Move(gtpmatch.Color.WHITE, "D6"),
        gtpmatch.Move(gtpmatch.Color.BLACK, "pass"),
        gtpmatch.Move(gtpmatch.Color.WHITE, "pass"),
    ]

    game = gtpmatch.FinishedGame(
        black_bot_name="TestBot1",
        white_bot_name="TestBot2",
        board_size=9,
        komi=6.5,
        moves=moves,
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="TestBot1",
        score="B+3.5"
    )

    sgf_string = game.get_sgf()

    # Basic checks
    assert sgf_string.startswith("(;")
    assert sgf_string.rstrip().endswith(")")
    assert "PB[TestBot1]" in sgf_string
    assert "PW[TestBot2]" in sgf_string
    assert "SZ[9]" in sgf_string
    assert "KM[6.5]" in sgf_string
    assert "RE[B+3.5]" in sgf_string


def test_final_score_method():
    """Test the final_score() method."""
    game = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="Bot1",
        score="B+12.5"
    )

    assert game.final_score() == "B+12.5"

    game_no_score = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.UNKNOWN,
        winner_name=None,
        score=None
    )

    assert game_no_score.final_score() is None


def test_game_result_types():
    """Test all game result types."""
    # Test ILLEGAL_MOVE result
    game = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.ILLEGAL_MOVE,
        winner_name=None
    )

    sgf_string = game.get_sgf()
    assert "RE[?]" in sgf_string

    # Test resignation
    game_resign = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.WHITE_WIN,
        winner_name="Bot2",
        score="W+R"
    )

    sgf_string = game_resign.get_sgf()
    assert "RE[W+R]" in sgf_string

    # Test unfinished game
    game_unfinished = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.UNFINISHED,
        winner_name=None
    )

    sgf_string = game_unfinished.get_sgf()
    assert "RE[" not in sgf_string  # No result tag for unfinished games


def test_max_moves_limit():
    """Test that games respect the max_moves limit."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Test with very small max_moves
        game = gtpmatch.play_game(bot1, bot2, board_size=9, max_moves=5)
        assert len(game.moves) <= 5

        # If game hit the move limit, it should be UNFINISHED
        if len(game.moves) == 5:
            assert game.result == gtpmatch.GameResult.UNFINISHED


def test_large_coordinate_system():
    """Test coordinate system for large boards."""
    # Test coordinates beyond Z - corrected coordinates
    test_cases = [
        ("AA1", 30, (0, 25)),  # AA1: row 1 (0-indexed = 0), col AA (0-indexed = 25)
        ("AB1", 30, (0, 26)),  # AB1: row 1 (0-indexed = 0), col AB (0-indexed = 26)
        ("AC1", 30, (0, 27)),  # AC1: row 1 (0-indexed = 0), col AC (0-indexed = 27)
        ("BA1", 51, (0, 50)),  # BA1: row 1 (0-indexed = 0), col BA (0-indexed = 50)
    ]

    for gtp_vertex, board_size, expected_sgf in test_cases:
        actual_sgf = gtpmatch.gtp_vertex_to_sgf_point(gtp_vertex, board_size)
        assert actual_sgf == expected_sgf, f"Failed for {gtp_vertex}: expected {expected_sgf}, got {actual_sgf}"

        # Test round trip
        converted_back = gtpmatch.sgf_point_to_gtp_vertex(actual_sgf, board_size)
        assert converted_back == gtp_vertex, f"Round trip failed: {gtp_vertex} -> {actual_sgf} -> {converted_back}"


def test_coordinate_skips_i():
    """Test that coordinate system properly skips I."""
    # H should be index 7, J should be index 8 (skipping I)
    assert gtpmatch.gtp_vertex_to_sgf_point("H1", 19) == (0, 7)  # H1: row 1 (0-indexed = 0), col H (0-indexed = 7)
    assert gtpmatch.gtp_vertex_to_sgf_point("J1", 19) == (
        0, 8
    )  # J1: row 1 (0-indexed = 0), col J (0-indexed = 8, skipping I)

    # Test in extended coordinates too
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    assert 'I' not in letters
    assert len(letters) == 25  # 26 letters minus I


def test_input_validation():
    """Test input validation for game parameters."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Test invalid board size
        with pytest.raises(ValueError, match="board_size must be an integer between 1 and 99"):
            gtpmatch.play_game(bot1, bot2, board_size=0)

        with pytest.raises(ValueError, match="board_size must be an integer between 1 and 99"):
            gtpmatch.play_game(bot1, bot2, board_size=100)

        # Test invalid komi
        with pytest.raises(ValueError, match="komi must be a number between -100 and 100"):
            gtpmatch.play_game(bot1, bot2, komi=-150)

        with pytest.raises(ValueError, match="komi must be a number between -100 and 100"):
            gtpmatch.play_game(bot1, bot2, komi=150)

        # Test invalid max_moves
        with pytest.raises(ValueError, match="max_moves must be a positive integer or None"):
            gtpmatch.play_game(bot1, bot2, max_moves=0)

        with pytest.raises(ValueError, match="max_moves must be a positive integer or None"):
            gtpmatch.play_game(bot1, bot2, max_moves=-5)


def test_color_opposite():
    """Test the Color.opposite() method."""
    assert gtpmatch.Color.BLACK.opposite() == gtpmatch.Color.WHITE
    assert gtpmatch.Color.WHITE.opposite() == gtpmatch.Color.BLACK


def test_unfinished_game_result():
    """Test UNFINISHED game result functionality."""
    # Test that UNFINISHED games have no RE tag in SGF
    game = gtpmatch.FinishedGame(
        black_bot_name="Bot1",
        white_bot_name="Bot2",
        board_size=9,
        komi=6.5,
        moves=[gtpmatch.Move(gtpmatch.Color.BLACK, "D4")],
        result=gtpmatch.GameResult.UNFINISHED,
        winner_name=None
    )

    # Check SGF has no result tag
    sgf_content = game.get_sgf()
    assert "RE[" not in sgf_content
    assert "PB[Bot1]" in sgf_content  # Other tags should still be present
    assert "PW[Bot2]" in sgf_content

    # Check that winner and score are None
    assert game.winner() is None
    assert game.final_score() is None


def test_fixed_handicap_placement():
    """Test fixed handicap stone placement positions."""
    # Test basic 2-stone handicap on 19x19
    positions = gtpmatch._get_fixed_handicap_positions(2, 19)
    assert len(positions) == 2
    assert (3, 3) in positions  # D4 equivalent
    assert (15, 15) in positions  # Q16 equivalent

    # Test 3-stone handicap
    positions = gtpmatch._get_fixed_handicap_positions(3, 19)
    assert len(positions) == 3
    assert (3, 3) in positions  # D4
    assert (15, 15) in positions  # Q16
    assert (3, 15) in positions  # D16

    # Test 4-stone handicap
    positions = gtpmatch._get_fixed_handicap_positions(4, 19)
    assert len(positions) == 4
    assert (3, 3) in positions  # D4
    assert (15, 15) in positions  # Q16
    assert (3, 15) in positions  # D16
    assert (15, 3) in positions  # Q4

    # Test 5-stone handicap (adds center)
    positions = gtpmatch._get_fixed_handicap_positions(5, 19)
    assert len(positions) == 5
    assert (9, 9) in positions  # K10 center stone

    # Test 9-stone handicap (full set)
    positions = gtpmatch._get_fixed_handicap_positions(9, 19)
    assert len(positions) == 9
    expected_positions = [
        (3, 3),
        (15, 15),
        (3, 15),
        (15, 3),  # corners
        (9, 9),  # center
        (3, 9),
        (15, 9),  # sides  
        (9, 3),
        (9, 15)  # top/bottom
    ]
    for pos in expected_positions:
        assert pos in positions

    # Test smaller board (13x13 uses 4th line)
    positions = gtpmatch._get_fixed_handicap_positions(2, 13)
    assert len(positions) == 2
    assert (3, 3) in positions  # 4th line from edge (13>=13 so uses 4th line)
    assert (9, 9) in positions

    # Test 9x9 board (uses 3rd line)
    positions = gtpmatch._get_fixed_handicap_positions(2, 9)
    assert len(positions) == 2
    assert (2, 2) in positions  # 3rd line from edge
    assert (6, 6) in positions


def test_fixed_handicap_validation():
    """Test validation of fixed handicap placement."""
    # Test invalid handicap numbers
    with pytest.raises(ValueError, match="Handicap must be between 2 and 9"):
        gtpmatch._get_fixed_handicap_positions(1, 19)

    with pytest.raises(ValueError, match="Handicap must be between 2 and 9"):
        gtpmatch._get_fixed_handicap_positions(10, 19)

    # Test board size restrictions
    with pytest.raises(ValueError, match="No handicap supported for boards smaller than 7x7"):
        gtpmatch._get_fixed_handicap_positions(2, 6)

    with pytest.raises(ValueError, match="Maximum 4 handicap stones for 7x7 board"):
        gtpmatch._get_fixed_handicap_positions(5, 7)

    with pytest.raises(ValueError, match="Maximum 4 handicap stones for even-sized boards"):
        gtpmatch._get_fixed_handicap_positions(5, 8)


def test_handicap_game_play():
    """Test playing a game with handicap stones."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Play game with 3-stone handicap
        game = gtpmatch.play_game(bot1, bot2, board_size=9, handicap_or_startpos=3)

        # Verify setup
        assert game.board_size == 9
        assert game.setup_moves is not None
        assert len(game.setup_moves) == 3

        # All setup moves should be black stones
        for move in game.setup_moves:
            assert move.color == gtpmatch.Color.BLACK
            assert move.vertex.lower() != "pass"

        # First regular move should be white (after handicap)
        if len(game.moves) > 0:
            assert game.moves[0].color == gtpmatch.Color.WHITE


def test_custom_starting_position():
    """Test custom starting positions with list of moves."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Create custom starting position with mixed colors
        custom_moves = [
            gtpmatch.Move(gtpmatch.Color.BLACK, "D4"),
            gtpmatch.Move(gtpmatch.Color.WHITE, "E5"),
            gtpmatch.Move(gtpmatch.Color.BLACK, "F6"),
        ]

        # Play game with custom starting position
        game = gtpmatch.play_game(bot1, bot2, board_size=9, handicap_or_startpos=custom_moves)

        # Verify setup
        assert game.setup_moves is not None
        assert len(game.setup_moves) == 3
        assert game.setup_moves == custom_moves

        # Regular moves should start after setup
        if len(game.moves) > 0:
            # First move should be black (default starting color)
            assert game.moves[0].color == gtpmatch.Color.BLACK


def test_color_to_move_parameter():
    """Test the color_to_move parameter."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Test white to move first
        game = gtpmatch.play_game(bot1, bot2, board_size=9, color_to_move=gtpmatch.Color.WHITE)
        if len(game.moves) > 0:
            assert game.moves[0].color == gtpmatch.Color.WHITE

        # Test black to move first
        game = gtpmatch.play_game(bot1, bot2, board_size=9, color_to_move=gtpmatch.Color.BLACK)
        if len(game.moves) > 0:
            assert game.moves[0].color == gtpmatch.Color.BLACK


def test_color_to_move_with_handicap():
    """Test color_to_move parameter overriding handicap defaults."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Handicap game normally starts with white, but override to black
        game = gtpmatch.play_game(bot1, bot2, board_size=9, handicap_or_startpos=2, color_to_move=gtpmatch.Color.BLACK)

        assert game.setup_moves is not None
        assert len(game.setup_moves) == 2

        if len(game.moves) > 0:
            assert game.moves[0].color == gtpmatch.Color.BLACK


def test_sgf_export_with_setup_stones():
    """Test SGF export includes setup stones correctly."""
    # Test with handicap stones (valid for 9x9 board)
    setup_moves = [
        gtpmatch.Move(gtpmatch.Color.BLACK, "C3"),
        gtpmatch.Move(gtpmatch.Color.BLACK, "G7"),
        gtpmatch.Move(gtpmatch.Color.BLACK, "C7"),
    ]

    regular_moves = [
        gtpmatch.Move(gtpmatch.Color.WHITE, "E5"),
        gtpmatch.Move(gtpmatch.Color.BLACK, "F6"),
    ]

    game = gtpmatch.FinishedGame(
        black_bot_name="TestBot1",
        white_bot_name="TestBot2",
        board_size=9,
        komi=6.5,
        moves=regular_moves,
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="TestBot1",
        setup_moves=setup_moves
    )

    sgf_string = game.get_sgf()

    # Check that SGF contains setup stones
    assert "AB[" in sgf_string  # Black setup stones

    # Test with mixed color setup stones
    mixed_setup = [
        gtpmatch.Move(gtpmatch.Color.BLACK, "D4"),
        gtpmatch.Move(gtpmatch.Color.WHITE, "E5"),
    ]

    game_mixed = gtpmatch.FinishedGame(
        black_bot_name="TestBot1",
        white_bot_name="TestBot2",
        board_size=9,
        komi=6.5,
        moves=[],
        result=gtpmatch.GameResult.DRAW,
        winner_name=None,
        setup_moves=mixed_setup
    )

    sgf_mixed = game_mixed.get_sgf()
    assert "AB[" in sgf_mixed  # Black setup stones
    assert "AW[" in sgf_mixed  # White setup stones


def test_handicap_input_validation():
    """Test input validation for new handicap parameters."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Test invalid handicap number
        with pytest.raises(ValueError, match="handicap must be between 2 and 9"):
            gtpmatch.play_game(bot1, bot2, handicap_or_startpos=1)

        with pytest.raises(ValueError, match="handicap must be between 2 and 9"):
            gtpmatch.play_game(bot1, bot2, handicap_or_startpos=10)

        # Test invalid startpos type
        with pytest.raises(ValueError, match="startpos must be a list of Move objects"):
            gtpmatch.play_game(bot1, bot2, handicap_or_startpos=["invalid"])

        # Test invalid handicap_or_startpos type
        with pytest.raises(ValueError, match="handicap_or_startpos must be int, list\\[Move\\], or None"):
            gtpmatch.play_game(bot1, bot2, handicap_or_startpos="invalid")


def test_handicap_coordinate_conversion():
    """Test that handicap positions convert correctly to GTP coordinates."""
    # Test 19x19 board positions
    positions = gtpmatch._get_fixed_handicap_positions(4, 19)

    # Convert to GTP and verify they're valid
    for row, col in positions:
        vertex = gtpmatch.sgf_point_to_gtp_vertex((row, col), 19)
        # Should be valid GTP format
        assert len(vertex) >= 2
        assert vertex[0].isalpha()
        assert vertex[1:].isdigit()

        # Should round-trip correctly
        converted_back = gtpmatch.gtp_vertex_to_sgf_point(vertex, 19)
        assert converted_back == (row, col)


def test_invalid_setup_moves():
    """Test that invalid setup moves are caught early."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Test invalid coordinate
        invalid_moves = [
            gtpmatch.Move(gtpmatch.Color.BLACK, "Z99"),  # Outside board
        ]

        with pytest.raises(ValueError, match="Invalid setup move"):
            gtpmatch.play_game(bot1, bot2, board_size=9, handicap_or_startpos=invalid_moves)

        # Test pass/resign in setup
        pass_moves = [
            gtpmatch.Move(gtpmatch.Color.BLACK, "pass"),
        ]

        with pytest.raises(ValueError, match="Setup moves cannot be pass or resign"):
            gtpmatch.play_game(bot1, bot2, board_size=9, handicap_or_startpos=pass_moves)


def test_move_validation_function():
    """Test the _is_valid_move function."""
    # Valid moves
    assert gtpmatch._is_valid_move("D4", 19) == True
    assert gtpmatch._is_valid_move("pass", 19) == True
    assert gtpmatch._is_valid_move("resign", 19) == True
    assert gtpmatch._is_valid_move("A1", 9) == True

    # Invalid moves
    assert gtpmatch._is_valid_move("Z99", 19) == False
    assert gtpmatch._is_valid_move("A10", 9) == False  # Outside 9x9 board
    assert gtpmatch._is_valid_move("invalid", 19) == False
    assert gtpmatch._is_valid_move("", 19) == False


def test_sgf_export_validates_moves():
    """Test that SGF export validates moves and raises on invalid ones."""
    # Test with invalid move in game record (should not happen in practice)
    moves = [
        gtpmatch.Move(gtpmatch.Color.BLACK, "Z99"),  # Invalid move
    ]

    game = gtpmatch.FinishedGame(
        black_bot_name="TestBot1",
        white_bot_name="TestBot2",
        board_size=9,
        komi=6.5,
        moves=moves,
        result=gtpmatch.GameResult.BLACK_WIN,
        winner_name="TestBot1"
    )

    # Should raise ValueError during SGF export
    with pytest.raises(ValueError, match="Invalid move found in game record"):
        game.get_sgf()


def test_default_behavior_unchanged():
    """Test that default behavior is unchanged when new parameters are None."""
    with gtpmatch.launch_bot("GnuGo1", "gnugo --mode gtp --quiet") as bot1, \
         gtpmatch.launch_bot("GnuGo2", "gnugo --mode gtp --quiet") as bot2:

        # Configure for fast play
        bot1.send_command("time_settings 0 1 1")
        bot2.send_command("time_settings 0 1 1")

        # Play normal game (should be unchanged from before)
        game = gtpmatch.play_game(bot1, bot2, board_size=9, komi=6.5)

        # Should have no setup moves
        assert game.setup_moves is None or len(game.setup_moves) == 0

        # Should start with black
        if len(game.moves) > 0:
            assert game.moves[0].color == gtpmatch.Color.BLACK


if __name__ == "__main__":
    pytest.main([__file__])
