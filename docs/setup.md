# Setup — Phase 0 prerequisites

This server calls SAP through `pyrfc`, which wraps the proprietary **SAP
NetWeaver RFC SDK** (C libraries, licensed, not distributed via pip).
Everything except real SAP calls works without it because `pyrfc` is an
optional, lazily imported dependency.

> [!WARNING]
> SAP archived PyRFC on May 28, 2026. Its last release (`3.3.1`) is yanked
> from PyPI and was built/tested against SAP NW RFC SDK 7.50 Patch Level 12,
> which SAP no longer supports. There is no official replacement identified
> by the archived project. Treat this connector as legacy: validate it against
> your exact SDK/kernel combination, isolate the RFC service account, and do
> not imply SAP support for this integration.

## 1. SAP NW RFC SDK

The SDK is expected at `C:\nwrfcsdk` (already present on this machine),
containing `bin/`, `include/`, `lib/`, `demo/`, `doc/`.

Set `SAPNWRFC_HOME` before installing `pyrfc` and every time before running
this server:

```powershell
# PowerShell (current session)
$env:SAPNWRFC_HOME = "C:\nwrfcsdk"
```

To persist across sessions (user-level env vars):

```powershell
[System.Environment]::SetEnvironmentVariable("SAPNWRFC_HOME", "C:\nwrfcsdk", "User")
```

`SAPNWRFC_HOME` locates the SDK. The archived PyRFC documentation says
Windows Python 3.8+ does not require adding the SDK directory to `PATH`.
If DLL loading still fails in your environment, consult the SDK diagnostics
and your organization's Windows library-loading policy rather than globally
rewriting `PATH`.

```
ImportError: DLL load failed while importing _pyrfc: The specified module could not be found.
```

## 2. Python 3.11 (pinned)

The archived PyRFC release includes a Python 3.11 Windows wheel; this repo pins `>=3.11,<3.12`
in `pyproject.toml`. Install and create a dedicated venv:

```powershell
uv python install 3.11
uv venv --python 3.11 .venv
.venv\Scripts\Activate.ps1
```

(Or without `uv`: install Python 3.11 from python.org, then
`py -3.11 -m venv .venv`.)

## 3. Install development dependencies (no SAP SDK required)

```powershell
uv sync --extra dev
```

This installs the MCP server, test, lint, typing, and build tools without
attempting to install PyRFC.

## 4. Enable the legacy SAP connector

Only after installing and validating the SDK:

```powershell
uv sync --extra dev --extra sap
```

The project pins exactly `pyrfc==3.3.1`; a range such as `pyrfc>=3.3` will
not resolve because PyPI yanked every available release. If the wheel is
incompatible with your SDK, stop and assess a maintained connector or an
internal build rather than silently upgrading the proprietary SDK beneath
an unmaintained binding.

## 5. Verify

```powershell
python -c "import pyrfc; print(pyrfc.__version__)"
```

This succeeds with **no SAP system reachable** — it only proves the SDK
linked correctly. Actual connectivity is a separate concern, validated later
with `scripts/smoke_test.py` once real SAP credentials are available.

## 6. Configure connection + policy

Copy `.env.example` to `.env` and fill in connection parameters (see
`src/rfc_mcp/config.py` for the full settings schema) and the read/write
function policy allowlist before enabling `mode="write"` calls.

The default allowlists are empty. The example permits only discovery,
source-reading helpers, and `STFC_CONNECTION`; add business RFCs explicitly
with SAP Basis review and matching least-privilege SAP authorizations.
