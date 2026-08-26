# RFC + ADT dual-transport plan

Proposed direction for extending this MCP server beyond RFC/BAPI-only access.

**Status (2026-08-04): partially implemented, and reworked once already.**
The first version exposed `adt_read_source` as its own tool alongside the
RFC tools, guided by docstrings + server `instructions` text telling a
calling agent when to prefer it and what to do if ADT was disabled. That
turned out to be the wrong shape: guidance is inherently probabilistic — it
relies on an agent reading and correctly weighing prose, which a weaker
model (or a long, crowded context) might not do reliably. Reading ABAP
source doesn't actually have a genuine choice for an agent to make (there's
always one clearly-best answer and a well-defined fallback), so the tool was
rebuilt as **`read_abap_source`** — one tool, no ADT-vs-RFC decision exposed
to the caller at all. It tries ADT when `RFC_MCP_ADT_ENABLED=true`, and
falls back to RFC automatically on **any** ADT failure (not just "disabled"
— a live ADT outage degrades gracefully too), via the exact same
`ExecutionInvoker` policy/audit path `call_rfc_function` uses. See
`docs/architecture.md`'s "read_abap_source" section for the full mechanics.

Implemented: `src/rfc_mcp/adt/` (`client.py`, `exceptions.py`),
`src/rfc_mcp/execution/source_reader.py` (the RFC fallback, including
reliable class-pool include discovery via `WITH_INCLUDELIST` rather than
guessing), `mcp/tools_source.py`, wired into `mcp/server.py`.
`ADTConnectionSettings` in `config.py`. Unit tested: `test_adt_client.py`
(mocked HTTP transport), `test_source_reader.py` (RFC fallback incl. the
class-name-padding formula, verified against the real system earlier in
this project — validated here for the first time as a general-purpose
function, not a one-off script), `test_tools_source.py` (the routing
decision itself: ADT-works, ADT-disabled, ADT-configured-but-fails).

**Not yet built**: `adt_where_used`, `adt_get_ddic_metadata`,
`adt_run_atc_check`, `adt_run_unit_tests`, and any source-write/activate
capability (see "Concrete shape" below for why write is a deliberately
separate, harder decision). These remain genuinely separate tools even
after the read_abap_source rework, since they don't have an RFC-equivalent
fallback to route to — where-used/ATC/unit-test have no RFC counterpart at
all, so there would be nothing to fall back *to*.

## Core idea

RFC and SAP's ADT (ABAP Development Tools) REST protocol solve different
problems, and the tool-design rule that fell out of building this is: **only
expose a transport choice to the calling agent when the choice reflects real
intent it alone knows.** Otherwise, collapse it — pick the best available
option internally and fall back automatically.

- **RFC/BAPI (`search_rfc_functions`, `get_rfc_function_interface`,
  `call_rfc_function`, `commit_rfc_transaction`, `rollback_rfc_transaction`)**
  — the *execution plane*. Calling business functions, posting data, using
  the automation semantics SAP built for this. `mode="read"` vs `"write"`,
  and which function to call, genuinely reflect caller intent — these stay
  separate, agent-driven tools, service-account driven, tightly scoped, well
  audited.
- **`read_abap_source`** — the *inspection plane*, and the one place this
  plan's original "two parallel tool families" idea turned out to be wrong.
  There's no caller intent to preserve in "should I read this program's
  source via ADT or RFC" — one answer is always better when available, so
  the tool decides internally instead of asking. See `docs/architecture.md`.
- **Not-yet-built ADT capabilities** (where-used, ATC, ABAP Unit) have no
  RFC equivalent to fall back to, so if/when they're built they'll remain
  genuinely separate, ADT-only tools — the collapsing trick only works when
  there's something to collapse *into*.

Intended agent loop for the execution side: **inspect via read_abap_source →
decide → execute via call_rfc_function**, closer to how a careful human
developer actually works, instead of calling a function the agent has never
seen based on a bare interface signature alone.

## Weakness → which side fixes it

