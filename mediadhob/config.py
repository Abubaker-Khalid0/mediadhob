"""Local configuration and private file handling, without import-time writes."""

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv


def env_file() -> Path:
    """Use the launch directory, including when installed from a wheel."""
    return Path.cwd() / ".env"


def redact_sensitive(message: str) -> str:
    """Remove configured credentials and common session values from diagnostics."""
    for name in ("IG_PROXY", "INSTA_PASS", "INSTA_USER"):
        value = os.environ.get(name)
        if value:
            message = message.replace(value, "[REDACTED]")
    message = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", message)
    message = re.sub(
        r"(?i)([\"']?(?:sessionid|csrftoken|password|authorization)[\"']?\s*[:=]\s*)([^\r\n,;}]+)",
        r"\1[REDACTED]",
        message,
    )
    return message


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive(super().format(record))


def configure_runtime() -> None:
    """Read optional .env and configure logging when an application starts."""
    load_dotenv(env_file(), override=False)
    if not logging.getLogger().handlers:
        handler = logging.FileHandler("media_downloader.log", encoding="utf-8")
        handler.setFormatter(RedactingFormatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[handler])


def write_private_text(path: str, content: str) -> None:
    """Write a session file with owner-only permissions on POSIX systems."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        if os.name != "nt":
            os.fchmod(stream.fileno(), 0o600)
        stream.write(content)
