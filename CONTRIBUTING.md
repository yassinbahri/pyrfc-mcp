# Contributing

## Development setup

Install Python 3.11 and `uv`, then run:

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pip-audit --local --skip-editable
```

The unit suite uses fake RFC and HTTP transports; SAP credentials and PyRFC
are not required. Real SAP testing is optional and must use an approved test
system and least-privilege service account.

## Pull requests

- Keep changes focused and add regression tests for behavior changes.
- Preserve deny-by-default authorization and connection-affine transactions.
- Never add credentials, customer identifiers, RFC traces, or proprietary SAP
  SDK binaries.
- Update documentation and `CHANGELOG.md` for caller-visible changes.
- Run all checks above and ensure the package builds with `uv build`.
- Security-sensitive changes to policy, transaction handling, workflows, or
  dependencies require an explicit reviewer discussion.

By contributing, you agree that your contribution is licensed under the MIT
license, except for content within `.claude/skills/sap-abap`, which retains
its separately documented GPL-3.0 license.