| Weakness | RFC's role | ADT's role | Residual after combining |
|---|---|---|---|
| Generic reader injection (`RFC_READ_TABLE` free-form WHERE is attacker/LLM-controllable ABAP boolean logic) | Keep for business-data reads, gated as a last resort | Resource-scoped (request *this* object by name/URI, not a query string) — removes the injection surface for **code** access entirely | Business-data reads still need an explicit table allow-list + WHERE-clause validator; ADT doesn't cover business data |
| Single shared identity / no principal propagation (today: one RFC service account, which happens to hold `SAP_ALL`) | Appropriate model for automated business actions — but needs that account's own authorizations fixed regardless | Normally used per-developer, authenticated as the actual human — naturally scopes code visibility | Execution side still runs under one shared identity by design; fixing the account's over-broad authorization is a prerequisite either way |
| Weak/blank type metadata (`abap_type: ""` seen on nearly every introspected parameter) | — | Real DDIC metadata: data element docs, domains, foreign keys | Agent should look up meaning via ADT before constructing an RFC call |
| No where-used / call-hierarchy (today: manual grep across separately dumped source files) | — | Native repository-information-system queries | Fully solved for code; nothing for business-data lineage |
| No static analysis / test execution (the `I_NO_ENQUEUE = ABAP_TRUE` race condition in `ZCL_CA_PAYMENT_SERVICES` was only caught by manual reading) | — | ATC checks + ABAP Unit, triggerable per object | Solved as a pre-flight step ahead of RFC execution |
| BAPI/LUW commit-sequencing footgun | The thing actually being invoked | Read the BAPI's own source/docs first to learn its calling convention | Reduces guesswork, doesn't remove the need for business-process knowledge |
| Retry-under-flakiness / idempotency (hit personally via the AnyConnect VPN drops during this project) | — | — | Neither protocol fixes this — MCP-server-level concern (idempotency keys, dedup on retry), independent of transport choice |

## Concrete shape

- Existing tools (`search_rfc_functions`, `get_rfc_function_interface`,
  `call_rfc_function`, `commit_rfc_transaction`, `rollback_rfc_transaction`)
  unchanged as the execution plane.
- `read_abap_source` (**done**) — single tool, internal ADT-then-RFC
  fallback, no transport choice exposed to the caller.
- `adt_where_used`, `adt_get_ddic_metadata`, `adt_run_atc_check`,
  `adt_run_unit_tests` (all **not yet built** — skipped deliberately rather
  than shipped as guessed/unverified XML request-body contracts; where-used
  and ATC in particular have real complexity beyond a plain GET-source call,
  and no live system to validate the exact schema against). Unlike
  `read_abap_source`, these have no RFC-side equivalent to fall back to, so
  if built they'd be real ADT-only tools, gated by `RFC_MCP_ADT_ENABLED`
  with no fallback story — worth deciding at that point whether "not
  available" should be a clear tool-call error (matching how
  `read_abap_source`'s ADT-disabled path used to behave) or whether the tool
  simply shouldn't be registered at all when ADT is off.
- Per-calling-user ADT authentication rather than the shared configured
  account — not yet done; `read_abap_source`'s ADT path currently uses one
  account, same single-identity limitation `call_rfc_function` has (see the
  weakness table above).
- `ExecutionPolicy` needs a second, distinct branch for ADT *write* (source
  edit + activate) if that's ever built — gated harder than the current
  business-data `read_write` policy, since it changes code, not records —
  **not built**, needs its own CSRF-token handshake and safety review
  before it exists at all. Read/inspect needed no such policy branch: "is
  ADT enabled and did it work" is itself the only gate, and RFC fallback on
  failure means there's no case where inspection is simply unavailable.

## Next step if pursued

Check whether ADT services are actually activated/reachable on this system
(SICF service check) before scaffolding any tool implementation.

**Status (checked 2026-08-04):** Not reachable from this environment. TCP
probes to the standard ICM ports for sysnr 01 (`8001` HTTP, `44301` HTTPS)
both failed, while the RFC port (`3301`) succeeded in the same check —
ruling out a dead VPN as the cause. Inconclusive as to *why*: either ADT/ICF
services genuinely aren't activated on this system, or (more likely, given
typical consultant VPN profiles) this connection's split-tunnel routing only
permits the RFC gateway port and nothing else. Resolving this needs either
confirmation from SAP Basis (is `/sap/bc/adt/*` active in SICF?) or from
whoever manages the VPN profile (does it route ports 8001/44301 to
`srv-devecc01` at all?). Until one of those is answered, there's no network
path to prototype the ADT tool family against this system — the
architecture proposal above remains valid as a design regardless.
