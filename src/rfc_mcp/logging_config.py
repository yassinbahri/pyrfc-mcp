"""Logging setup. Never logs credentials — SAPConnectionSettings.passwd is a
SecretStr and to_pyrfc_kwargs() results must not be logged verbatim."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger("rfc_mcp")
    root.setLevel(level)
    if root.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
