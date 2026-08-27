# pyrfc-mcp

MCP server exposing SAP RFC-enabled function modules (BAPIs/RFCs) to AI
agents through a discovery-first interface, built on SAP's `pyrfc`
connector — plus automatic ABAP source reading (ADT when reachable,
transparent RFC fallback otherwise, see
[docs/adt_rfc_integration_plan.md](docs/adt_rfc_integration_plan.md)).

## Setup

See [docs/setup.md](docs/setup.md) for the SAP NW RFC SDK + Python 3.11
prerequisites (required before real SAP calls work) and
[docs/architecture.md](docs/architecture.md) for the layer overview,
including the read/write policy model, the generic-table-reader guard, and
audit logging.

Quick start once prerequisites are installed:

```powershell
uv sync --extra dev
copy .env.example .env   # fill in connection + policy settings
uv run pytest             # unit tests, fake pyrfc, no SAP needed
uv run mcp dev src/rfc_mcp/mcp/server.py
```

Real SAP connectivity additionally requires the proprietary SAP NW RFC SDK
and the archived/yanked `pyrfc==3.3.1` connector. Read the support warning
and installation steps in [docs/setup.md](docs/setup.md) before running
`uv sync --extra sap` or the smoke test.

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
al.), and audit logging of every policy decision and call outcome. Not
built: multi-tenant auth/RBAC beyond the single server-wide policy, rate
limiting, metrics/tracing, and deployment packaging — see
[docs/architecture.md](docs/architecture.md)'s "Out of scope" section for
what's deliberately deferred and why.

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
- See [SECURITY.md](SECURITY.md) for reporting and deployment guidance.

## License

MIT (see [LICENSE](LICENSE)), with one carved-out exception:
[.claude/skills/sap-abap/](.claude/skills/sap-abap/) is vendored third-party
content under GPL-3.0 — see its own `LICENSE` and `NOTICE.md`. Including
that directory does not place the rest of the project under GPL-3.0.
