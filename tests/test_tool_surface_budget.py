"""CI-style guardrails on the tool surface itself, not just individual tool
behaviour. Two checks, both inspired by ideas found reviewing arc-1
(docs/competitor_analysis_arc1.md) but reimplemented natively rather than
ported: their `check-tool-schema-budget.ts` keeps each tool's JSON schema
small enough not to waste an agent's context window on `list_tools()`, and
their `validate-action-policy.ts` makes it structurally impossible to ship a
new action without a declared safety classification. Our RFC layer is fully
dynamic (any function module, not a fixed action registry), so their exact
mechanism doesn't transfer — but "a new tool must earn its place in the
schema, and must document itself" does.

Budgets below are set with real headroom over current measured sizes (see
git history of this file's first commit), not tuned to the exact bytes
today - they exist to catch *future* schema bloat (e.g. someone dumping a
long enum into a tool's input schema), not to be re-tuned every time a
docstring grows by a sentence.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

# Generous headroom over the largest tool measured today (~2.8KB for
# get_rfc_function_interface) - this should only ever fire on real bloat.
MAX_SINGLE_TOOL_SCHEMA_CHARS = 6_000

# Generous headroom over the full six-tool surface measured today (~8.7KB
# total) - an agent lists every tool up front, so the whole surface shares
# one budget, not just each tool individually.
MAX_TOTAL_SCHEMA_CHARS = 20_000

# A description short enough to be a stub ("TODO", "does the thing") rather
# than something that actually tells a calling agent when to reach for this
# tool and what it needs.
MIN_DESCRIPTION_CHARS = 40


async def _list_tools():
    from rfc_mcp.mcp.server import mcp

    return await mcp.list_tools()


async def test_no_single_tool_schema_exceeds_budget():
    tools = await _list_tools()
    for tool in tools:
        schema_size = len(json.dumps(tool.model_dump()))
        assert schema_size <= MAX_SINGLE_TOOL_SCHEMA_CHARS, (
            f"{tool.name}'s schema is {schema_size} chars, over the "
            f"{MAX_SINGLE_TOOL_SCHEMA_CHARS} budget - trim its description "
            "or parameter schema before it eats into every agent's context "
            "window on every session."
        )


async def test_total_tool_surface_stays_within_budget():
    tools = await _list_tools()
    total = sum(len(json.dumps(tool.model_dump())) for tool in tools)
    assert total <= MAX_TOTAL_SCHEMA_CHARS, (
        f"Full tool surface is {total} chars, over the {MAX_TOTAL_SCHEMA_CHARS} "
        "budget - list_tools() pays this cost on every agent session "
        "regardless of which tools actually get called."
    )


async def test_every_tool_has_a_substantive_description():
    """A tool with no description, or a stub one, forces a calling agent to
    guess when to use it from the name alone - exactly the kind of ambiguity
    that pushed read_abap_source's transport choice inside the tool instead
    of leaving it to prose (see docs/adt_rfc_integration_plan.md)."""
    tools = await _list_tools()
    for tool in tools:
        description = tool.description or ""
        assert len(description.strip()) >= MIN_DESCRIPTION_CHARS, (
            f"{tool.name} has no substantive description ({len(description)} "
            "chars) - a calling agent has nothing but the name to decide "
            "when to use it."
        )


async def test_every_tool_parameter_is_documented():
    """Every property in every tool's input schema must carry its own
    description, not just the tool as a whole - matches the granularity
    arc-1's ACTION_POLICY documents at (per-action, not just per-tool)."""
    tools = await _list_tools()
    undocumented = []
    for tool in tools:
        properties = tool.input_schema.get("properties", {})
        for param_name, param_schema in properties.items():
            has_description = bool(param_schema.get("description"))
            # A $ref'd/nested model (e.g. a parameters dict) documents itself
            # at its own field definitions rather than needing a description
            # on the reference site.
            if not has_description and "$ref" not in param_schema and "allOf" not in param_schema:
                undocumented.append(f"{tool.name}.{param_name}")
    assert not undocumented, f"Undocumented tool parameters: {undocumented}"
