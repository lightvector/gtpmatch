from typing import Any
from pathlib import Path

import gtpmatch
import sgfmill.sgf


def load_openings_from_sgf(sgf_path: Path, leaves_only: bool) -> list[list[gtpmatch.Move]]:
    """
    Load all possible opening sequences from an SGF file.

    Args:
        sgf_path: Path to SGF file containing opening variations
        leaves_only: If True, only load sequences at leaf nodes. If False, load all nodes.

    Returns:
        List of openings, where each opening is a list of moves.
        If leaves_only is True, only leaf nodes are included as openings.
        If leaves_only is False, every node in the tree is treated as a possible opening.
    """
    openings = []

    with open(sgf_path, 'r') as f:
        sgf_content = f.read()

    sgf_game = sgfmill.sgf.Sgf_game.from_string(sgf_content)
    board_size = sgf_game.get_size()

    def traverse_tree(node: Any, current_sequence: list[gtpmatch.Move]) -> None:
        """Recursively traverse the SGF tree, collecting all sequences."""

        # Check if this is a leaf node (no children)
        is_leaf = len(list(node)) == 0

        move_info = None
        if node.has_property('B'):
            color = gtpmatch.Color.BLACK
            move_value = node.get_raw_property_map()['B']
            assert len(move_value) == 1
            move_value = move_value[0].decode("utf-8")
            move_info = (color, move_value)
        elif node.has_property('W'):
            color = gtpmatch.Color.WHITE
            move_value = node.get_raw_property_map()['W']
            assert len(move_value) == 1
            move_value = move_value[0].decode("utf-8")
            move_info = (color, move_value)

        if move_info:
            color, move_value = move_info
            vertex = gtpmatch.sgf_point_to_gtp_vertex(move_value, board_size)

            # Skip pass move for forced openings
            if vertex != "pass":
                current_sequence.append(gtpmatch.Move(color, vertex))

        # Add to openings based on leaves_only setting
        if not leaves_only or is_leaf:
            openings.append(list(current_sequence))

        for child in node:
            traverse_tree(child, list(current_sequence))

    # Start traversal from the root
    root = sgf_game.get_root()
    traverse_tree(root, [])

    return openings
