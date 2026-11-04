"""Transport layer: GraphQL requests to LeetCode.

This module only talks to LeetCode. The interpretation of the response
lives in `collection.py`, which is pure and testable.
"""

import time
from datetime import date

import requests

from scripts.collection import CollectionError, parse_challenge, parse_question

# Leetcode "API" URL
LEETCODE_URL = "https://leetcode.com/graphql/"

# A single transient failure should not lose the day's challenge.
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

DAILY_CHALLENGE_QUERY = """
query questionOfToday {
    activeDailyCodingChallengeQuestion {
        date
        link
        question {
            questionFrontendId
            title
            titleSlug
            difficulty
            content
            topicTags {
                name
            }
            codeSnippets {
                lang
                code
            }
        }
    }
}
"""

DAILY_CHALLENGE_LIST_QUERY = """
query dailyCodingChallengeV2($year: Int!, $month: Int!) {
    dailyCodingChallengeV2(year: $year, month: $month) {
        challenges {
            date
            link
            question {
                questionFrontendId
                title
                titleSlug
                difficulty
            }
        }
    }
}
"""

QUESTION_DETAIL_QUERY = """
query questionData($titleSlug: String!) {
    question(titleSlug: $titleSlug) {
        questionFrontendId
        title
        titleSlug
        difficulty
        content
        topicTags {
            name
        }
        codeSnippets {
            lang
            code
        }
    }
}
"""


def _headers() -> dict:
    """Headers that make the request look like a browser, not a bot."""
    return {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://leetcode.com",
        "Referer": "https://leetcode.com/",
    }


def _raise_for_graphql_errors(payload: dict) -> None:
    """LeetCode often reports failures inside a 200 response."""
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return

    messages = []
    for error in errors:
        if isinstance(error, dict):
            messages.append(str(error.get("message") or error))
        else:
            messages.append(str(error))
    raise CollectionError(f"LeetCode returned an error: {'; '.join(messages)}")


def fetch_graphql(query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL query and return the decoded payload.

    Connection errors, 429/5xx responses and timeouts are retried with a
    linear backoff. Other 4xx responses fail immediately: retrying a bad
    request only wastes the scheduler's time.
    """
    body = {"query": query}
    if variables is not None:
        body["variables"] = variables

    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                LEETCODE_URL,
                json=body,
                headers=_headers(),
                timeout=30,
            )
        except requests.RequestException as e:
            last_error = f"no connection to LeetCode ({e})"
        else:
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    raise CollectionError("Failed to fetch challenge: response is not valid JSON")
                if not isinstance(payload, dict):
                    raise CollectionError("Failed to fetch challenge: response is not valid JSON")
                _raise_for_graphql_errors(payload)
                return payload

            last_error = f"LeetCode responded {response.status_code}"
            if response.status_code not in RETRYABLE_STATUS:
                raise CollectionError(f"Failed to fetch challenge: {last_error}")

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise CollectionError(
        f"Failed to fetch challenge after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def fetch_challenge_payload(query: str = DAILY_CHALLENGE_QUERY) -> dict:
    """Backwards-compatible helper for the original daily query."""
    return fetch_graphql(query)


def get_daily_challenge() -> dict:
    """Fetch and interpret today's Daily Challenge.

    Returns the internal challenge mapping with a `warnings` list.
    Raises CollectionError when the response is unusable or the problem
    identity is missing.
    """
    return parse_challenge(fetch_graphql(DAILY_CHALLENGE_QUERY))


def list_daily_challenges(year: int, month: int) -> list[dict]:
    """Return the daily challenge records published for one month.

    Each record has `date`, `link` and a basic `question` mapping. The full
    statement, topic tags and starter code are fetched separately with
    `get_question_detail`, so the monthly request stays cheap.
    """
    payload = fetch_graphql(
        DAILY_CHALLENGE_LIST_QUERY,
        {"year": year, "month": month},
    )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise CollectionError("Failed to fetch challenge history: response missing 'data'")
    month_data = data.get("dailyCodingChallengeV2")
    if not isinstance(month_data, dict):
        raise CollectionError(
            "Failed to fetch challenge history: response missing 'dailyCodingChallengeV2'"
        )
    challenges = month_data.get("challenges")
    if not isinstance(challenges, list):
        raise CollectionError(
            "Failed to fetch challenge history: 'challenges' in unexpected format"
        )

    records = []
    for item in challenges:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not isinstance(item.get("date"), str) or not isinstance(question, dict):
            continue
        records.append(
            {
                "date": item.get("date"),
                "link": item.get("link"),
                "question": question,
            }
        )
    return records


def get_question_detail(title_slug: str) -> dict:
    """Fetch the full question data needed to generate a solution file."""
    payload = fetch_graphql(QUESTION_DETAIL_QUERY, {"titleSlug": title_slug})

    data = payload.get("data")
    question = data.get("question") if isinstance(data, dict) else None
    if not isinstance(question, dict):
        raise CollectionError(f"Failed to fetch challenge: no question for slug {title_slug!r}")
    return question


def get_challenge_for_record(record: dict) -> dict:
    """Fetch the full challenge for one record from the monthly history."""
    question = record.get("question") if isinstance(record, dict) else None
    title_slug = question.get("titleSlug") if isinstance(question, dict) else None
    if not isinstance(title_slug, str) or not title_slug.strip():
        raise CollectionError(
            "Failed to fetch challenge history: record without a usable titleSlug"
        )

    detail = get_question_detail(title_slug)
    occurrence = {"date": record.get("date"), "link": record.get("link")}
    return parse_question(detail, occurrence)


def get_challenge_for_date(day: str | date) -> dict:
    """Fetch one specific Daily Challenge by date (YYYY-MM-DD)."""
    if isinstance(day, str):
        try:
            day = date.fromisoformat(day)
        except ValueError:
            raise CollectionError(f"Invalid date {day!r}; expected YYYY-MM-DD")
    if not isinstance(day, date):
        raise CollectionError(f"Invalid date {day!r}; expected YYYY-MM-DD")

    for record in list_daily_challenges(day.year, day.month):
        if record.get("date") == day.isoformat():
            return get_challenge_for_record(record)

    raise CollectionError(f"No Daily Challenge found for {day.isoformat()}")
