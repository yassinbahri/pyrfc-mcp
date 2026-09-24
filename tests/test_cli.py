from __future__ import annotations

from rfc_mcp import __main__


def test_demo_flag_selects_demo_backend(monkeypatch) -> None:
    run_calls: list[bool] = []
    monkeypatch.delenv("RFC_MCP_BACKEND", raising=False)
    monkeypatch.setattr(__main__.mcp, "run", lambda: run_calls.append(True))

    __main__.main(["--demo"])

    assert __main__.os.environ["RFC_MCP_BACKEND"] == "demo"
    assert run_calls == [True]


def test_default_cli_preserves_configured_backend(monkeypatch) -> None:
    monkeypatch.setenv("RFC_MCP_BACKEND", "sap")
    monkeypatch.setattr(__main__.mcp, "run", lambda: None)

    __main__.main([])

    assert __main__.os.environ["RFC_MCP_BACKEND"] == "sap"
