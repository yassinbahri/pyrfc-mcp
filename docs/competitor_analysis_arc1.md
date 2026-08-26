# Competitor analysis: arc-mcp/arc-1

Full source review (not just README), done 2026-08-05 by downloading the
repo archive and reading actual implementation files — `authz/policy.ts`,
`adt/safety.ts`, `server/multi-target-basic-auth.ts`, `adt/oauth.ts`,
`package.json`. MIT licensed, both projects open source.

## The "package vs solution" question — answered

**arc-1 is a solution. rfc-mcp is a package.** Confirmed structurally, not
just by impression:

- arc-1 ships `manifest.yml`, `manifest-btp-abap.yml`, `mta.yaml`,
  `mta-ui-approuter.mtaext`, `xs-security.json`, a `Dockerfile`, and a `btp/`
  directory — a deployable, multi-tenant Cloud Foundry/BTP application with
  its own auth gateway (approuter) and XSUAA integration. It has a CLI
  (`arc1-cli`), an HTTP transport mode, a documentation *site*
  (`mkdocs.yml`), release automation (`release-please`), and 554 commits /
  148 stars / 3,474 unit + 262 integration + 141 E2E tests.
- rfc-mcp is a single-process stdio server, configured via `.env`, run as a
  subprocess of one MCP client at a time. No deployment story, no
  multi-tenant auth layer, no HTTP mode.

Neither is "better" in the abstract — they're different products solving
different problems. But it means most of arc-1's infrastructure (BTP
deployment, approuter, XSUAA, multi-target routing) isn't something to
port — it's a consequence of being a hosted solution, not a technique to
borrow piecemeal.

## What arc-1 has that RFC alone structurally cannot

- **12 intent-based tools** (`SAPRead`, `SAPSearch`, `SAPWrite`,
  `SAPActivate`, `SAPNavigate`, `SAPQuery`, `SAPTransport`, `SAPGit`,
  `SAPContext`, `SAPLint`, `SAPDiagnose`, `SAPManage`) versus our 6. They've
  built almost everything our own plan doc deliberately scoped out as
  "not yet built" (`adt_where_used` → `SAPNavigate.references`,
  `adt_run_atc_check`/`adt_run_unit_tests` → `SAPDiagnose`,
  `adt_get_ddic_metadata` → part of `SAPRead`) — proof these are buildable,
  not just theoretically possible.
- Full write/transport/gCTS/abapGit/RAP-scaffolding support — an entire
  category of capability RFC-only access cannot reach at all (RFC has no
  concept of source editing, transport management, or Git-backed ABAP).

## The single most valuable idea: opType vs scope separation

`authz/policy.ts`'s `ACTION_POLICY` matrix gives every tool+action **two
independent classifications**: `scope` (the user-facing permission gate —
`read`/`write`/`data`/`sql`/`transports`/`git`/`admin`) and `opType` (a
server-safety classification — `Read`/`Search`/`Query`/`FreeSQL`/`Create`/
`Update`/`Delete`/`Activate`/`Test`/`Lock`/`Intelligence`/`Workflow`/
`Transport`) that's **intrinsic to the action itself, never asserted by the
caller**.

This matters because it eliminates a whole risk class our design still has.
`call_rfc_function(function_name, parameters, mode)` requires the *caller*
to declare `mode="read"` vs `"write"`, checked against `read_allow_patterns`/
`write_allow_patterns`/`deny_patterns` — `DEFAULT_DENY_PATTERNS` exists
specifically as a heuristic backstop against a caller mislabeling a
mutating call as `mode="read"`. In arc-1's model, there's no labeling step
to get wrong: calling `SAPWrite.delete_method` *is* inherently opType
`Update`, full stop, because it's baked into which specific, well-typed
action was invoked, not asserted by the request.

This is the same principle we independently arrived at when we collapsed
`adt_read_source`/RFC-source-reading into one `read_abap_source` tool with
no transport choice exposed — arc-1 just applies it systematically, action
by action, across their entire surface, rather than to one tool.

**Where else this applies for us, concretely:** our own
`table_deny_patterns` guard on `RFC_READ_TABLE` (see below) already is a
version of this — deriving a safety signal from the `QUERY_TABLE`
parameter value itself rather than trusting the caller's declared `mode`.
It doesn't generalize to `call_rfc_function` as a whole, because arc-1's
version works specifically *because* their action set is fixed and
hand-curated (calling a named action has an intrinsic `opType` by
construction); ours is arbitrary RFC function calling, where the only
signal available for an unknown function is still its name
(`deny_patterns`). Extending this further for us would mean building a real
per-function-module classification lookup, not adopting a pattern — see
`docs/architecture.md`'s "Generic table-reader guard" section for the full
reasoning.

Directly relevant to us: they caught the *exact* shape of our
`RFC_READ_TABLE`-injection finding independently. Their `SAPSearch` tool
has a `tadir_lookup_db`/`tadir_lookup_both` mode that falls back to a raw
SQL query against table TADIR (to surface rows the ADT info-system
normally filters). They explicitly escalate *that specific mode* to the
`sql`/`FreeSQL` gate rather than inheriting the tool's default `read` gate
— the same "generic tool with a raw-query escape hatch needs its own,
stricter gate" pattern as our `table_deny_patterns` fix, independently
discovered. Good validation this is a real, recurring problem in this
space, not a one-off.

