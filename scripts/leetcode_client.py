import requests

# Leetcode "API" URL
LEETCODE_URL = "https://leetcode.com/graphql/"

def get_daily_challenge():
    # Asssigning request into variable for daily challenge infos: {date, url}
    query = """
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

    # Simulating browser access
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    # Getting the response after requesting through POST
    try:
        response = requests.post(LEETCODE_URL, json={"query": query}, headers=headers)
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch challenge: no connection to LeetCode ({e})")

    # Treatment for connection fail
    if response.status_code != 200:
        raise Exception(f"Failed to fetch challenge: LeetCode responded {response.status_code}")
    

    # Organizing the data so we can use it later.
    # Missing/null/empty are different observations: preserve absence with
    # warnings instead of crashing with KeyError (partial failure is not
    # total failure). Only questionFrontendId blocks the run (identity).
    _MISSING = object()
    warnings = []

    try:
        payload = response.json()
    except ValueError:
        raise Exception("Failed to fetch challenge: response is not valid JSON")

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise Exception("Failed to fetch challenge: response missing 'data' (layout changed?)")

    raw_data = data.get("activeDailyCodingChallengeQuestion")
    if raw_data is None:
        raise Exception("Failed to fetch challenge: response missing 'activeDailyCodingChallengeQuestion' (layout changed?)")
    if not isinstance(raw_data, dict):
        raise Exception("Failed to fetch challenge: 'activeDailyCodingChallengeQuestion' in unexpected format")

    question_info = raw_data.get("question")
    if question_info is None:
        raise Exception("Failed to fetch challenge: response missing 'question' (layout changed?)")
    if not isinstance(question_info, dict):
        raise Exception("Failed to fetch challenge: 'question' in unexpected format")

    # Context for a possible identity failure (all optional, best effort).
    tmp_title = question_info.get("title")
    tmp_slug = question_info.get("titleSlug")
    tmp_date = raw_data.get("date")
    tmp_link = raw_data.get("link")

    # Identity: questionFrontendId is mandatory. Without it there is no
    # valid problem record, so stop this problem with context to investigate.
    question_id = question_info.get("questionFrontendId")
    if question_id is None or (isinstance(question_id, str) and not question_id.strip()):
        raise Exception(
            "Challenge without ID (questionFrontendId missing). Skipping save. "
            f"Seen: title={tmp_title!r} slug={tmp_slug!r} date={tmp_date!r} link={tmp_link!r}"
        )

    # Optional scalar fields: absent/null/empty become warnings, run continues.
    for field in ("title", "titleSlug", "difficulty", "content"):
        if field not in question_info:
            warnings.append(f"Warning: field '{field}' missing in response — continued anyway")
        elif question_info.get(field) is None:
            warnings.append(f"Warning: field '{field}' was null — continued anyway")

    for field in ("date", "link"):
        if field not in raw_data:
            warnings.append(f"Warning: field '{field}' missing in response — continued anyway")
        elif raw_data.get(field) is None:
            warnings.append(f"Warning: field '{field}' was null — continued anyway")

    # We will always use python, so we just need Python3.
    python_snippet = ""
    raw_snippets = question_info.get("codeSnippets", _MISSING)
    if raw_snippets is _MISSING:
        warnings.append("Warning: field 'codeSnippets' missing in response — continued without starter code")
    elif raw_snippets is None:
        warnings.append("Warning: field 'codeSnippets' was null — continued without starter code")
    elif not isinstance(raw_snippets, list):
        warnings.append("Warning: field 'codeSnippets' in unexpected format — continued without starter code")
    else:
        for snippet in raw_snippets:
            if not isinstance(snippet, dict):
                warnings.append("Warning: 'codeSnippets' item in unexpected format — skipped the item")
                continue
            if snippet.get("lang") == "Python3":
                code = snippet.get("code")
                if isinstance(code, str):
                    python_snippet = code
                else:
                    warnings.append("Warning: Python3 snippet without valid 'code' — continued without starter code")
                break
    
    # We will extract topics in a string list, later those will be used for organizing the files.
    # Missing/null/empty topics do not block: file generation falls back to "general".
    topics = []
    raw_tags = question_info.get("topicTags", _MISSING)
    if raw_tags is _MISSING:
        warnings.append("Warning: field 'topicTags' missing in response — fell back to 'general' folder")
    elif raw_tags is None:
        warnings.append("Warning: field 'topicTags' was null — fell back to 'general' folder")
    elif not isinstance(raw_tags, list):
        warnings.append("Warning: field 'topicTags' in unexpected format — fell back to 'general' folder")
    elif len(raw_tags) == 0:
        warnings.append("Warning: 'topicTags' came back empty [] — fell back to 'general' folder")
    else:
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

    # Challenge-level optional fields. Link is derived; never fabricate it.
    challenge_date = raw_data.get("date")
    raw_link = raw_data.get("link")
    if isinstance(raw_link, str) and raw_link.strip():
        full_link = f"https://leetcode.com{raw_link}"
    else:
        full_link = None
        if raw_link is not None and (not isinstance(raw_link, str) or raw_link.strip()):
            warnings.append("Warning: field 'link' in unexpected format — continued without link")

    # This will be the base for the structure in the python file our script will generate
    formatted_data = {
        "id": question_id,
        "date": challenge_date,
        "title": question_info.get("title"),
        "slug": question_info.get("titleSlug"),
        "link": full_link,
        "difficulty": question_info.get("difficulty"),
        "content": question_info.get("content"),
        "topics": topics,
        "code_snippet": python_snippet,
        "warnings": warnings,
    }

    return formatted_data

