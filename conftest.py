"""Shared test setup.

Makes the project importable and provides temporary paths, so a test never
writes to the real output folder, to the real database or to the real
topic catalog.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SAMPLE_CONTENT = """
<p>You are given a string <code>s</code> consisting of lowercase English letters.</p>
<p><strong class="example">Example 1:</strong></p>
<div class="example-block">
<p><strong>Input:</strong> <span class="example-io">s = &quot;dog&quot;</span></p>
<p><strong>Output:</strong> <span class="example-io">1</span></p>
</div>
<p><strong class="example">Example 2:</strong></p>
<div class="example-block">
<p><strong>Input:</strong> <span class="example-io">s = &quot;card&quot;</span></p>
<p><strong>Output:</strong> <span class="example-io">2</span></p>
</div>
<p><strong>Constraints:</strong></p>
<ul><li><code>1 &lt;= s.length &lt;= 10<sup>5</sup></code></li></ul>
"""


@pytest.fixture
def temp_output_dir(tmp_path, monkeypatch):
    """Redirect the generated files to a temporary folder."""
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(output))
    return output


@pytest.fixture
def temp_db_path(tmp_path, monkeypatch):
    """Redirect the database to a temporary file."""
    database = tmp_path / "history.db"
    monkeypatch.setenv("LEETCODE_DB_PATH", str(database))
    return database


@pytest.fixture
def temp_catalog(tmp_path, monkeypatch):
    """Redirect the topic catalog to a temporary file."""
    import scripts.topics as topics_module

    catalog = tmp_path / "topics.json"
    monkeypatch.setattr(topics_module, "CATALOG_PATH", catalog)
    return catalog


@pytest.fixture
def sample_challenge():
    """A collected challenge, shaped like the real payload."""
    return {
        "id": "3863",
        "date": "2026-10-21",
        "title": "Minimum Operations to Sort a String",
        "slug": "minimum-operations-to-sort-a-string",
        "link": "https://leetcode.com/problems/minimum-operations-to-sort-a-string/",
        "difficulty": "Medium",
        "content": SAMPLE_CONTENT,
        "topics": ["String"],
        "code_snippet": "class Solution:\n    def minOperations(self, s: str) -> int:\n        ",
        "warnings": [],
    }


@pytest.fixture
def sample_payload():
    """A GraphQL payload shaped like the real LeetCode response."""
    return {
        "data": {
            "activeDailyCodingChallengeQuestion": {
                "date": "2026-10-21",
                "link": "/problems/minimum-operations-to-sort-a-string/",
                "question": {
                    "questionFrontendId": "3863",
                    "title": "Minimum Operations to Sort a String",
                    "titleSlug": "minimum-operations-to-sort-a-string",
                    "difficulty": "Medium",
                    "content": SAMPLE_CONTENT,
                    "topicTags": [{"name": "String"}],
                    "codeSnippets": [
                        {"lang": "Python3", "code": "class Solution:\n    def minOperations(self, s: str) -> int:\n        "}
                    ],
                },
            }
        }
    }
