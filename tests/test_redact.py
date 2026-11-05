"""Tests for the redaction of the credentials.

The rule of the project: a credential is never printed. These tests
are the guard of that rule.
"""

from scripts.redact import redact


class TestConnectionStrings:
    def test_the_password_of_a_connection_string_is_removed(self):
        text = "postgresql://leetcode_app:s3cr3t@host.neon.tech/neondb"
        result = redact(text)

        assert "s3cr3t" not in result
        assert "postgresql://leetcode_app:***@host.neon.tech/neondb" == result

    def test_a_url_without_a_password_is_left_alone(self):
        text = "postgresql://leetcode_app@host.neon.tech/neondb"
        assert redact(text) == text

    def test_a_host_with_a_port_is_not_mistaken_for_a_password(self):
        text = "postgresql://host:5432/neondb"
        assert redact(text) == text

    def test_a_connection_without_a_user_is_redacted(self):
        text = "postgresql://:s3cr3t@host/neondb"
        assert "s3cr3t" not in redact(text)

    def test_the_query_string_is_kept(self):
        text = "postgresql://u:s3cr3t@host/db?sslmode=require&channel_binding=require"
        result = redact(text)

        assert "sslmode=require" in result
        assert "channel_binding=require" in result
        assert "s3cr3t" not in result


class TestLabelledSecrets:
    def test_a_labelled_password_is_removed(self):
        result = redact("password=hunter2 is wrong")

        assert "hunter2" not in result
        assert "password=***" in result

    def test_a_labelled_token_is_removed(self):
        result = redact("token: ghp_abcdefghijklmnopqrstuvwxyz012345")

        assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in result
        assert "***" in result

    def test_a_secret_is_removed(self):
        result = redact("secret = topsecretvalue")

        assert "topsecretvalue" not in result

    def test_an_ordinary_sentence_is_left_alone(self):
        text = "the password authentication failed for the user"
        assert redact(text) == text


class TestEnvironmentSecrets:
    def test_a_password_that_is_in_the_environment_is_removed(self, monkeypatch):
        monkeypatch.setenv("LEETCODE_DB_URL", "postgresql://app:uniquesecretvalue@host/db")

        result = redact("the connection postgresql://app:uniquesecretvalue@host/db failed")

        assert "uniquesecretvalue" not in result

    def test_a_password_is_removed_even_without_the_url_around_it(
        self, monkeypatch
    ):
        monkeypatch.setenv("LEETCODE_DB_URL", "postgresql://app:uniquesecretvalue@host/db")

        result = redact("it said uniquesecretvalue in the middle of a sentence")

        assert "uniquesecretvalue" not in result

    def test_a_whole_token_is_removed(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "abcdefghijklmnopqrstuvwxyz")

        result = redact("the token was abcdefghijklmnopqrstuvwxyz")

        assert "abcdefghijklmnopqrstuvwxyz" not in result


class TestRobustness:
    def test_none_becomes_an_empty_string(self):
        assert redact(None) == ""

    def test_an_empty_string_stays_empty(self):
        assert redact("") == ""

    def test_a_number_is_accepted(self):
        assert redact(42) == "42"

    def test_the_function_never_raises(self):
        class Weird:
            def __str__(self):
                raise ValueError("no string for you")

        assert isinstance(redact(Weird()), str)
