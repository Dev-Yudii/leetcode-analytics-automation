"""Tests for the generation of the solution file."""

from scripts.generator import (
    clean_html,
    determine_file_path,
    extract_inputs,
    generate_daily_file,
    relative_file_path,
)


class TestCleanHtml:
    def test_removes_tags_and_decodes_entities(self):
        cleaned = clean_html('<p><strong>Input:</strong> s = &quot;dog&quot;</p>')
        assert cleaned == "Input: s = \"dog\""

    def test_keeps_the_line_break_between_paragraphs(self):
        cleaned = clean_html("<p>first</p><p>second</p>")
        assert cleaned.split("\n") == ["first", "second"]

    def test_empty_content_is_empty_string(self):
        assert clean_html(None) == ""
        assert clean_html("") == ""


class TestExtractInputs:
    def test_reads_the_example_blocks(self, sample_challenge):
        assert extract_inputs(sample_challenge["content"]) == [
            ('s = "dog"', "1"),
            ('s = "card"', "2"),
        ]

    def test_ignores_an_input_mentioned_in_the_description(self):
        content = (
            "<p>Input: the array to sort</p>"
            "<p><strong>Example 1:</strong></p>"
            "<p><strong>Input:</strong> nums = [1,2]</p>"
            "<p><strong>Output:</strong> 3</p>"
        )
        assert extract_inputs(content) == [("nums = [1,2]", "3")]

    def test_falls_back_to_a_global_scan(self):
        content = "<p>Input: nums = [1,2]</p><p>Output: 3</p>"
        assert extract_inputs(content) == [("nums = [1,2]", "3")]


class TestFilePath:
    def test_first_topic_decides_the_folder(self, sample_challenge):
        assert relative_file_path(sample_challenge) == (
            "string/3863_minimum-operations-to-sort-a-string.py"
        )

    def test_without_topics_the_folder_is_general(self, sample_challenge):
        sample_challenge["topics"] = []
        assert relative_file_path(sample_challenge).startswith("general/")

    def test_path_lives_inside_the_output_folder(self, sample_challenge, temp_output_dir):
        path = determine_file_path(sample_challenge)
        assert path.parent.parent == temp_output_dir


class TestGenerateFile:
    def test_creates_the_file(self, sample_challenge, temp_output_dir):
        path = generate_daily_file(sample_challenge)
        assert (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").exists()
        assert path.endswith(".py")

    def test_writes_the_header(self, sample_challenge, temp_output_dir):
        path = generate_daily_file(sample_challenge)
        content = path and (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").read_text(encoding="utf-8")
        assert "Minimum Operations to Sort a String" in content
        assert "https://leetcode.com/problems/minimum-operations-to-sort-a-string/" in content
        assert "Notes:" in content

    def test_writes_the_parsed_tests(self, sample_challenge, temp_output_dir):
        generate_daily_file(sample_challenge)
        content = (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").read_text(encoding="utf-8")
        assert "inputs1 = {'s': 'dog'}" in content
        assert "solution.minOperations(**inputs1)" in content
        assert "exec(" not in content

    def test_never_overwrites_an_existing_file(self, sample_challenge, temp_output_dir):
        path = generate_daily_file(sample_challenge)
        target = temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py"
        target.write_text("# my solution\n", encoding="utf-8")
        generate_daily_file(sample_challenge)
        assert target.read_text(encoding="utf-8") == "# my solution\n"
        assert path

    def test_test_block_survives_a_comma_inside_a_string(self, sample_challenge, temp_output_dir):
        sample_challenge["content"] = (
            "<p><strong>Example 1:</strong></p>"
            "<p><strong>Input:</strong> s = &quot;a,b&quot;</p>"
            "<p><strong>Output:</strong> 2</p>"
        )
        generate_daily_file(sample_challenge)
        content = (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").read_text(encoding="utf-8")
        assert "inputs1 = {'s': 'a,b'}" in content

    def test_untranslatable_input_becomes_a_comment(self, sample_challenge, temp_output_dir):
        sample_challenge["content"] = (
            "<p><strong>Example 1:</strong></p>"
            "<p><strong>Input:</strong> s = a + b</p>"
            "<p><strong>Output:</strong> 2</p>"
        )
        generate_daily_file(sample_challenge)
        content = (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").read_text(encoding="utf-8")
        assert "not auto-translated" in content
        assert "exec(" not in content