## Per-user identity: real, but narrower than it first looked

The README's "per-user identity forwarding via X.509 or OAuth2 token
exchange" is accurate but needs a caveat found only by reading the code
(`adt/oauth.ts`, `server/multi-target-basic-auth.ts`):

- **True per-user identity (OAuth2 Authorization Code flow against XSUAA)**
  exists and is well-built — each user does a real browser login, gets
  their own JWT, and that JWT (not a shared credential) is what SAP sees.
  But this is **BTP-native-cloud-ABAP-environment-specific** ("Steampunk"),
  using SAP's own `@sap-cloud-sdk/connectivity`/`@sap/xsenv`/`@sap/xssec`
  packages.
- **For Basic-Auth destinations** — the path used for classic on-premise
  systems reached via BTP Cloud Connector, i.e. the case that actually
  matches SENELEC — the code itself names it `SharedBasicSetupError` /
  "shared Basic targets". Same single-shared-identity model we have.

So: arc-1 solves the identity-forwarding problem for BTP-hosted cloud ABAP
systems. For classic on-prem ECC/S4 landscapes — which is most of the
installed base, including everything we've tested against — it has the
same limitation we do. Worth being precise about this rather than treating
"they solved it" as a blanket statement.

## Other concrete, adoptable ideas (roughly prioritized)

Status as of 2026-08-05, after acting on this list per "use the logic of
things they have, don't copy-paste":

1. ~~Tool-schema token budget enforced in CI~~ — **done**,
   `tests/test_tool_surface_budget.py`. Native pytest reimplementation of
   `check-tool-schema-budget.ts`'s *purpose* (keep `list_tools()` cheap),
   plus a per-parameter documentation check in the same spirit as
   `validate-action-policy.ts` (every tool parameter now carries its own
   `Field(description=...)`, not just the tool as a whole — this surfaced
   and fixed 11 genuinely undocumented parameters across all six tools).
   See `docs/architecture.md`'s "Tool surface guardrails" section.
2. ~~CI-enforced policy-completeness validator~~ — **principle applied,
   script not ported.** `scripts/validate-action-policy.ts` assumes a
   fixed action registry we don't have; the parameter-documentation check
   above is the shape this principle takes for a dynamic RFC-calling
   surface: nothing ships without describing itself.
3. **Two-gate server-ceiling × per-caller-profile intersection** —
   **deliberately deferred, not forgotten.** Still no second caller/trust
   level to intersect against; building this now would be speculative
   infrastructure with nothing to exercise it. See `docs/architecture.md`
   for the explicit "why not yet."
4. **`$TMP`-restricted writes by default** — **deliberately deferred.**
   Only meaningful once ADT write capability exists, which it still
   doesn't. Adopt verbatim the day that's built.
5. **`@abaplint/core`** — not evaluated this round; a real, standalone,
   local ABAP linter, independent of arc-1's own design. Worth a separate
   look if a local-lint capability is ever wanted.
6. **Layered, capability-specific opt-in flags** — not adopted. We have
   exactly one write-shaped capability today (`call_rfc_function`
   mode=write); inventing `SAP_ALLOW_*`-style flags for capabilities we
   don't yet have would be flags for nothing to gate.
7. **`husky`+`lint-staged` pre-commit enforcement** — not adopted this
   round; `ruff`/`mypy` are configured but not auto-run pre-commit.

## Where we're not behind — different bets, not gaps

- **No RFC/BAPI execution plane at all.** arc-1 cannot call arbitrary
  business function modules, post business data, or do anything
  `call_rfc_function` does. Our RFC-execution capability is a genuine,
  structural advantage theirs cannot reach by design (ADT has no concept of
  "call this BAPI").
- **`read_abap_source`'s automatic ADT-then-RFC fallback**, live-verified
  today against two independent SAP systems (SENELEC — VPN-gated, ADT
  unreachable; a public A4H trial system — no VPN, ADT also unreachable,
  RFC directly reachable) is something a pure-ADT design cannot offer: if
  ADT is down or was never activated, arc-1 simply doesn't work against
  that system. We degrade to RFC transparently. Every real-world test we've
  run so far has gone through the RFC fallback path — exactly the scenario
  a pure-ADT tool can't handle at all.

## Bottom line

arc-1 is a more complete, more mature *product* for organizations that have
already committed to ADT-reachable, typically BTP-hosted SAP landscapes and
want a governed, multi-tenant, deployable service. rfc-mcp is a leaner
*package* that works even when ADT isn't available at all (which, per our
own testing, is the common case, not the exception) and additionally
reaches business execution (RFC/BAPI) that ADT-only tools structurally
cannot. The most valuable concrete things to actually pull from arc-1,
ranked: the opType/scope separation principle, the two-gate server/profile
safety intersection model, and the `$TMP`-default-write-scope pattern for
whenever we build ADT write capability.
