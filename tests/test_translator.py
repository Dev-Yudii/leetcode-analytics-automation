"""Tests for the translation of LeetCode examples into Python literals."""

from scripts.translator import (
    convert_leetcode_literals,
    find_assignments,
    parse_input,
    parse_output,
)


class TestSplitting:
    def test_splits_multiple_parameters(self):
        assignments = find_assignments("nums1 = [1,2], nums2 = [3,4], k = 0")
        assert assignments == [("nums1", "[1,2]"), ("nums2", "[3,4]"), ("k", "0")]

    def test_comma_inside_a_string_does_not_split(self):
        assignments = find_assignments('s = "a,b"')
        assert assignments == [("s", '"a,b"')]

    def test_comma_inside_a_list_does_not_split(self):
        assignments = find_assignments("nums = [1,2,3]")
        assert assignments == [("nums", "[1,2,3]")]

    def test_positional_value_has_no_assignment(self):
        assert find_assignments("[1,2,3]") == []


class TestLiteralConversion:
    def test_converts_standalone_tokens(self):
        assert convert_leetcode_literals("true") == "True"
        assert convert_leetcode_literals("false") == "False"
        assert convert_leetcode_literals("null") == "None"

    def test_keeps_tokens_inside_strings(self):
        assert convert_leetcode_literals('"nullable"') == '"nullable"'
        assert convert_leetcode_literals('"true story"') == '"true story"'
        assert convert_leetcode_literals('"null"') == '"null"'

    def test_keeps_words_that_merely_contain_a_token(self):
        assert convert_leetcode_literals("nullable") == "nullable"
        assert convert_leetcode_literals("untrue") == "untrue"


class TestParseInput:
    def test_parses_named_parameters(self):
        parsed = parse_input("nums = [1,2,3], target = 2")
        assert parsed.ok is True
        assert parsed.parameters == {"nums": [1, 2, 3], "target": 2}
        assert parsed.literal == "{'nums': [1, 2, 3], 'target': 2}"

    def test_keeps_a_comma_inside_a_string(self):
        parsed = parse_input('s = "a,b"')
        assert parsed.ok is True
        assert parsed.parameters == {"s": "a,b"}

    def test_keeps_a_word_inside_a_string(self):
        parsed = parse_input('word = "nullable"')
        assert parsed.ok is True
        assert parsed.parameters == {"word": "nullable"}

    def test_converts_null_inside_a_list(self):
        parsed = parse_input("head = [1,null,2]")
        assert parsed.ok is True
        assert parsed.parameters == {"head": [1, None, 2]}

    def test_parses_a_dict_value(self):
        parsed = parse_input('graph = {"a":1,"b":2}')
        assert parsed.ok is True
        assert parsed.parameters == {"graph": {"a": 1, "b": 2}}

    def test_parses_a_positional_value(self):
        parsed = parse_input("[1,2,3]")
        assert parsed.ok is True
        assert parsed.positional is True
        assert parsed.value == [1, 2, 3]

    def test_parses_a_thousand_separated_number(self):
        parsed = parse_input("n = 1,000,000")
        assert parsed.ok is True
        assert parsed.parameters == {"n": 1000000}

    def test_unparseable_input_is_reported(self):
        parsed = parse_input("s = a + b")
        assert parsed.ok is False
        assert parsed.parameters == {}

    def test_empty_input_is_not_parsed(self):
        parsed = parse_input("")
        assert parsed.ok is False


class TestParseOutput:
    def test_parses_a_number(self):
        assert parse_output("3") == (3, True)

    def test_parses_a_boolean(self):
        assert parse_output("true") == (True, True)

    def test_parses_a_list_of_strings(self):
        value, ok = parse_output('["(())","()()"]')
        assert ok is True
        assert value == ["(())", "()()"]

    def test_thousand_separated_number_is_not_a_tuple(self):
        assert parse_output("1,000") == (1000, True)

    def test_plain_text_is_not_a_literal(self):
        value, ok = parse_output("Hello")
        assert ok is False
        assert value is None
