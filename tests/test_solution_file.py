"""Tests for the convention that marks a solution file as solved."""

from scripts.solution_file import (
    SOLVED_MARKER,
    is_solved,
    problem_id_from_path,
)


class TestSolvedMarker:
    def test_matches_the_plain_marker(self):
        assert SOLVED_MARKER.search("# Solved")

    def test_matches_without_a_space(self):
        assert SOLVED_MARKER.search("#solved")

    def test_matches_the_dashed_marker(self):
        assert SOLVED_MARKER.search("# --solved")

    def test_ignores_the_case(self):
        assert SOLVED_MARKER.search("# SOLVED")

    def test_needs_a_line_of_its_own(self):
        assert not SOLVED_MARKER.search("# this one is solved")

    def test_does_not_match_a_negative_sentence(self):
        assert not SOLVED_MARKER.search("# not solved yet")

    def test_does_not_match_the_instruction(self):
        assert not SOLVED_MARKER.search(
            '# Add a line reading "# Solved" below when you finish the solution.'
        )


class TestIsSolved:
    def test_a_file_without_the_marker_is_open(self, tmp_path):
        path = tmp_path / "3863_minimum-operations.py"
        path.write_text("class Solution:\n    pass\n", encoding="utf-8")
        assert not is_solved(path)

    def test_a_file_with_the_marker_is_solved(self, tmp_path):
        path = tmp_path / "3863_minimum-operations.py"
        path.write_text("class Solution:\n    pass\n# Solved\n", encoding="utf-8")
        assert is_solved(path)

    def test_the_solution_code_alone_does_not_solve_it(self, tmp_path):
        path = tmp_path / "3863_minimum-operations.py"
        path.write_text(
            "class Solution:\n    def solve(self):\n        return 42\n",
            encoding="utf-8",
        )
        assert not is_solved(path)

    def test_a_missing_file_is_not_solved(self, tmp_path):
        assert not is_solved(tmp_path / "does-not-exist.py")


class TestProblemIdFromPath:
    def test_reads_the_id_from_the_file_name(self):
        assert problem_id_from_path("string/3863_minimum-operations.py") == "3863"

    def test_returns_none_without_a_leading_number(self):
        assert problem_id_from_path("string/minimum-operations.py") is None
