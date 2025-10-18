"""
Tests for the sgf_utils module.
"""

import tempfile
from pathlib import Path
import pytest
import gtpmatch
import sgf_utils


def test_load_openings_all_nodes():
    sgf_content = """(;GM[1]FF[4]CA[UTF-8]AP[CGoban:3]ST[2]
RU[Japanese]SZ[19]KM[0.00]
PW[White]PB[Black]
(;B[pd]
(;W[pp]
(;B[dc])
(;B[dd]))
(;W[dp]
;B[fq]))
(;B[qd]))
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sgf', delete=False) as tmp:
        tmp.write(sgf_content)
        tmp_path = Path(tmp.name)

    try:
        openings = sgf_utils.load_openings_from_sgf(tmp_path, leaves_only=False)
        expected = """
[]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='Q4')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='Q4'), Move(color=<Color.BLACK: 'black'>, vertex='D17')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='Q4'), Move(color=<Color.BLACK: 'black'>, vertex='D16')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='D4')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='D4'), Move(color=<Color.BLACK: 'black'>, vertex='F3')]
[Move(color=<Color.BLACK: 'black'>, vertex='R16')]
"""
        assert expected.strip() == "\n".join([str(opening) for opening in openings])

    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def test_load_openings_leaves_only():
    sgf_content = """(;GM[1]FF[4]CA[UTF-8]AP[CGoban:3]ST[2]
RU[Japanese]SZ[19]KM[0.00]
PW[White]PB[Black]
(;B[pd]
(;W[pp]
(;B[dc])
(;B[dd]))
(;W[dp]
;B[fq]))
(;B[qd]))
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sgf', delete=False) as tmp:
        tmp.write(sgf_content)
        tmp_path = Path(tmp.name)

    try:
        openings = sgf_utils.load_openings_from_sgf(tmp_path, leaves_only=True)
        expected = """
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='Q4'), Move(color=<Color.BLACK: 'black'>, vertex='D17')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='Q4'), Move(color=<Color.BLACK: 'black'>, vertex='D16')]
[Move(color=<Color.BLACK: 'black'>, vertex='Q16'), Move(color=<Color.WHITE: 'white'>, vertex='D4'), Move(color=<Color.BLACK: 'black'>, vertex='F3')]
[Move(color=<Color.BLACK: 'black'>, vertex='R16')]
"""
        assert expected.strip() == "\n".join([str(opening) for opening in openings])

    finally:
        if tmp_path.exists():
            tmp_path.unlink()

def test_load_openings_empty_sgf():
    sgf_content = """(;GM[1]FF[4]SZ[19])"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sgf', delete=False) as tmp:
        tmp.write(sgf_content)
        tmp_path = Path(tmp.name)

    try:
        # Load with leaves_only=False (should include root)
        openings_all = sgf_utils.load_openings_from_sgf(tmp_path, leaves_only=False)
        assert len(openings_all) == 1
        assert len(openings_all[0]) == 0  # Empty sequence

        # Load with leaves_only=True (root is a leaf when it has no children)
        openings_leaves = sgf_utils.load_openings_from_sgf(tmp_path, leaves_only=True)
        assert len(openings_leaves) == 1
        assert len(openings_leaves[0]) == 0  # Empty sequence

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__])
