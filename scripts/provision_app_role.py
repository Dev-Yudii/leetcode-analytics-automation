"""Provision the application role of the operational database.

The pipeline and the notebook sync should not run as the database owner.
This script creates `leetcode_app`: a role that owns the objects it
manages — so it can apply the schema — but has no cluster-level powers.
It cannot create databases, roles or extensions, and it cannot read the
credentials of any other role.

The ownership is what makes the schema self-healing: `ensure_schema()`
runs `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` and
`CREATE OR REPLACE VIEW`, and all three need ownership, not just
privileges.

Usage:
    uv run python scripts/provision_app_role.py            # dry run
    uv run python scripts/provision_app_role.py --apply    # do it

The owner connection is NOT stored in `.env`. It is a cluster-level
credential and the `.env` file is read by every single run of the
pipeline. It comes from the environment instead, for the one command
that needs it:

    $env:LEETCODE_ADMIN_DB_URL="postgresql://neondb_owner:...@host/neondb?sslmode=require"
    uv run python scripts/provision_app_role.py --apply

The application connection string is written to `.env` as
`LEETCODE_DB_URL`. The generated password is never printed and never
reaches a command line: the script prints the shape of the connection
(scheme, host, database, user) and nothing else.
"""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from scripts.db_utils import PROJECT_ROOT, connection_shape

APP_ROLE = "leetcode_app"
ADMIN_URL_ENV = "LEETCODE_ADMIN_DB_URL"
DB_URL_ENV = "LEETCODE_DB_URL"
ENV_FILE = PROJECT_ROOT / ".env"

# The objects the pipeline manages. The role owns them so that it can
# alter them; the sequence keeps the identity of the audit rows.
OWNABLE_KINDS = {
    "r": "TABLE",
    "p": "TABLE",
    "v": "VIEW",
    "m": "MATERIALIZED VIEW",
    "S": "SEQUENCE",
    "f": "FOREIGN TABLE",
}


class ProvisionError(Exception):
    """The provisioning could not run. The message states the real cause."""


def _read_env_file() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _write_env_file(lines: list[str]) -> None:
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_env_value(lines: list[str], key: str, value: str) -> list[str]:
    """Replace a line in the .env file, or append it."""
    prefix = f"{key}="
    updated = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            if not replaced:
                updated.append(f"{prefix}{value}")
                replaced = True
            continue
        updated.append(line)
    if not replaced:
        updated.append(f"{prefix}{value}")
    return updated


def _remove_env_value(lines: list[str], key: str) -> list[str]:
    """Drop a line from the .env file."""
    prefix = f"{key}="
    return [line for line in lines if not line.startswith(prefix)]


def _write_app_url(app_url: str) -> None:
    """Write the application connection string to `.env`.

    Only the application credential goes to the file. The owner
    credential is never written: it comes from the environment, for the
    one command that needs it. Any leftover owner line is dropped here,
    so the file cannot keep it by accident.
    """
    lines = _set_env_value(_read_env_file(), DB_URL_ENV, app_url)
    lines = _remove_env_value(lines, ADMIN_URL_ENV)
    _write_env_file(lines)


def _copy_to_clipboard(text: str) -> bool:
    """Put the text in the Windows clipboard.

    The clipboard is not a command line and not a log: the value goes
    from the process to the user's hands without passing through the
    console, the transcript or a file.
    """
    try:
        result = subprocess.run(
            ["clip"],
            input=text,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return result.returncode == 0


def _url_for_role(admin_url: str, role: str, password: str) -> str:
    """The admin connection string, pointing at another role."""
    parts = urlsplit(admin_url)
    netloc = f"{role}:{password}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _role_privileges(cursor, role: str) -> dict:
    cursor.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin"
        " FROM pg_roles WHERE rolname = %s",
        (role,),
    )
    row = cursor.fetchone()
    if row is None:
        return {}
    return {
        "superuser": row[0],
        "createdb": row[1],
        "createrole": row[2],
        "login": row[3],
    }


