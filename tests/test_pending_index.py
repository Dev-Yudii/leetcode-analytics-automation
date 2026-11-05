"""Tests for the index of the open challenges."""

from datetime import date

from scripts.pending_index import (
    PENDING_FILE,
    render_pending_index,
    write_pending_index,
)


def make_row(**overrides):
    row = {
        "id": "1385",
        "title": "Find the Distance Value Between Two Arrays",
        "difficulty": "Easy",
        "challenge_date": date(2026, 11, 5),
        "file_path": "array/1385_find-the-distance-value-between-two-arrays.py",
        "topics": "Array, Sorting",
    }
    row.update(overrides)
    return row


class TestRender:
    def test_the_header_says_it_is_generated(self):
        content = render_pending_index([make_row()])
        assert "# Open challenges" in content
        assert "do not edit by hand" in content

    def test_the_row_carries_the_essentials(self):
        content = render_pending_index([make_row()])
        assert "2026-11-05" in content
        assert "1385" in content
        assert "Find the Distance Value Between Two Arrays" in content
        assert "Easy" in content
        assert "Array, Sorting" in content

    def test_the_file_is_a_link(self):
        content = render_pending_index([make_row()])
        assert (
            "[array/1385_find-the-distance-value-between-two-arrays.py]"
            "(array/1385_find-the-distance-value-between-two-arrays.py)"
        ) in content

    def test_an_empty_list_says_there_is_nothing_open(self):
        content = render_pending_index([])
        assert "Nothing open right now." in content

    def test_the_waiting_label_counts_the_days(self):
        rows = [make_row(challenge_date=date(2026, 11, 5))]
        content = render_pending_index(rows, today=date(2026, 11, 6))
        assert "1 day" in content

    def test_a_challenge_of_today_is_labelled_today(self):
        rows = [make_row(challenge_date=date(2026, 11, 5))]
        content = render_pending_index(rows, today=date(2026, 11, 5))
        assert "| today |" in content

    def test_a_missing_file_is_reported(self, tmp_path):
        rows = [make_row()]
        content = render_pending_index(rows, root=tmp_path)
        assert "not collected yet" in content

    def test_the_challenge_the_cloud_has_not_collected_is_reported(self):
        content = render_pending_index([], missing_today="#4242 — Tomorrow")
        assert "not collected yet" in content
        assert "4242" in content


class TestWrite:
    def test_the_file_is_created(self, tmp_path):
        content = render_pending_index([make_row()])
        assert write_pending_index(tmp_path, content) is True
        assert (tmp_path / PENDING_FILE).read_text(encoding="utf-8") == content

    def test_the_same_content_is_not_written_again(self, tmp_path):
        content = render_pending_index([make_row()])
        write_pending_index(tmp_path, content)
        assert write_pending_index(tmp_path, content) is False

    def test_a_different_content_is_written(self, tmp_path):
        write_pending_index(tmp_path, render_pending_index([make_row()]))
        assert write_pending_index(tmp_path, render_pending_index([])) is True
