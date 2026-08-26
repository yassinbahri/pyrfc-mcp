# Usage & Testing Guide

Assumes you've already done [docs/setup.md](docs/setup.md) (SAP NW RFC SDK +
pinned Python 3.11 venv) and filled in `.env` (see the walkthrough in
[README.md](README.md) / prior setup). Create/sync the pinned environment first:

```powershell
uv sync --extra dev
```

## 1. Verify the code without touching SAP

Run this first, always — it's fast, needs no SAP connectivity, and catches
regressions in discovery/execution/policy logic before you ever dial into a
real system.

```powershell
uv run pytest -q
```

Expect something like `NN passed, 1 skipped` — the one skip is
`test_sap_exceptions.py`, which only runs once `pyrfc` is actually
importable (i.e. inside the pinned venv with the SDK linked). If it's
skipped even *inside* the pinned venv, `pyrfc` isn't installed correctly —
see step 2.

## 2. Verify pyrfc itself is installed and linked

```powershell
python -c "import pyrfc; print(pyrfc.__version__)"
```

This must succeed **before** you try connecting to anything — it only
proves the SDK's DLLs loaded, not that SAP is reachable. If it fails with
`ModuleNotFoundError`, `pyrfc` isn't installed (`uv sync --extra dev --extra sap`
inside the venv). If it fails with `ImportError: DLL load failed`,
`SAPNWRFC_HOME`/`PATH` aren't set correctly — recheck
[docs/setup.md](docs/setup.md) §1.

## 3. Verify SAP connectivity end-to-end (smoke test)

```powershell
python scripts/smoke_test.py
```

This is the real test of whether `.env` is correct. It:
1. Acquires a connection and pings it (`check_connectivity`)
2. Introspects `STFC_CONNECTION`'s interface (discovery)
3. Calls `STFC_CONNECTION` for real (execution) — SAP's built-in,
   side-effect-free echo/connectivity test function, safe to call in any
   environment

**Expected success output** (exact parameter list/count depends on your SAP
release — `REQUTEXT`/`ECHOTEXT` are the well-known ones, there may be more):
```
1. Checking connectivity...
   OK: Connected and ping succeeded.
2. Introspecting STFC_CONNECTION interface...
   N parameter(s): [...includes REQUTEXT, ECHOTEXT...]
3. Calling STFC_CONNECTION (side-effect-free echo test)...
   Result: {'ECHOTEXT': 'rfc-mcp smoke test', ...}

Smoke test passed.
```

If it fails, the exit code and printed message tell you which layer broke:

| Exit code | Meaning | Where to look |
|---|---|---|
| 1 | Connectivity check failed | `.env` `ASHOST`/`SYSNR` (or `MSHOST`/... ), network reachability to that host |
| 2 | `pyrfc`/SDK not available | Step 2 above |
| 3 | Logon failed | `.env` `CLIENT`/`USER`/`PASSWD` — verify the same credentials work in SAP GUI first |
| 4 | Communication failed | Host/port reachable? VPN needed? `SAProuter` string needed (not currently supported by this config — ask if you need it) |
| 5 | Other SAP error | Printed exception type/message — often an authorization issue (missing `S_RFC`, see below) |

If you get a logon or authorization error but SAP GUI logs in fine with the
same user, it's almost always **missing `S_RFC` authorization** for the RFC
user — see the PFCG guidance from setup, and test the same user/host/client
via SM59's "Connection Test" + "Authorization Test" buttons to confirm SAP
GUI-only login isn't secretly using a different auth path.

## 4. Inspect the MCP server directly (no AI client needed)

The `mcp` SDK ships an inspector CLI that lists tools and lets you invoke
them manually against schemas — useful for confirming the server itself is
sound before wiring up an actual agent:

```powershell
uv run mcp dev src/rfc_mcp/mcp/server.py
```

This opens a local web UI. You should see all 6 tools listed:
`search_rfc_functions`, `get_rfc_function_interface`, `call_rfc_function`,
`commit_rfc_transaction`, `rollback_rfc_transaction`, `read_abap_source`.
The last one works either way regardless of `RFC_MCP_ADT_ENABLED` — it uses
ADT when enabled/reachable and transparently falls back to RFC otherwise,
so there's nothing extra to configure to try it (see
docs/adt_rfc_integration_plan.md). Try:
1. `search_rfc_functions` with `pattern="STFC_*"` — should return
   `STFC_CONNECTION` (and similar) with no SAP write risk.
