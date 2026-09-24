from __future__ import annotations

from rfc_mcp.config import AppSettings, BackendMode, PolicySettings, SAPConnectionSettings
from rfc_mcp.diagnostics import CheckStatus, run_diagnostics


def _sap_settings() -> SAPConnectionSettings:
    return SAPConnectionSettings(
        ashost="sap.example.com",
        sysnr="00",
        client="100",
        user="RFC_USER",
        passwd="secret",
    )


def test_demo_diagnostics_need_no_sap_dependencies() -> None:
    report = run_diagnostics(AppSettings(backend=BackendMode.DEMO))

    assert report.ok is True
    assert [(check.name, check.status) for check in report.checks] == [
        ("backend", CheckStatus.PASS),
        ("configuration", CheckStatus.PASS),
        ("pyrfc", CheckStatus.SKIP),
        ("read policy", CheckStatus.PASS),
        ("connectivity", CheckStatus.SKIP),
    ]


def test_demo_connectivity_check_uses_synthetic_backend() -> None:
    report = run_diagnostics(AppSettings(backend=BackendMode.DEMO), connect=True)

    connectivity = report.checks[-1]
    assert connectivity.status is CheckStatus.PASS
    assert connectivity.detail == "Connected and ping succeeded."


def test_sap_dependency_failure_does_not_reveal_credentials() -> None:
    settings = AppSettings(backend=BackendMode.SAP, sap=_sap_settings())

    def unavailable() -> None:
        raise ImportError("secret must not appear")

    report = run_diagnostics(settings, pyrfc_probe=unavailable)
    rendered = str(report.as_dict())

    assert report.ok is False
    assert "secret" not in rendered
    assert report.checks[-1].status is CheckStatus.FAIL


def test_empty_read_allowlist_is_reported_without_failing_preflight() -> None:
    settings = AppSettings(
        backend=BackendMode.SAP,
        sap=_sap_settings(),
        policy=PolicySettings(read_allow_patterns=[]),
    )

    report = run_diagnostics(settings, pyrfc_probe=lambda: None)

    read_policy = next(check for check in report.checks if check.name == "read policy")
    assert report.ok is True
    assert read_policy.status is CheckStatus.WARN
