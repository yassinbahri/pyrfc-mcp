from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from rfc_mcp.mcp.server import mcp


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rfc-mcp",
        description="Run the MCP server for SAP RFC functions.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use deterministic synthetic RFC data; no SAP credentials or PyRFC required",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.demo:
        os.environ["RFC_MCP_BACKEND"] = "demo"
    mcp.run()


if __name__ == "__main__":
    main()
