"""Tests for the GraphQL transport layer.

No test touches the network: responses and requests are replaced by fakes.
"""

import copy

import pytest

import scripts.leetcode_client as client
from scripts.collection import CollectionError


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


def monthly_payload():
    return {
        "data": {
            "dailyCodingChallengeV2": {
                "challenges": [
                    {
                        "date": "2026-10-01",
                        "link": "/problems/valid-parentheses/",
                        "question": {
                            "questionFrontendId": "20",
                            "title": "Valid Parentheses",
                            "titleSlug": "valid-parentheses",
                            "difficulty": "Easy",
                        },
                    },
                    {
                        "date": "2026-10-02",
                        "link": "/problems/generate-parentheses/",
                        "question": {
                            "questionFrontendId": "22",
                            "title": "Generate Parentheses",
                            "titleSlug": "generate-parentheses",
                            "difficulty": "Medium",
                        },
                    },
                ]
            }
        }
    }


class TestDailyChallenge:
    def test_parses_todays_challenge(self, monkeypatch, sample_payload):
        monkeypatch.setattr(client, "fetch_graphql", lambda *args, **kwargs: sample_payload)
        data = client.get_daily_challenge()
        assert data["id"] == "3863"
        assert data["date"] == "2026-10-21"


class TestMonthlyHistory:
    def test_lists_the_month_records(self, monkeypatch):
        calls = []

        def fake_fetch(query, variables=None):
            calls.append((query, variables))
            return monthly_payload()

        monkeypatch.setattr(client, "fetch_graphql", fake_fetch)
        records = client.list_daily_challenges(2026, 10)

        assert calls[0][1] == {"year": 2026, "month": 10}
        assert [record["date"] for record in records] == ["2026-10-01", "2026-10-02"]
        assert records[0]["question"]["titleSlug"] == "valid-parentheses"

    def test_skips_records_without_a_date(self, monkeypatch):
        payload = monthly_payload()
        payload["data"]["dailyCodingChallengeV2"]["challenges"].append(
            {"link": "/problems/broken/", "question": {"titleSlug": "broken"}}
        )
        monkeypatch.setattr(client, "fetch_graphql", lambda *args, **kwargs: payload)
        records = client.list_daily_challenges(2026, 10)
        assert len(records) == 2

    def test_rejects_a_broken_history_payload(self, monkeypatch):
        monkeypatch.setattr(client, "fetch_graphql", lambda *args, **kwargs: {"data": {}})
        with pytest.raises(CollectionError, match="dailyCodingChallengeV2"):
            client.list_daily_challenges(2026, 10)

    def test_gets_the_question_detail(self, monkeypatch, sample_payload):
        question = copy.deepcopy(
            sample_payload["data"]["activeDailyCodingChallengeQuestion"]["question"]
        )
        calls = []

        def fake_fetch(query, variables=None):
            calls.append(variables)
            return {"data": {"question": question}}

        monkeypatch.setattr(client, "fetch_graphql", fake_fetch)
        detail = client.get_question_detail("minimum-operations-to-sort-a-string")

        assert calls == [{"titleSlug": "minimum-operations-to-sort-a-string"}]
        assert detail["questionFrontendId"] == "3863"


class TestChallengeByRecord:
    def test_combines_detail_with_the_occurrence_date_and_link(self, monkeypatch, sample_payload):
        question = copy.deepcopy(
            sample_payload["data"]["activeDailyCodingChallengeQuestion"]["question"]
        )
        monkeypatch.setattr(client, "get_question_detail", lambda slug: question)

        record = {
            "date": "2026-10-21",
            "link": "/problems/minimum-operations-to-sort-a-string/",
            "question": {"titleSlug": "minimum-operations-to-sort-a-string"},
        }
        data = client.get_challenge_for_record(record)

        assert data["id"] == "3863"
        assert data["date"] == "2026-10-21"
        assert data["link"] == (
            "https://leetcode.com/problems/minimum-operations-to-sort-a-string/"
        )

    def test_record_without_slug_is_rejected(self):
        with pytest.raises(CollectionError, match="titleSlug"):
            client.get_challenge_for_record({"date": "2026-10-21", "question": {}})

    def test_date_lookup_rejects_an_invalid_date(self):
        with pytest.raises(CollectionError, match="Invalid date"):
            client.get_challenge_for_date("21/10/2026")

    def test_date_lookup_uses_the_month_list(self, monkeypatch, sample_payload):
        question = copy.deepcopy(
            sample_payload["data"]["activeDailyCodingChallengeQuestion"]["question"]
        )
        monkeypatch.setattr(client, "get_question_detail", lambda slug: question)
        monkeypatch.setattr(
            client,
            "list_daily_challenges",
            lambda year, month: [
                {
                    "date": "2026-10-21",
                    "link": "/problems/minimum-operations-to-sort-a-string/",
                    "question": {"titleSlug": "minimum-operations-to-sort-a-string"},
                }
            ],
        )
        data = client.get_challenge_for_date("2026-10-21")
        assert data["id"] == "3863"


class TestRetries:
    def test_retries_a_transient_failure(self, monkeypatch):
        responses = [
            FakeResponse(503),
            FakeResponse(200, {"data": {"ok": True}}),
        ]
        monkeypatch.setattr(client.requests, "post", lambda *args, **kwargs: responses.pop(0))
        monkeypatch.setattr(client.time, "sleep", lambda seconds: None)

        payload = client.fetch_graphql("query")

        assert payload == {"data": {"ok": True}}
        assert responses == []

    def test_gives_up_after_the_attempt_limit(self, monkeypatch):
        calls = []

        def fake_post(*args, **kwargs):
            calls.append(1)
            return FakeResponse(503)

        monkeypatch.setattr(client.requests, "post", fake_post)
        monkeypatch.setattr(client.time, "sleep", lambda seconds: None)

        with pytest.raises(CollectionError, match="after 3 attempts"):
            client.fetch_graphql("query")
        assert len(calls) == 3

    def test_does_not_retry_a_client_error(self, monkeypatch):
        calls = []

        def fake_post(*args, **kwargs):
            calls.append(1)
            return FakeResponse(400)

        monkeypatch.setattr(client.requests, "post", fake_post)
        monkeypatch.setattr(client.time, "sleep", lambda seconds: None)

        with pytest.raises(CollectionError, match="400"):
            client.fetch_graphql("query")
        assert len(calls) == 1

    def test_graphql_errors_inside_a_200_are_reported(self, monkeypatch):
        payload = {"errors": [{"message": "rate limited"}]}
        monkeypatch.setattr(client.requests, "post", lambda *args, **kwargs: FakeResponse(200, payload))
        monkeypatch.setattr(client.time, "sleep", lambda seconds: None)

        with pytest.raises(CollectionError, match="rate limited"):
            client.fetch_graphql("query")
