# Architecture

## Layers

```
mcp/            MCPServer tools:
                   Execution (caller chooses intent): search_rfc_functions,
                     get_rfc_function_interface, call_rfc_function,
                     commit_rfc_transaction, rollback_rfc_transaction
                   Inspection (server chooses transport): read_abap_source
   |                          |
execution/      policy        source_reader.py  RFC fallback (program/FM/class,
   -> param_mapper               |                incl. class-pool include-walking)
   -> invoker                 adt/               ADTClient (httpx.Client, read-only)
   -> result_transform
   |
discovery/      catalog (search / get_interface) -> structure_resolver -> cache
   |
sap/            ConnectionPool (pyrfc.Connection pooling) + PooledCaller adapter
```

`sap/caller.py` defines a narrow `RfcCaller` protocol (`.call(name, **params)`)
that both `pyrfc.Connection` and `tests/fakes/fake_pyrfc.FakeConnection`
satisfy structurally. `discovery/catalog.py` and `execution/invoker.py`
depend only on this protocol (via `sap.connection.PooledCaller`), not on
`pyrfc` or `ConnectionPool` directly — this is what keeps them unit-testable
without the SAP NW RFC SDK installed.

`import pyrfc` is confined to `sap/connection.py`, always function-local
(inside `_import_pyrfc()`), so the rest of the package stays importable on
any Python version even without the SDK. `import httpx` is similarly
confined to `adt/client.py` and `adt/exceptions.py`.

## read_abap_source: one tool, transport chosen internally

See `docs/adt_rfc_integration_plan.md` for the full design rationale. This
is deliberately different from every other tool in this server: for
`call_rfc_function`, the caller's choice (which function, `mode="read"` vs
`"write"`) reflects real intent only the caller knows — that choice is
guided (docstrings, server `instructions`) but never removed. Reading ABAP
source has no equivalent ambiguity — there's always one clearly-best answer
(ADT, when it works) and a well-defined fallback (RFC) — so the choice is
removed entirely rather than merely guided. A calling agent cannot get this
one wrong, because there's nothing for it to decide.

`mcp/tools_source.py`'s `read_abap_source` tries `adt/client.py`'s
`ADTClient` first when `RFC_MCP_ADT_ENABLED=true`, and falls back to
`execution/source_reader.py`'s RFC-based reading (`RPY_PROGRAM_READ` /
`RPY_FUNCTIONMODULE_READ` via the *same* `ExecutionInvoker` used by
`call_rfc_function` — same policy checks, same audit logging, nothing
bypassed) on **any** `ADTError`, not just "not configured". A live ADT
outage degrades to RFC transparently rather than failing the read. The
response's `via` field (`"adt"` or `"rfc"`) is informational only — callers
never need to branch on it.

`ADTClient` wraps a single `httpx.Client` (HTTP already pools/reuses
connections safely, unlike a stateful `pyrfc.Connection`, so no bounded-pool
equivalent is needed) and exposes three read-only calls: `get_program_source`,
`get_class_source`, `get_function_module_source` — GETs against ADT's
`.../source/main` endpoints, plain-text regardless of object type.

`source_reader.py`'s RFC-side class reading is two-phase, not guessed: pad
the class name to 30 characters with `=` and suffix `CP` to get the
class-pool program, read it with `WITH_INCLUDELIST='X'` to get the *real*
per-class include list (`CU`/`CI`/`CO`/`CM<NNN>`/...), then read each one.
Guessing which includes exist without that discovery step is unreliable —
confirmed directly during this project's own development, where a version
that skipped the include-list discovery failed for several classes.

Disabled by default (`RFC_MCP_ADT_ENABLED=false`) and every field in
`ADTConnectionSettings` is optional unless enabled — deployments that only
want RFC configure nothing new and `read_abap_source` works purely on the
RFC fallback path with zero extra configuration.

There is deliberately no source-write/activate tool. Per the plan doc, ADT
write capability needs its own dedicated safety review (CSRF token
handshake, transport/activation semantics) before it's built — reading
source is a fundamentally different risk profile than editing it.

