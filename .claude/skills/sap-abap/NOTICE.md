# Third-party component notice

This directory (`.claude/skills/sap-abap/`) is **vendored, unmodified,
third-party content** — it is not part of the RFC-MCP project's own code and
is licensed separately under its own terms.

- **Component:** `sap-abap` Claude Skill, v2.4.0
- **Source:** https://github.com/secondsky/sap-skills
  (`plugins/sap-abap/skills/sap-abap/`)
- **Author:** Eduard Jiglau (hello@sap-ai-skills.com, https://sap-ai-skills.com)
- **License:** GNU General Public License v3.0 — see `LICENSE` in this
  directory for the full text.
- **Vendored on:** 2026-08-04, verbatim, via direct raw-file download (not
  paraphrased or summarized).

## Why it's here

This skill gives an AI agent working through the RFC-MCP server accurate,
version-boundary-aware ABAP language knowledge (internal tables, ABAP SQL,
OO, exceptions, SAP LUW, RAP/EML, CDS views, unit testing, etc.) — it
complements RFC-MCP's own connectivity/access capability rather than
overlapping with it. RFC-MCP itself contains no ABAP-specific knowledge; it
only discovers, reads, and calls SAP objects.

## Licensing boundary

This subdirectory is GPL-3.0. **The rest of the RFC-MCP project is licensed
separately** (see the project root `LICENSE` file) — including this
component does not place the whole project under GPL-3.0. This mirrors the
standard pattern of vendoring a GPL-licensed third-party tool/dataset inside
a differently-licensed project, keeping the two license scopes distinct.

If you redistribute RFC-MCP, this directory must keep its own copyright
notices and `LICENSE` intact, per GPL-3.0 §5 ("Conveying Modified Source
Versions") and §4 ("Conveying Verbatim Copies") — do not strip or relicense
this specific directory.
