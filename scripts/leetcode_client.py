"""Transport layer: one GraphQL request to LeetCode per day.

This module only talks to LeetCode. The interpretation of the response
lives in `collection.py`, which is pure and testable.
"""

import requests

from scripts.collection import CollectionError, parse_challenge

# Leetcode "API" URL
LEETCODE_URL = "https://leetcode.com/graphql/"

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


def fetch_challenge_payload(query: str = DAILY_CHALLENGE_QUERY) -> dict:
    """POST the daily challenge query and return the decoded payload.

    Raises CollectionError when the request cannot be completed or the
    response is not usable JSON.
    """
    # Simulating browser access
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.post(LEETCODE_URL, json={"query": query}, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise CollectionError(f"Failed to fetch challenge: no connection to LeetCode ({e})")

    if response.status_code != 200:
        raise CollectionError(f"Failed to fetch challenge: LeetCode responded {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        raise CollectionError("Failed to fetch challenge: response is not valid JSON")

    return payload


def get_daily_challenge() -> dict:
    """Fetch and interpret today's Daily Challenge.

    Returns the internal challenge mapping with a `warnings` list.
    Raises CollectionError when the response is unusable or the problem
    identity is missing.
    """
    return parse_challenge(fetch_challenge_payload())
