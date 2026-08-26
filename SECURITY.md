# Security policy

## Supported versions

Security fixes are applied to the latest code on the default branch until a
stable release policy is published.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature when it is enabled for
the repository. If it is unavailable, open a minimal issue asking the
maintainer for a private reporting channel; do not include credentials,
customer data, SAP hostnames, exploit details, or logs in a public issue.

Please include the affected version/commit, impact, reproduction conditions,
and a suggested mitigation. Maintainers should acknowledge a report within
seven days and coordinate disclosure after a fix is available.

## Deployment boundaries

- This project ships as a local stdio server. Do not expose it over HTTP
  without MCP-compliant authorization, HTTPS, token audience validation,
  rate limiting, and per-caller authorization.
- Never pass an MCP client's token through to SAP or another upstream.
- Use a dedicated SAP service account with the narrowest possible `S_RFC`,
  `S_TABU_DIS`, and `S_TABU_NAM` authorizations. Application allowlists are
  defense in depth, not a replacement for SAP authorization.
- Keep `.env`, `.mcp.json`, RFC traces, and business-data logs out of source
  control. Enable GitHub secret scanning and push protection after publishing.
- PyRFC 3.3.1 and its expected SAP NW RFC SDK patch are unsupported upstream.
  Treat connector compatibility as an explicit operational risk.