**ADT itself untested against a live service.** Every SAP RFC-side
capability in this project (including the RFC fallback path this tool
uses) was validated against a real system during development; the ADT
client specifically wasn't — the one system this was built against didn't
have ADT/ICM ports reachable (see the plan doc's "Status" note). It's fully
unit tested against a mocked HTTP transport (`tests/test_adt_client.py`),
but the exact endpoint shapes are implemented from documented ADT REST
conventions, not confirmed against a real server. Because the fallback is
automatic, this doesn't block using `read_abap_source` today — it just
means every real-world call so far has gone through the RFC path, and the
ADT path remains implemented-but-unverified until pointed at a reachable
ADT-enabled system at least once.

## Read-only vs. write

RFC has no universal "this function only reads" flag. `execution/policy.py`
enforces a config-driven allow/deny classification (`rfc_mcp.config.
PolicySettings`), fail-closed: functions not explicitly allowed are blocked.
This needs to be curated with SAP Basis input per landscape before enabling
`RFC_MCP_POLICY_MODE=read_write` in any real environment.

### Generic table-reader guard

`deny_patterns` classifies by the *function name* being called — but
`RFC_READ_TABLE` (and known clones like `RFC_GET_TABLE_ENTRIES`,
`/SDF/RFC_READ_TABLE2`, `BBP_RFC_READ_TABLE`) reads whatever table is named
in its `QUERY_TABLE` parameter, and none of those function names match a
mutating-verb pattern — so by function name alone, `mode="read"` would let a
caller dump `USR02`, `AGR_USERS`, `UST04`, or any other table the RFC user's
own SAP-side authorization permits, entirely unrestricted. `PolicySettings.
table_deny_patterns` (default: `DEFAULT_SENSITIVE_TABLE_PATTERNS` in
`config.py`, covering `USR*`/`AGR_*`/`UST04`/`DEVACCESS`/`RFCDES`/etc.) is a
second, independent guard specifically for this: `ExecutionPolicy.
_check_generic_table_reader()` runs before the normal allow/deny check
whenever the called function is in `generic_table_reader_functions`, and
blocks regardless of declared mode. Same philosophy and same limitation as
`deny_patterns`: defense in depth, a heuristic list, not a substitute for
SAP-side `S_TABU_DIS`/`S_TABU_NAM` authorization scoped on the RFC user.

This guard is, in effect, our version of arc-1's `opType`-vs-`scope`
separation (`docs/competitor_analysis_arc1.md`): for the one place we can
derive a real signal independent of the caller's declared `mode`— the
`QUERY_TABLE` parameter value on a known generic-reader function — we check
that signal instead of trusting the label. It doesn't generalize to
`call_rfc_function` as a whole, though: arc-1 can do this everywhere because
their tool surface is a fixed, hand-curated action registry (calling
`SAPWrite.delete_method` *is* intrinsically `opType: Update`, no function
name to inspect). Ours is arbitrary RFC function calling — there's no
intrinsic classification to derive for a function module we've never seen
before beyond its name, which is exactly what `deny_patterns` already
checks. Extending this further would mean building a real per-function
classification lookup (e.g. from SAP's own function module properties), not
something to bolt on speculatively.

## Write commit model

`call_rfc_function` never auto-commits. Many BAPIs stage changes in the
current LUW; `commit_rfc_transaction` / `rollback_rfc_transaction` are
separate, explicit tools (`BAPI_TRANSACTION_COMMIT` / `_ROLLBACK`) so an
agent can inspect a call's result (e.g. `BAPIRET2` messages) before deciding
to persist. A first write reserves one pooled connection and returns an
opaque `transaction_id`; subsequent writes, commit, and rollback use that ID
to stay on the same connection and therefore the same SAP LUW. IDs expire
after `RFC_MCP_TRANSACTION_TTL_SECONDS` of inactivity and are rolled back.
Open transactions are also rolled back during clean server shutdown. A failed
write discards its connection because the LUW state is uncertain.

The pool has a bounded acquisition timeout. Exhaustion produces a clear
error instead of leaving an MCP request blocked forever.

## Audit logging

Two choke points, two loggers, covering the full lifecycle of a call:

- `execution/policy.py` (`rfc_mcp.execution.policy`): every `authorize()`/
  `authorize_transaction_control()` decision — `ALLOWED`/`DENIED`, function
  name, mode, and (for generic table-reader calls) the target table name,
  since that's the exact signal the table-reader guard exists to catch.
- `execution/invoker.py` (`rfc_mcp.execution.invoker`): the outcome of the
  actual `pyrfc` call after policy allows it — `CALL SUCCEEDED`/`CALL
  FAILED` (and the commit/rollback equivalents), with the translated
  exception type and message on failure.

Together these answer "what was attempted, was it allowed, and did it
actually work" — the three questions a bare `try/except` around `pyrfc`
alone can't answer after the fact. Deliberately never logs parameter values
in bulk (could carry business-sensitive data); the table name on
table-reader calls is the one intentional exception.

## Tool surface guardrails

`tests/test_tool_surface_budget.py` enforces four things about the tool
surface itself, checked on every test run rather than left to manual review:
every tool's own JSON schema stays under a size budget, the full six-tool
surface (what `list_tools()` costs every agent up front) stays under a
combined budget, every tool has a substantive description, and every tool
parameter carries its own `description` (via `Annotated[type, Field(...)]`
on the tool function's signature — see `mcp/tools_discovery.py`,
`mcp/tools_execution.py`, `mcp/tools_source.py`).

This is a native reimplementation of two ideas found reviewing arc-1's
`check-tool-schema-budget.ts` and `validate-action-policy.ts`
(`docs/competitor_analysis_arc1.md`), not a port: their scripts assume a
fixed, hand-enumerated action registry, which our dynamic RFC-calling model
doesn't have. What transferred is the underlying principle — a tool
shouldn't ship undocumented, and the tool surface shouldn't silently bloat —
applied to what we actually have (pytest, six statically-defined tools) as
a fifth check in the existing test suite.

**Deliberately not adopted from arc-1, and why:**

- **Two-gate server-ceiling × per-caller-profile intersection.** Real,
  well-built idea, but it solves a problem we don't have yet: rfc-mcp is a
  single-process stdio server with exactly one caller and one
  `PolicySettings`. Building profile-intersection logic now would be
  speculative infrastructure with no caller to exercise it. Revisit if/when
  rfc-mcp ever serves more than one identity through one running server.
- **`$TMP`-restricted writes by default.** Only meaningful once there's a
  write path through ADT (source edit/activate). We have no ADT write
  capability at all today — `read_abap_source` is read-only by construction
  — so there's nothing yet to scope. Worth adopting verbatim the day that
  capability is built, not before.

## Out of scope (Phase 6, not built here)

Authn/authz beyond the read/write policy, rate limiting, metrics/tracing,
and remote deployment packaging. The shipped entry point is a local stdio
server. Any future Streamable HTTP deployment must implement the MCP
authorization specification, validate token audience, use HTTPS, and avoid
token passthrough. See `src/rfc_mcp/security/__init__.py` for intended hook
points.
