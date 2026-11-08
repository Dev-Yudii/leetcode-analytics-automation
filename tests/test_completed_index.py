"""Tests for the index of the completed challenges.

The index links to where the solution file really is: a solved file
leaves the working tree, so the relative path would point to nothing in
the local clone.
"""

from datetime import date, datetime, timedelta, timezone

from scripts.completed_index import (
    COMPLETED_FILE,
    _parse_remote,
    _format_resolution,
    _format_solved_date,
    render_completed_index,
    write_completed_index,
)

BRT = timezone(timedelta(hours=-3))


def make_row(**overrides):
    row = {
        "id": "1385",
        "title": "Find the Distance Value Between Two Arrays",
        "difficulty": "Easy",
        "challenge_date": date(2026, 11, 5),
        "file_path": "array/1385_find-the-distance-value-between-two-arrays.py",
        "topics": "Array, Sorting",
        "solved_at": datetime(2026, 11, 5, 21, 26, 54, tzinfo=timezone.utc),
        "resolution_hours": 341 / 3600,
    }
    row.update(overrides)
    return row


class TestRender:
    def test_the_header_says_it_is_generated(self):
        content = render_completed_index([make_row()])
        assert "# Completed challenges" in content
        assert "do not edit by hand" in content

    def test_the_row_carries_the_essentials(self):
        content = render_completed_index([make_row()])

        assert "2026-11-05" in content
        assert "1385" in content
        assert "Find the Distance Value Between Two Arrays" in content
        assert "Easy" in content
        assert "Array, Sorting" in content

    def test_the_challenge_date_is_a_column_of_its_own(self):
        row = make_row(
            challenge_date=date(2026, 11, 5),
            solved_at=datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc),
        )
        content = render_completed_index([row])

        header = [line for line in content.splitlines() if line.startswith("| Challenge")]
        assert "Challenge" in header[0]
        assert "Solved" in header[0]

    def test_the_resolution_time_is_shown(self):
        content = render_completed_index([make_row()])
        assert "5m 41s" in content

    def test_the_repository_is_shown(self):
        content = render_completed_index(
            [make_row()],
            repository="Dev-Yudii/leetcode",
            repository_url="https://github.com/Dev-Yudii/leetcode",
        )
        assert "Dev-Yudii/leetcode" in content

    def test_the_file_link_is_absolute(self):
        content = render_completed_index(
            [make_row()],
            repository="Dev-Yudii/leetcode",
            repository_url="https://github.com/Dev-Yudii/leetcode",
        )

        assert (
            "https://github.com/Dev-Yudii/leetcode/blob/main/"
            "array/1385_find-the-distance-value-between-two-arrays.py"
        ) in content

    def test_without_a_repository_the_file_is_not_a_broken_link(self):
        content = render_completed_index([make_row()])

        assert "](https://" not in content
        assert "array/1385_find-the-distance-value-between-two-arrays.py" in content

    def test_an_empty_list_says_there_is_nothing_completed(self):
        content = render_completed_index([])

        assert "Nothing completed yet." in content
        assert "PENDING.md" in content

    def test_the_two_indexes_point_at_each_other(self):
        content = render_completed_index([make_row()])
        assert "[PENDING.md](PENDING.md)" in content

    def test_the_count_is_reported(self):
        content = render_completed_index([make_row(), make_row(id="1400")])
        assert "2 challenge(s) completed" in content


class TestResolution:
    def test_seconds(self):
        assert _format_resolution(0.005) == "18s"

    def test_minutes_and_seconds(self):
        assert _format_resolution(341 / 3600) == "5m 41s"

    def test_hours(self):
        assert _format_resolution(2.3) == "2.3 h"

    def test_days(self):
        assert _format_resolution(3 * 24) == "3 days"

    def test_many_days_are_whole(self):
        assert _format_resolution(20 * 24) == "20 days"

    def test_nothing_is_nothing(self):
        assert _format_resolution(None) == ""


class TestSolvedDate:
    def test_it_uses_the_local_time_of_the_reader(self):
        # 21:26 UTC is 18:26 in BRT — the same day.
        value = datetime(2026, 11, 5, 21, 26, 54, tzinfo=timezone.utc)
        assert _format_solved_date(value, tz=BRT) == "2026-11-05"

    def test_a_late_night_stays_on_the_day_it_was_solved(self):
        # 00:30 UTC on the 6th is 21:30 on the 5th, in BRT.
        value = datetime(2026, 11, 6, 0, 30, 0, tzinfo=timezone.utc)
        assert _format_solved_date(value, tz=BRT) == "2026-11-05"

    def test_a_missing_value_says_unknown(self):
        assert _format_solved_date(None, tz=BRT) == "unknown"


class TestParseRemote:
    def test_an_https_remote(self):
        slug, url = _parse_remote("https://github.com/Dev-Yudii/leetcode.git")
        assert slug == "Dev-Yudii/leetcode"
        assert url == "https://github.com/Dev-Yudii/leetcode"

    def test_an_ssh_remote(self):
        slug, url = _parse_remote("git@github.com:Dev-Yudii/leetcode.git")
        assert slug == "Dev-Yudii/leetcode"
        assert url == "https://github.com/Dev-Yudii/leetcode"

    def test_a_remote_without_the_suffix(self):
        slug, url = _parse_remote("https://github.com/Dev-Yudii/leetcode")
        assert slug == "Dev-Yudii/leetcode"
        assert url == "https://github.com/Dev-Yudii/leetcode"

    def test_an_empty_remote(self):
        assert _parse_remote("") == ("", "")


class TestWrite:
    def test_the_file_is_created(self, tmp_path):
        content = render_completed_index([make_row()])

        assert write_completed_index(tmp_path, content) is True
        assert (tmp_path / COMPLETED_FILE).read_text(encoding="utf-8") == content

    def test_the_same_content_is_not_written_again(self, tmp_path):
        content = render_completed_index([make_row()])
        write_completed_index(tmp_path, content)

        assert write_completed_index(tmp_path, content) is False

    def test_a_different_content_is_written(self, tmp_path):
        write_completed_index(tmp_path, render_completed_index([make_row()]))

        assert write_completed_index(tmp_path, render_completed_index([])) is True
