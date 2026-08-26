from __future__ import annotations

import pytest

from rfc_mcp.config import PolicyMode, PolicySettings
from rfc_mcp.execution.policy import ExecutionPolicy, PolicyDeniedError


def test_read_denied_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY))
    with pytest.raises(PolicyDeniedError):
        policy.authorize("STFC_CONNECTION", "read")


def test_read_allowed_by_explicit_pattern():
    policy = ExecutionPolicy(
        PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["STFC_*"])
    )
    policy.authorize("STFC_CONNECTION", "read")


def test_read_denied_when_pattern_matches_deny():
    policy = ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_ONLY,
            read_allow_patterns=["*"],
            deny_patterns=["STFC_*"],
        )
    )
    with pytest.raises(PolicyDeniedError):
        policy.authorize("STFC_CONNECTION", "read")


def test_write_blocked_in_read_only_mode():
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, write_allow_patterns=["*"]))
    with pytest.raises(PolicyDeniedError):
        policy.authorize("BAPI_CUSTOMER_CHANGE", "write")


def test_write_allowed_when_mode_and_pattern_match():
    # deny_patterns explicitly cleared: this test targets the allow-list
    # mechanism in isolation. BAPI_CUSTOMER_CHANGE matches
    # DEFAULT_DENY_PATTERNS' "*_CHANGE*", which is exercised separately by
    # test_deny_pattern_overrides_write_allow and
    # test_default_deny_patterns_block_mislabeled_read_of_mutating_function.
    policy = ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_WRITE, write_allow_patterns=["BAPI_CUSTOMER_*"], deny_patterns=[]
        )
    )
    policy.authorize("BAPI_CUSTOMER_CHANGE", "write")


def test_write_blocked_when_not_in_allow_list():
    policy = ExecutionPolicy(
        PolicySettings(mode=PolicyMode.READ_WRITE, write_allow_patterns=["BAPI_CUSTOMER_*"])
    )
    with pytest.raises(PolicyDeniedError):
        policy.authorize("BAPI_ORDER_CREATE", "write")


def test_deny_pattern_overrides_write_allow():
    policy = ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_WRITE,
            write_allow_patterns=["BAPI_CUSTOMER_*"],
            deny_patterns=["BAPI_CUSTOMER_DELETE"],
        )
    )
    with pytest.raises(PolicyDeniedError):
        policy.authorize("BAPI_CUSTOMER_DELETE", "write")


def test_transaction_control_requires_read_write_mode():
    with pytest.raises(PolicyDeniedError):
        ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY)).authorize_transaction_control()

    ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_WRITE)).authorize_transaction_control()


def test_unknown_mode_raises_value_error():
    policy = ExecutionPolicy(PolicySettings())
    with pytest.raises(ValueError):
        policy.authorize("X", "delete")


def test_default_deny_patterns_block_mislabeled_read_of_mutating_function():
    # Default PolicySettings(): a caller declaring mode="read" on a function
    # that's actually mutating (e.g. mislabeled by an agent) should still be
    # blocked by DEFAULT_DENY_PATTERNS, not silently allowed through
    # read_allow_patterns=["*"].
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    with pytest.raises(PolicyDeniedError):
        policy.authorize("BAPI_CUSTOMER_CHANGE", "read")


def test_generic_table_reader_blocks_sensitive_table_by_default():
    # RFC_READ_TABLE itself matches no DEFAULT_DENY_PATTERNS entry (its name
    # isn't a mutating verb) — this is the second, table-name-level guard
    # that catches it via the QUERY_TABLE parameter instead.
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    with pytest.raises(PolicyDeniedError):
        policy.authorize("RFC_READ_TABLE", "read", {"QUERY_TABLE": "USR02"})


def test_generic_table_reader_allows_non_sensitive_table():
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    policy.authorize("RFC_READ_TABLE", "read", {"QUERY_TABLE": "T000"})


def test_generic_table_reader_check_is_case_insensitive_on_param_key_and_table():
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    with pytest.raises(PolicyDeniedError):
        policy.authorize("rfc_read_table", "read", {"query_table": "agr_users"})


def test_generic_table_reader_deny_patterns_are_overridable():
    policy = ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_ONLY,
            read_allow_patterns=["*"],
            table_deny_patterns=[],
        )
    )
    policy.authorize("RFC_READ_TABLE", "read", {"QUERY_TABLE": "USR02"})


def test_generic_table_reader_guard_does_not_affect_non_reader_functions():
    # A function that merely happens to take a QUERY_TABLE-named param but
    # isn't in generic_table_reader_functions must not trigger this guard.
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    policy.authorize("STFC_CONNECTION", "read", {"QUERY_TABLE": "USR02"})


def test_missing_query_table_parameter_does_not_crash():
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    policy.authorize("RFC_READ_TABLE", "read", {})
    policy.authorize("RFC_READ_TABLE", "read")
