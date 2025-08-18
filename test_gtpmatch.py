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
    # Test basic coordinates
    assert gtpmatch.gtp_vertex_to_sgf_point("D4", 19) == (15, 3)
    assert gtpmatch.gtp_vertex_to_sgf_point("A1", 19) == (18, 0)
    assert gtpmatch.gtp_vertex_to_sgf_point("T19", 19) == (0, 18)
    assert gtpmatch.gtp_vertex_to_sgf_point("pass", 19) is None
    
    # Test skipping I
    assert gtpmatch.gtp_vertex_to_sgf_point("J4", 19) == (15, 8)  # J is the 9th letter (index 8)
    
    # Test extended coordinates for large boards
    assert gtpmatch.gtp_vertex_to_sgf_point("AA1", 30) == (29, 25)  # AA is 26th column
    assert gtpmatch.gtp_vertex_to_sgf_point("AB1", 30) == (29, 26)  # AB is 27th column
    
    # Test reverse conversion
    assert gtpmatch.sgf_point_to_gtp_vertex((15, 3), 19) == "D4"
    assert gtpmatch.sgf_point_to_gtp_vertex((18, 0), 19) == "A1"
    assert gtpmatch.sgf_point_to_gtp_vertex((0, 18), 19) == "T19"
    assert gtpmatch.sgf_point_to_gtp_vertex(None, 19) == "pass"
    
    # Test large board reverse conversion
    assert gtpmatch.sgf_point_to_gtp_vertex((29, 25), 30) == "AA1"
    assert gtpmatch.sgf_point_to_gtp_vertex((29, 26), 30) == "AB1"
    
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
    # Test coordinates beyond Z
    test_cases = [
        ("AA1", 30, (29, 25)),
        ("AB1", 30, (29, 26)), 
        ("AC1", 30, (29, 27)),
        ("BA1", 51, (50, 50)),  # Second letter cycles
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
    assert gtpmatch.gtp_vertex_to_sgf_point("H1", 19) == (18, 7)
    assert gtpmatch.gtp_vertex_to_sgf_point("J1", 19) == (18, 8)
    
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


if __name__ == "__main__":
    pytest.main([__file__])