"""Tests for the provisioning of the application role.

The important invariant: the owner credential never lands in `.env`.
The file is read by every run of the pipeline, and the owner is a
cluster-level credential.
"""

import pytest

from scripts import provision_app_role as provision


class TestWritingTheEnvFile:
    def test_the_application_url_is_written(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr(provision, "ENV_FILE", env_file)

        provision._write_app_url("postgresql://app:secret@host/db")

        assert "postgresql://app:secret@host/db" in env_file.read_text(encoding="utf-8")

    def test_the_owner_url_is_never_written(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr(provision, "ENV_FILE", env_file)

        provision._write_app_url("postgresql://app:secret@host/db")

        content = env_file.read_text(encoding="utf-8")
        assert provision.ADMIN_URL_ENV not in content

    def test_a_leftover_owner_line_is_removed(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "LEETCODE_DB_URL=postgresql://old:old@host/db\n"
            "LEETCODE_ADMIN_DB_URL=postgresql://owner:ownersecret@host/db\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(provision, "ENV_FILE", env_file)

        provision._write_app_url("postgresql://app:secret@host/db")

        content = env_file.read_text(encoding="utf-8")
        assert "ownersecret" not in content
        assert provision.ADMIN_URL_ENV not in content
        assert "postgresql://app:secret@host/db" in content

    def test_the_other_variables_survive(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "LEETCODE_TEST_DB_URL=postgresql://test:pass@localhost/db\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(provision, "ENV_FILE", env_file)

        provision._write_app_url("postgresql://app:secret@host/db")

        content = env_file.read_text(encoding="utf-8")
        assert "LEETCODE_TEST_DB_URL=postgresql://test:pass@localhost/db" in content


class TestMissingAdminUrl:
    def test_it_explains_where_the_owner_url_comes_from(
        self, monkeypatch, capsys
    ):
        monkeypatch.delenv(provision.ADMIN_URL_ENV, raising=False)

        assert provision.main([]) == 1

        out = capsys.readouterr().out
        assert "Neon console" in out
        assert provision.ADMIN_URL_ENV in out

    def test_neither_the_old_nor_the_new_credential_is_printed(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv(
            provision.ADMIN_URL_ENV, "postgresql://owner:supersecret@host/db"
        )
        monkeypatch.setattr(
            provision,
            "rotate_owner_password",
            lambda url: "postgresql://owner:newsecret@host/db",
        )
        monkeypatch.setattr(provision, "_copy_to_clipboard", lambda text: True)

        assert provision.main(["--rotate-owner"]) == 0

        out = capsys.readouterr().out
        assert "supersecret" not in out
        assert "newsecret" not in out

    def test_the_new_credential_goes_to_the_clipboard(self, monkeypatch):
        handed = {}

        monkeypatch.setenv(
            provision.ADMIN_URL_ENV, "postgresql://owner:supersecret@host/db"
        )
        monkeypatch.setattr(
            provision,
            "rotate_owner_password",
            lambda url: "postgresql://owner:newsecret@host/db",
        )
        monkeypatch.setattr(
            provision,
            "_copy_to_clipboard",
            lambda text: handed.setdefault("value", text) is None,
        )

        provision.main(["--rotate-owner"])

        assert handed["value"] == "postgresql://owner:newsecret@host/db"


class TestClipboard:
    def test_the_clipboard_receives_the_value(self, monkeypatch):
        captured = {}

        class FakeResult:
            returncode = 0

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["input"] = kwargs.get("input")
            return FakeResult()

        monkeypatch.setattr(provision.subprocess, "run", fake_run)

        assert provision._copy_to_clipboard("the-secret") is True
        assert captured["input"] == "the-secret"

    def test_a_failure_is_reported(self, monkeypatch):
        class FakeResult:
            returncode = 1

        monkeypatch.setattr(provision.subprocess, "run", lambda *a, **k: FakeResult())

        assert provision._copy_to_clipboard("the-secret") is False

    def test_a_missing_clipboard_is_reported(self, monkeypatch):
        def fake_run(args, **kwargs):
            raise FileNotFoundError("clip.exe")

        monkeypatch.setattr(provision.subprocess, "run", fake_run)

        assert provision._copy_to_clipboard("the-secret") is False
