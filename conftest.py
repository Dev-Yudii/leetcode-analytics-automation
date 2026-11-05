"""Shared test setup.

Makes the project importable and provides temporary paths, so a test never
writes to the real output folder, to the real database or to the real
topic catalog.

The database tests run against a separate PostgreSQL database
(`leetcode_analytics_test`). When PostgreSQL is not reachable, those tests
are skipped instead of failing.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB_NAME = "leetcode_analytics_test"


def _database_name(url: str) -> str:
    """The database a connection string points at."""
    return urlsplit(url).path.lstrip("/")


def _url_with_database(url: str, database: str) -> str:
    """The same connection string, pointing at another database."""
    parts = urlsplit(url)
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{parts.netloc}/{database}{query}"


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


@pytest.fixture(autouse=True)
def no_backfill_floor(monkeypatch):
    """The temporary production floor must not shape the test fixtures.

    The floor is a production rule: the collected data was reset on
    2026-11-05 and the backfill must not pull anything older until the
    rule is removed. The tests use historical dates, so they turn it off.
    """
    import scripts.backfill as backfill_module

    monkeypatch.setattr(backfill_module, "BACKFILL_FLOOR", None)


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
def postgres_url(monkeypatch):
    """Point the tests at a separate PostgreSQL database, empty.

    The test database is created on the server of `LEETCODE_TEST_DB_URL`,
    not on the server of the operational database. The pipeline can talk
    to Neon while the tests use the local Docker container, and a
    provider that forbids `CREATE DATABASE` never blocks the test suite.

    The tests are skipped when the test server is not reachable.
    """
    import psycopg

    from scripts.db_utils import get_db_url

    base_url = get_db_url()
    test_url = os.environ.get("LEETCODE_TEST_DB_URL") or _url_with_database(
        base_url, TEST_DB_NAME
    )
    test_db_name = _database_name(test_url)
    # The maintenance database always exists, and it is the one that is
    # allowed to create another database.
    admin_url = _url_with_database(test_url, "postgres")

    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (test_db_name,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{test_db_name}"')
    except psycopg.Error as e:
        pytest.skip(f"PostgreSQL is not reachable: {e}")

    try:
        with psycopg.connect(test_url, autocommit=True, connect_timeout=5) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
    except psycopg.Error as e:
        pytest.skip(f"the test database is not usable: {e}")

    monkeypatch.setenv("LEETCODE_DB_URL", test_url)
    return test_url


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