2. `get_rfc_function_interface` with `function_name="STFC_CONNECTION"` —
   confirm it shows `REQUTEXT`/`ECHOTEXT` parameters.
3. `call_rfc_function` with `function_name="STFC_CONNECTION"`,
   `parameters={"REQUTEXT": "hello"}`, `mode="read"` — should echo back.
4. Try `call_rfc_function` with `mode="write"` on anything — should be
   rejected, since `.env` has `RFC_MCP_POLICY_MODE=read_only`. This is the
   guardrail working as intended, not a bug.

When writes are deliberately enabled, the first successful write returns a
`transaction_id`. Pass it to related write calls and finally to exactly one
of `commit_rfc_transaction` or `rollback_rfc_transaction`. Completed,
failed, expired, and unknown IDs cannot be reused.

## 5. Run the server for real, wired to an MCP client

Once steps 1–4 pass, point an actual MCP client at the server. Example for
Claude Desktop/Claude Code-style config (`claude_desktop_config.json` or
equivalent `mcpServers` block):

```json
{
  "mcpServers": {
    "sap-rfc-gateway": {
      "command": "python",
      "args": ["-m", "rfc_mcp"]
    }
  }
}
```

Run the client from the project environment or replace `python` with the
absolute path to this project's `.venv` interpreter. Copy
`.mcp.json.example` to the client-specific configuration location; never
commit a machine-specific `.mcp.json`.

Restart the client, then in a conversation try prompting something like:
*"Search SAP for customer-related RFC functions"* — the agent should call
`search_rfc_functions`, then `get_rfc_function_interface` on whatever it
picks, then `call_rfc_function` with `mode="read"`. Watch for it attempting
`mode="write"` unprompted — if `.env` is still `read_only`, that's blocked
server-side regardless of what the agent tries.

## Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pyrfc'` | Wrong Python or the optional SAP connector is absent | Run `uv sync --extra dev --extra sap` after reading the legacy-support warning in `docs/setup.md` |
| `ImportError: DLL load failed while importing _pyrfc` | `SAPNWRFC_HOME`/`PATH` not set in the current shell | Re-run the `$env:SAPNWRFC_HOME`/`$env:PATH` lines from docs/setup.md §1 — these don't persist across new terminals unless set at the User env-var level |
| `SAPLogonError` | Bad `CLIENT`/`USER`/`PASSWD`, or user locked/expired | Test the same creds in SAP GUI directly first |
| `SAPCommunicationError` | Host unreachable — VPN, firewall, wrong `ASHOST`/`SYSNR` | `ping`/`telnet` the host:32<NN> port; confirm via SM51 |
| `PolicyDeniedError: ... not in read_allow_patterns, or explicitly denied` | Function name matches `DEFAULT_DENY_PATTERNS` (e.g. contains `_CHANGE`, `_CREATE`, etc.) | Working as intended for a read-only dev setup — see `docs/architecture.md` |
| `ParameterValidationError` | Missing required IMPORT parameter, or unknown parameter name | Call `get_rfc_function_interface` first to see the real parameter list before `call_rfc_function` |
| pytest test `test_sap_exceptions.py` always skipped | `pyrfc` not importable in whatever Python ran pytest | Only meaningful when run inside the pinned 3.11 venv with the SDK linked |

## What "successfully tested" looks like, end to end

1. `pytest -q` → all pass (1 skip outside the pinned venv is fine)
2. Inside the pinned venv: `python -c "import pyrfc"` → succeeds, and the
   previously-skipped test now runs and passes too
3. `python scripts/smoke_test.py` → "Smoke test passed."
4. `mcp dev` → all 6 tools listed, `STFC_CONNECTION` round-trips correctly,
   a `mode="write"` attempt is rejected, `read_abap_source` returns real
   source via its RFC fallback path even with ADT disabled (expected on
   most systems — see docs/adt_rfc_integration_plan.md)
5. A real MCP client can search, introspect, and read-call SAP functions
   through the server, and cannot write
