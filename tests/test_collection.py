"""Tests for the interpretation of the LeetCode response."""

import copy

import pytest

from scripts.collection import CollectionError, parse_challenge


class TestValidPayload:
    def test_reads_every_field(self, sample_payload):
        data = parse_challenge(sample_payload)
        assert data["id"] == "3863"
        assert data["title"] == "Minimum Operations to Sort a String"
        assert data["slug"] == "minimum-operations-to-sort-a-string"
        assert data["difficulty"] == "Medium"
        assert data["date"] == "2026-10-21"
        assert data["link"] == "https://leetcode.com/problems/minimum-operations-to-sort-a-string/"
        assert data["topics"] == ["String"]
        assert "def minOperations" in data["code_snippet"]
        assert data["warnings"] == []


class TestIdentity:
    def test_missing_id_is_fatal(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        del payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["questionFrontendId"]
        with pytest.raises(CollectionError, match="questionFrontendId missing"):
            parse_challenge(payload)

    def test_empty_id_is_fatal(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["questionFrontendId"] = "  "
        with pytest.raises(CollectionError, match="questionFrontendId missing"):
            parse_challenge(payload)

    def test_missing_identity_keeps_the_context(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        del payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["questionFrontendId"]
        with pytest.raises(CollectionError) as error:
            parse_challenge(payload)
        assert "Minimum Operations to Sort a String" in str(error.value)


class TestBrokenPayload:
    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"data": None},
            {"data": {}},
            {"data": {"activeDailyCodingChallengeQuestion": None}},
            {"data": {"activeDailyCodingChallengeQuestion": "text"}},
            {"data": {"activeDailyCodingChallengeQuestion": {"question": None}}},
            {"data": {"activeDailyCodingChallengeQuestion": {"question": "text"}}},
        ],
    )
    def test_unusable_payload_is_fatal(self, payload):
        with pytest.raises(CollectionError):
            parse_challenge(payload)


class TestWarnings:
    def test_missing_field_warns_and_continues(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        del payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["title"]
        data = parse_challenge(payload)
        assert any("'title' missing" in warning for warning in data["warnings"])
        assert data["id"] == "3863"

    def test_null_field_warns_and_continues(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["difficulty"] = None
        data = parse_challenge(payload)
        assert any("'difficulty' was null" in warning for warning in data["warnings"])

    def test_empty_topic_list_warns(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        payload["data"]["activeDailyCodingQuestion"] = None
        payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["topicTags"] = []
        data = parse_challenge(payload)
        assert any("empty []" in warning for warning in data["warnings"])
        assert data["topics"] == []

    def test_missing_topic_tags_warns(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        del payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["topicTags"]
        data = parse_challenge(payload)
        assert any("'topicTags' missing" in warning for warning in data["warnings"])
        assert data["topics"] == []

    def test_missing_code_snippets_warns(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        del payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["codeSnippets"]
        data = parse_challenge(payload)
        assert any("'codeSnippets' missing" in warning for warning in data["warnings"])
        assert data["code_snippet"] == ""

    def test_topic_without_name_is_skipped(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        payload["data"]["activeDailyCodingChallengeQuestion"]["question"]["topicTags"] = [
            {"name": "String"},
            {},
        ]
        data = parse_challenge(payload)
        assert data["topics"] == ["String"]
        assert any("without 'name'" in warning for warning in data["warnings"])


class TestDerivedLink:
    def test_link_is_built_from_the_relative_path(self, sample_payload):
        data = parse_challenge(sample_payload)
        assert data["link"].startswith("https://leetcode.com/")

    def test_missing_link_is_not_invented(self, sample_payload):
        payload = copy.deepcopy(sample_payload)
        payload["data"]["activeDailyCodingChallengeQuestion"]["link"] = None
        data = parse_challenge(payload)
        assert data["link"] is None
