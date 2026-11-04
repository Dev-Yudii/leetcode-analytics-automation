"""Interpretation of the LeetCode GraphQL response.

This module is pure: it takes a decoded payload and returns the internal
representation of the challenge, with the collection warnings attached.
Keeping it free of network calls makes the validation rules testable.

The rules come from docs/architecture.md:
    * missing, null and empty are different observations (section 5);
    * only a missing problem identity blocks the run (section 3.1);
    * partial failure is not total failure (section 2.2).
"""

_MISSING = object()


class CollectionError(Exception):
    """The response cannot be turned into a valid problem.

    Raised when the payload has no usable structure or when the problem
    identity (`questionFrontendId`) is missing. Both are fatal for the run.
    """


def parse_challenge(payload) -> dict:
    """Turn a decoded GraphQL payload into the internal challenge mapping.

    Returns a dict with the problem fields plus a `warnings` list. Raises
    CollectionError when the payload is unusable or the identity is missing.
    """
    if not isinstance(payload, dict):
        raise CollectionError("Failed to fetch challenge: response missing 'data' (layout changed?)")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise CollectionError("Failed to fetch challenge: response missing 'data' (layout changed?)")

    raw_data = data.get("activeDailyCodingChallengeQuestion")
    if raw_data is None:
        raise CollectionError(
            "Failed to fetch challenge: response missing 'activeDailyCodingChallengeQuestion' (layout changed?)"
        )
    if not isinstance(raw_data, dict):
        raise CollectionError(
            "Failed to fetch challenge: 'activeDailyCodingChallengeQuestion' in unexpected format"
        )

    return parse_question(raw_data.get("question"), raw_data)


def parse_question(question_info, occurrence: dict) -> dict:
    """Interpret a question plus the daily occurrence that points to it.

    `occurrence` is the source object that carries `date` and `link` (the
    `activeDailyCodingChallengeQuestion` object for today's query, or a record
    from the monthly history query). Keeping this separate from the payload
    layout lets the backfill reuse the exact same validation rules.
    """
    if question_info is None:
        raise CollectionError("Failed to fetch challenge: response missing 'question' (layout changed?)")
    if not isinstance(question_info, dict):
        raise CollectionError("Failed to fetch challenge: 'question' in unexpected format")

    if occurrence is None:
        occurrence = {}
    if not isinstance(occurrence, dict):
        raise CollectionError(
            "Failed to fetch challenge: 'activeDailyCodingChallengeQuestion' in unexpected format"
        )

    warnings = []

    # Identity: questionFrontendId is mandatory. Without it there is no
    # valid problem record, so stop this problem with context to investigate.
    question_id = question_info.get("questionFrontendId")
    if question_id is None or (isinstance(question_id, str) and not question_id.strip()):
        raise CollectionError(
            "Challenge without ID (questionFrontendId missing). Skipping save. "
            f"Seen: title={question_info.get('title')!r} slug={question_info.get('titleSlug')!r} "
            f"date={occurrence.get('date')!r} link={occurrence.get('link')!r}"
        )

    # Optional scalar fields: absent/null become warnings, the run continues.
    for field in ("title", "titleSlug", "difficulty", "content"):
        if field not in question_info:
            warnings.append(f"Warning: field '{field}' missing in response — continued anyway")
        elif question_info.get(field) is None:
            warnings.append(f"Warning: field '{field}' was null — continued anyway")

    for field in ("date", "link"):
        if field not in occurrence:
            warnings.append(f"Warning: field '{field}' missing in response — continued anyway")
        elif occurrence.get(field) is None:
            warnings.append(f"Warning: field '{field}' was null — continued anyway")

    python_snippet = _extract_python_snippet(question_info, warnings)
    topics = _extract_topics(question_info, warnings)

    # Link is derived; never fabricate it.
    raw_link = occurrence.get("link")
    if isinstance(raw_link, str) and raw_link.strip():
        full_link = f"https://leetcode.com{raw_link}"
    else:
        full_link = None
        if raw_link is not None and (not isinstance(raw_link, str) or raw_link.strip()):
            warnings.append("Warning: field 'link' in unexpected format — continued without link")

    return {
        "id": question_id,
        "date": occurrence.get("date"),
        "title": question_info.get("title"),
        "slug": question_info.get("titleSlug"),
        "link": full_link,
        "difficulty": question_info.get("difficulty"),
        "content": question_info.get("content"),
        "topics": topics,
        "code_snippet": python_snippet,
        "warnings": warnings,
    }


def _extract_python_snippet(question_info: dict, warnings: list) -> str:
    """Return the Python3 starter code, or an empty string with a warning."""
    raw_snippets = question_info.get("codeSnippets", _MISSING)
    if raw_snippets is _MISSING:
        warnings.append("Warning: field 'codeSnippets' missing in response — continued without starter code")
        return ""
    if raw_snippets is None:
        warnings.append("Warning: field 'codeSnippets' was null — continued without starter code")
        return ""
    if not isinstance(raw_snippets, list):
        warnings.append("Warning: field 'codeSnippets' in unexpected format — continued without starter code")
        return ""

    for snippet in raw_snippets:
        if not isinstance(snippet, dict):
            warnings.append("Warning: 'codeSnippets' item in unexpected format — skipped the item")
            continue
        if snippet.get("lang") == "Python3":
            code = snippet.get("code")
            if isinstance(code, str):
                return code
            warnings.append("Warning: Python3 snippet without valid 'code' — continued without starter code")
            break
    return ""


def _extract_topics(question_info: dict, warnings: list) -> list:
    """Return the topic names, or an empty list with a warning."""
    raw_tags = question_info.get("topicTags", _MISSING)
    if raw_tags is _MISSING:
        warnings.append("Warning: field 'topicTags' missing in response — fell back to 'general' folder")
        return []
    if raw_tags is None:
        warnings.append("Warning: field 'topicTags' was null — fell back to 'general' folder")
        return []
    if not isinstance(raw_tags, list):
        warnings.append("Warning: field 'topicTags' in unexpected format — fell back to 'general' folder")
        return []
    if len(raw_tags) == 0:
        warnings.append("Warning: 'topicTags' came back empty [] — fell back to 'general' folder")
        return []

    topics = []
    for tag in raw_tags:
        if not isinstance(tag, dict):
            warnings.append("Warning: 'topicTags' item in unexpected format — skipped the item")
            continue
        name = tag.get("name")
        if name is None:
            warnings.append("Warning: topic without 'name' (null) — skipped the item")
            continue
        if not isinstance(name, str):
            warnings.append("Warning: topic with 'name' in unexpected format — skipped the item")
            continue
        if not name.strip():
            warnings.append("Warning: topic with empty name — skipped the item")
            continue
        topics.append(name)
    return topics
