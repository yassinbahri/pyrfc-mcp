from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from rfc_mcp.config import AppSettings
from rfc_mcp.diagnostics import DiagnosticReport, run_diagnostics
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
    parser.add_argument(
        "--connect",
        action="store_true",
        help="with doctor, perform an explicit live connectivity check",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with doctor, emit machine-readable JSON",
    )
    parser.add_argument(
        "command",
        choices=("serve", "doctor"),
        nargs="?",
        default="serve",
        help="serve MCP over stdio (default) or run safe installation diagnostics",
    )
    return parser.parse_args(argv)


def _format_report(report: DiagnosticReport) -> str:
    lines = [f"pyrfc-mcp doctor ({report.backend})"]
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():4}] {check.name}: {check.detail}")
    lines.append("Result: ready" if report.ok else "Result: action required")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.demo:
        os.environ["RFC_MCP_BACKEND"] = "demo"
    if args.command == "doctor":
        report = run_diagnostics(AppSettings(), connect=args.connect)
        print(json.dumps(report.as_dict(), indent=2) if args.json else _format_report(report))
        return 0 if report.ok else 1
    mcp.run()
    return 0


if __name__ == "__main__":
    main()
