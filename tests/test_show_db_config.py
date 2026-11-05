"""Tests for the diagnostic that shows the shape of the connections.

This script exists so that a diagnostic never needs the raw `.env`
file. The secret must not appear in its output — not in the shape, not
in the length, not in the check.
"""

import pytest

from scripts.db_utils import connection_shape, password_length
from scripts.show_db_config import CONNECTION_VARS, describe, main

SECRET = "s3cr3tvalue"


class TestConnectionShape:
    def test_the_password_is_replaced(self):
        shape = connection_shape(f"postgresql://leetcode_app:{SECRET}@host.neon.tech/neondb")

        assert SECRET not in shape
        assert "***" in shape

    def test_the_essentials_are_kept(self):
        shape = connection_shape(
            f"postgresql://leetcode_app:{SECRET}@host.neon.tech:5432/neondb?sslmode=require"
        )

        assert shape.startswith("postgresql://leetcode_app:")
        assert "host.neon.tech:5432" in shape
        assert "/neondb" in shape
        assert "sslmode=require" in shape

    def test_an_empty_url_does_not_break(self):
        assert isinstance(connection_shape(""), str)

    def test_the_password_length_is_the_length(self):
        assert password_length(f"postgresql://u:{SECRET}@host/db") == len(SECRET)

    def test_a_url_without_a_password_has_length_zero(self):
        assert password_length("postgresql://u@host/db") == 0


class TestDescribe:
    def test_the_secret_never_appears(self, monkeypatch):
        monkeypatch.setenv("LEETCODE_DB_URL", f"postgresql://app:{SECRET}@host/db")

        assert SECRET not in describe("LEETCODE_DB_URL")

    def test_the_password_length_is_shown(self, monkeypatch):
        monkeypatch.setenv("LEETCODE_DB_URL", f"postgresql://app:{SECRET}@host/db")

        assert f"{len(SECRET)} characters" in describe("LEETCODE_DB_URL")

    def test_a_variable_that_is_not_set_says_so(self, monkeypatch):
        monkeypatch.delenv("LEETCODE_ADMIN_DB_URL", raising=False)

        described = describe("LEETCODE_ADMIN_DB_URL")

        assert "not set" in described
        assert "purpose" in described

    def test_every_connection_variable_has_a_purpose(self):
        for name in CONNECTION_VARS:
            assert name in CONNECTION_VARS
            assert "purpose" in describe(name)


class TestMain:
    def test_the_output_never_carries_the_secret(self, monkeypatch, capsys):
        monkeypatch.setenv("LEETCODE_DB_URL", f"postgresql://app:{SECRET}@host/db")
        monkeypatch.setenv("LEETCODE_TEST_DB_URL", f"postgresql://test:{SECRET}@host/db")

        main([])

        captured = capsys.readouterr()
        assert SECRET not in captured.out
        assert SECRET not in captured.err

    def test_it_says_where_the_secret_is_kept(self, capsys):
        main([])

        assert "never printed" in capsys.readouterr().out