def _ownable_objects(cursor) -> list[tuple[str, str, bool]]:
    """The objects of the public schema, with the sequences that are
    linked to a column.

    A sequence generated for a serial column cannot change its owner on
    its own: Postgres refuses it with "linked to a table column". The
    ownership of the table carries it, so those are transferred with
    their table and skipped here.
    """
    cursor.execute(
        "SELECT c.relname, c.relkind,"
        " EXISTS ("
        "   SELECT 1 FROM pg_depend d"
        "   WHERE d.classid = 'pg_class'::regclass"
        "     AND d.objid = c.oid"
        "     AND d.deptype = 'a'"
        " ) AS linked"
        " FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public'"
        "   AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')"
        " ORDER BY CASE c.relkind WHEN 'S' THEN 1 ELSE 0 END, c.relname"
    )
    return [(row[0], OWNABLE_KINDS[row[1]], row[2]) for row in cursor.fetchall()]


def provision(admin_url: str, apply: bool) -> dict:
    """Create the role and hand it the ownership of the schema."""
    import psycopg
    from psycopg import sql

    password = secrets.token_urlsafe(32)
    admin_role = urlsplit(admin_url).username or "neondb_owner"

    with psycopg.connect(admin_url, autocommit=False) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)
            )
            exists = cursor.fetchone() is not None

            objects = _ownable_objects(cursor)

            if not apply:
                return {
                    "applied": False,
                    "role_exists": exists,
                    "objects": objects,
                    "app_url": _url_for_role(admin_url, APP_ROLE, password),
                }

            # Each statement is labelled: a failure reports which one it
            # was, without the message (it may carry the password).
            steps = []

            def run(label: str, statement: str) -> None:
                steps.append(label)
                try:
                    cursor.execute(statement)
                except Exception:
                    raise ProvisionError(label)

            # The role. The password is a literal in the statement, so an
            # error message could carry it: nothing below prints the
            # exception message, only the label of the failing step.
            literal = sql.Literal(password).as_string(conn)
            run(
                f"create the role {APP_ROLE}",
                f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD {literal}"
                if not exists
                else f"ALTER ROLE {APP_ROLE} LOGIN PASSWORD {literal}",
            )

            # To give an object to another role, the session must be able
            # to SET ROLE to it. The admin is not a superuser in Neon, so
            # it needs the membership. The direction matters: the admin
            # becomes a member of the application role, never the other
            # way around — the application role must not inherit the
            # CREATEDB and CREATEROLE powers of the admin.
            run(
                f"give {admin_role} the membership of {APP_ROLE}",
                f"GRANT {APP_ROLE} TO {admin_role}",
            )

            # The privileges are granted before the ownership moves, so
            # the admin keeps its access to everything it owned.
            run(
                "grant the schema privileges",
                f"GRANT USAGE, CREATE ON SCHEMA public TO {APP_ROLE}"
                f"; GRANT ALL ON SCHEMA public TO {admin_role}",
            )
            run(
                "grant the table privileges",
                f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
                f"; GRANT ALL ON ALL TABLES IN SCHEMA public TO {admin_role}",
            )
            run(
                "grant the sequence privileges",
                f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"
                f"; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {admin_role}",
            )
            run(
                "grant the default privileges",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public"
                f" GRANT ALL ON TABLES TO {APP_ROLE}"
                "; ALTER DEFAULT PRIVILEGES IN SCHEMA public"
                f" GRANT ALL ON SEQUENCES TO {APP_ROLE}",
            )

            # The ownership. Owning the objects is what allows the role
            # to alter them: `ensure_schema()` runs ALTER TABLE and
            # CREATE OR REPLACE VIEW, and both need ownership, not just
            # privileges. The tables come first: the ownership of a
            # table carries the sequences of its serial columns.
            for name, kind, linked in objects:
                if linked:
                    continue
                run(
                    f"transfer the ownership of {kind} {name}",
                    f"ALTER {kind} public.{name} OWNER TO {APP_ROLE}",
                )

            app_privileges = _role_privileges(cursor, APP_ROLE)
            admin_privileges = _role_privileges(cursor, admin_role)

        conn.commit()

    return {
        "applied": True,
        "role_exists": exists,
        "objects": objects,
        "app_url": _url_for_role(admin_url, APP_ROLE, password),
        "app_privileges": app_privileges,
        "admin_privileges": admin_privileges,
    }


