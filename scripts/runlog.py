"""Run log: one line per event, appended to logs/pipeline.log.

The log is the first piece of the collection audit: it tells what happened
on each run, even when the database write or the file generation failed.
"""

import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"


def _use_replace_on_console() -> None:
    """The Windows console is often cp1252: a non-ASCII character would
    raise UnicodeEncodeError and kill the run."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


class RunLogger:
    """Writes the same line to the console and to the log file."""

    def __init__(self, path: Path | None = None, echo: bool = True):
        self.path = Path(path) if path else LOG_FILE
        self.echo = echo
        _use_replace_on_console()

    def _write(self, level: str, message: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        line = f"{timestamp} | {level} | {message}"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            # A broken log must never break the run
            print(f"[LOG ERROR] could not write to {self.path}: {e}", file=sys.stderr)
        if self.echo:
            print(line)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warning(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)
