# pyrfc-mcp

[![CI](https://github.com/yassinbahri/pyrfc-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/yassinbahri/pyrfc-mcp/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

MCP server exposing SAP RFC-enabled function modules (BAPIs/RFCs) to AI
agents through a discovery-first interface, built on SAP's `pyrfc`
connector — plus automatic ABAP source reading (ADT when reachable,
transparent RFC fallback otherwise, see
[docs/adt_rfc_integration_plan.md](docs/adt_rfc_integration_plan.md)).

It is deny-by-default: discovering an RFC does not authorize calling it.
Function allowlists, mutating-name deny rules, sensitive-table guards, result
limits, and connection-affine transactions remain enforced at the server.

## Try it without SAP

The supported demo backend uses deterministic synthetic RFC metadata and
business records. It exercises the real discovery, validation, authorization,
result-limiting, and MCP tool layers; only the final SAP transport is replaced.

```console
python -m pip install pyrfc-mcp
rfc-mcp doctor --demo --connect
rfc-mcp --demo
```

No SAP account, PyRFC installation, or SAP NW RFC SDK is needed for demo mode.
Configure an MCP client with the included [.mcp.json.example](.mcp.json.example)
to explore it immediately.

## Setup

See [docs/setup.md](docs/setup.md) for the SAP NW RFC SDK + Python 3.11
prerequisites (required before real SAP calls work) and
[docs/architecture.md](docs/architecture.md) for the layer overview,
including the read/write policy model, the generic-table-reader guard, and
audit logging.

For a real system, install the proprietary SDK prerequisites, then:

```powershell
uv sync --extra dev
copy .env.example .env    # fill in connection + policy settings
uv run rfc-mcp doctor     # validates config and native dependencies, no SAP call
uv run rfc-mcp doctor --connect  # explicitly performs a live SAP ping
uv run pytest             # unit tests, synthetic backend, no SAP needed
uv run mcp dev src/rfc_mcp/mcp/server.py
```

Real SAP connectivity additionally requires the proprietary SAP NW RFC SDK
and the archived/yanked `pyrfc==3.3.1` connector. Read the support warning
and installation steps in [docs/setup.md](docs/setup.md) before running
`uv sync --extra sap` or the smoke test.

`doctor` intentionally redacts connection and credential values. It does not
contact SAP unless `--connect` is present, and it also supports `--json` for
automation.

## Tools

- `search_rfc_functions(pattern, group=None, limit=50)`
- `get_rfc_function_interface(function_name)`
- `call_rfc_function(function_name, parameters, mode="read"|"write", transaction_id=None)`
- `commit_rfc_transaction(transaction_id, wait=False)`
- `rollback_rfc_transaction(transaction_id)`
- `read_abap_source(object_type, object_name, function_group=None)` — one
  tool, no transport choice exposed to the caller; see
  [docs/architecture.md](docs/architecture.md).

## ABAP knowledge skill

[.claude/skills/sap-abap/](.claude/skills/sap-abap/) vendors the third-party
`sap-abap` Claude Skill so an agent using this server also has accurate
ABAP language knowledge on hand. It's licensed separately (GPL-3.0, its own
`LICENSE`/`NOTICE.md`) from the rest of this project — see below.

## Scope

Foundation, connection layer, discovery, execution, and MCP integration are
built and tested, including a deny-by-default read/write policy, a table-level guard
against the generic-table-reader injection surface (`RFC_READ_TABLE` et
al.), fail-closed RFC response limits, and audit logging of every policy
decision and call outcome. Not
built: multi-tenant auth/RBAC beyond the single server-wide policy, rate
limiting, metrics/tracing, and deployment packaging — see
[docs/architecture.md](docs/architecture.md)'s "Out of scope" section for
what’s deliberately deferred and why.

Write calls return an opaque `transaction_id`. Reuse it for related writes,
then pass it to commit or rollback. This pins the entire SAP LUW to one RFC
connection; abandoned transactions expire and roll back automatically.

## Security posture

- Reads and writes are denied unless their function names match explicit
  allowlists. The example configuration only permits discovery, source
  reading, and the harmless `STFC_CONNECTION` smoke test.
- MCP tool annotations describe read/write risk for capable clients, but are
  advisory metadata—not an authorization boundary. Server policy and the SAP
  service account's `S_RFC`/table authorizations remain mandatory.
- Stdio credentials come from the environment and are never placed in MCP
  tool arguments. Do not expose the server over HTTP without implementing the
  MCP authorization specification and deployment-level rate limiting.
- RFC results are rejected rather than silently truncated when their cumulative
  nested table rows or serialized UTF-8 JSON size exceed
  `RFC_MCP_RESULT_MAX_TABLE_ROWS` or
  `RFC_MCP_RESULT_MAX_SERIALIZED_BYTES`. These limits protect MCP consumers;
  they cannot reduce work already performed inside SAP.
- See [SECURITY.md](SECURITY.md) for reporting and deployment guidance.

## License

MIT (see [LICENSE](LICENSE)), with one carved-out exception:
[.claude/skills/sap-abap/](.claude/skills/sap-abap/) is vendored third-party
content under GPL-3.0 — see its own `LICENSE` and `NOTICE.md`. Including
that directory does not place the rest of the project under GPL-3.0.