def rotate_owner_password(admin_url: str) -> str:
    """Give the database owner a new password.

    The password is generated at runtime and handed over through the
    clipboard: it is never printed, never reaches a command line and
    never lands in a file. Use it when a credential may have been
    exposed — the old password dies here.

    The caller is responsible for the hand-over: the new connection
    string has to reach the place where the owner credential lives
    (the Neon console, a password manager).
    """
    import psycopg
    from psycopg import sql

    admin_role = urlsplit(admin_url).username
    if not admin_role:
        raise ProvisionError("the admin connection string has no user")

    password = secrets.token_urlsafe(32)

    with psycopg.connect(admin_url, autocommit=False) as conn:
        with conn.cursor() as cursor:
            literal = sql.Literal(password).as_string(conn)
            try:
                cursor.execute(f"ALTER ROLE {admin_role} PASSWORD {literal}")
            except Exception:
                # The statement carries the new password: the message is
                # never printed.
                raise ProvisionError(f"change the password of {admin_role}")
        conn.commit()

    return _url_for_role(admin_url, admin_role, password)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Provision the {APP_ROLE} role of the operational database"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="do it (without this flag nothing is changed)",
    )
    parser.add_argument(
        "--rotate-owner",
        action="store_true",
        help="give the database owner a new password and copy it to the clipboard",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    admin_url = os.environ.get(ADMIN_URL_ENV)
    if not admin_url:
        print(
            f"[ERROR] {ADMIN_URL_ENV} is not set. It holds the connection"
            " string of the database owner."
        )
        print("")
        print(
            "        The owner credential is not stored in .env on purpose:"
            " it is a cluster-level credential and the file is read by"
            " every run of the pipeline."
        )
        print("")
        print("        Paste it into the environment for this one command:")
        print("")
        print(
            '            $env:LEETCODE_ADMIN_DB_URL="postgresql://neondb_owner:...'
            '@host/neondb?sslmode=require"'
        )
        print(
            "            uv run python scripts/provision_app_role.py"
            + (" --rotate-owner" if args.rotate_owner else " --apply")
        )
        print("")
        print(
            "        The connection string of the owner is in the Neon"
            " console: Dashboard -> Connection string -> neondb_owner."
        )
        return 1

    if args.rotate_owner:
        try:
            new_admin_url = rotate_owner_password(admin_url)
        except ProvisionError as e:
            print(f"[ERROR] the rotation failed at the step: {e}")
            return 1
        except Exception as e:
            print(
                f"[ERROR] the rotation failed: {type(e).__name__}"
                f" (sqlstate {getattr(e, 'sqlstate', 'unknown')})"
            )
            return 1

        copied = _copy_to_clipboard(new_admin_url)

        print("The owner password was rotated.")
        print(f"  owner url : {connection_shape(new_admin_url)}")
        if copied:
            print("  hand-over : the new connection string is in the clipboard")
            print(
                "              paste it in the Neon console (Dashboard ->"
                " Connection string -> neondb_owner) and in your password"
                " manager. The old password is already dead."
            )
        else:
            print(
                "  hand-over : FAILED — the clipboard is not available, so"
                " the new connection string is lost."
            )
            print(
                "              The old password is already dead: reset the"
                " owner password from the Neon console"
                " (Dashboard -> Roles -> neondb_owner)."
            )
            return 1
        return 0

    try:
        report = provision(admin_url, apply=args.apply)
    except ProvisionError as e:
        print(f"[ERROR] the provisioning failed at the step: {e}")
        print("        nothing was changed: the transaction was rolled back.")
        return 1
    except Exception as e:
        # The statement may carry the generated password: the message is
        # never printed.
        print(
            f"[ERROR] the provisioning failed: {type(e).__name__}"
            f" (sqlstate {getattr(e, 'sqlstate', 'unknown')})"
        )
        return 1

    if not args.apply:
        print("[dry-run] nothing was changed. Here is what would happen:")
        print(f"  role     : {APP_ROLE} ({'exists' if report['role_exists'] else 'new'})")
        print(f"  owns     : schema public + {len(report['objects'])} object(s)")
        for name, kind, linked in report["objects"]:
            suffix = " (with its table)" if linked else ""
            print(f"             {kind} public.{name}{suffix}")
        print(f"  app url  : {connection_shape(report['app_url'])}")
        print("  written  : .env (LEETCODE_DB_URL)")
        return 0

    _write_app_url(report["app_url"])

    privileges = report.get("app_privileges", {})
    print(f"Role {APP_ROLE} is ready.")
    print(f"  owns       : schema public + {len(report['objects'])} object(s)")
    print(f"  superuser  : {privileges.get('superuser')}")
    print(f"  createdb   : {privileges.get('createdb')}")
    print(f"  createrole : {privileges.get('createrole')}")
    print(f"  app url    : {connection_shape(report['app_url'])}")
    print(f"  written    : .env ({DB_URL_ENV})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
