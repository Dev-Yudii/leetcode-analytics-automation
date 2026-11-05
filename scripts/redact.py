"""Keep the credentials out of anything that is printed.

A connection string is a secret. The moment one of them reaches a
terminal, a log file or a transcript, it is a credential that has to be
rotated — and rotating is not free. This module is the belt to that
pair of braces: anything that is about to be shown to a human goes
through `redact()` first.

Three layers, from the most specific to the most general:

* the passwords that the environment holds right now are replaced
  wherever they appear, even in a message that does not look like a
  connection string;
* a connection string loses its password:
  `postgresql://user:***@host/database`;
* a `password=`, `token=` or `secret=` pair loses its value.

The rule of the project is simple: a credential is never printed. The
diagnostics show the *shape* of the connection, never the secret.
"""

import os
import re
from urllib.parse import urlsplit

# A connection string with a password in it.
_URL_WITH_PASSWORD = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)"
    r"(?P<user>[^:/@\s]*):(?P<password>[^@\s]*)@"
)

# A labelled secret in free text.
_LABELLED_SECRET = re.compile(
    r"(?i)\b(?P<label>password|passwd|pwd|secret|token|api[_-]?key)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^\s,;'\"]+)"
)

# The environment variables that may hold a credential.
_SECRET_NAME_MARKERS = (
    "URL",
    "DSN",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "KEY",
)


def _environment_secrets() -> list[str]:
    """The secret values that the environment holds right now.

    A URL contributes only its password: the rest of the connection
    string is the shape, and the shape is safe to show.
    """
    found: set[str] = set()

    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue

        upper = name.upper()
        if not any(marker in upper for marker in _SECRET_NAME_MARKERS):
            continue

        parts = urlsplit(value)
        if parts.password:
            found.add(parts.password)
        elif "://" not in value:
            found.add(value)

    # The longest first: a short secret that lives inside a longer one
    # is replaced as part of it.
    return sorted(found, key=len, reverse=True)


def redact(text) -> str:
    """Return the text without the credentials.

    The function never raises: a redaction that fails is worse than a
    message that is a little too talkative.
    """
    if text is None:
        return ""

    try:
        result = str(text)
    except Exception:
        return "<unprintable message>"

    try:
        for secret in _environment_secrets():
            if secret in result:
                result = result.replace(secret, "***")
    except Exception:
        pass

    try:
        result = _URL_WITH_PASSWORD.sub(
            lambda m: f"{m.group('scheme')}{m.group('user')}:***@", result
        )
    except Exception:
        pass

    try:
        result = _LABELLED_SECRET.sub(
            lambda m: f"{m.group('label')}{m.group('separator')}***", result
        )
    except Exception:
        pass

    return result
