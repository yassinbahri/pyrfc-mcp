from __future__ import annotations

import pytest
from pydantic import ValidationError

from rfc_mcp.config import (
    ADTConnectionSettings,
    PolicyMode,
    PolicySettings,
    SAPConnectionSettings,
)


@pytest.fixture(autouse=True)
def _isolate_from_dotenv(tmp_path, monkeypatch):
    """SAPConnectionSettings/PolicySettings auto-load `.env` from the cwd.
    Without this, a real, filled-in `.env` in the repo root (as usage.md's
    workflow expects you to have) leaks values into any field a test leaves
    unset, corrupting these tests' explicit inputs.
    """
    monkeypatch.chdir(tmp_path)


def test_direct_addressing_mode_valid():
    settings = SAPConnectionSettings(
        ashost="sap.example.com", sysnr="00", client="100", user="u", passwd="p"
    )
    kwargs = settings.to_pyrfc_kwargs()
    assert kwargs["ashost"] == "sap.example.com"
    assert kwargs["sysnr"] == "00"
    assert "mshost" not in kwargs


def test_load_balanced_addressing_mode_valid():
    settings = SAPConnectionSettings(
        mshost="msg.example.com",
        msserv="sapmsXX",
        group="PUBLIC",
        r3name="XXX",
        client="100",
        user="u",
        passwd="p",
    )
    kwargs = settings.to_pyrfc_kwargs()
    assert kwargs["mshost"] == "msg.example.com"
    assert "ashost" not in kwargs


def test_both_addressing_modes_rejected():
    with pytest.raises(ValidationError):
        SAPConnectionSettings(
            ashost="sap.example.com",
            sysnr="00",
            mshost="msg.example.com",
            msserv="sapmsXX",
            group="PUBLIC",
            r3name="XXX",
            client="100",
            user="u",
            passwd="p",
        )


def test_neither_addressing_mode_rejected():
    with pytest.raises(ValidationError):
        SAPConnectionSettings(client="100", user="u", passwd="p")


def test_invalid_client_format_rejected():
    with pytest.raises(ValidationError):
        SAPConnectionSettings(ashost="h", sysnr="00", client="1", user="u", passwd="p")


def test_invalid_sysnr_format_rejected():
    with pytest.raises(ValidationError):
        SAPConnectionSettings(ashost="h", sysnr="not-a-number", client="100", user="u", passwd="p")


def test_passwd_not_leaked_in_repr():
    settings = SAPConnectionSettings(
        ashost="h", sysnr="00", client="100", user="u", passwd="secret123"
    )
    assert "secret123" not in repr(settings)
    assert settings.passwd.get_secret_value() == "secret123"


def test_policy_read_write_matching_and_deny_precedence():
    policy = PolicySettings(
        mode=PolicyMode.READ_WRITE,
        read_allow_patterns=["BAPI_*"],
        write_allow_patterns=["BAPI_CUSTOMER_*"],
        deny_patterns=["BAPI_CUSTOMER_DELETE"],
    )
    assert policy.is_read_allowed("BAPI_CUSTOMER_GETLIST")
    assert policy.is_write_allowed("BAPI_CUSTOMER_CHANGE")
    assert not policy.is_write_allowed("BAPI_CUSTOMER_DELETE")
    assert not policy.is_write_allowed("BAPI_ORDER_CREATE")


def test_policy_read_only_blocks_all_writes():
    policy = PolicySettings(mode=PolicyMode.READ_ONLY, write_allow_patterns=["*"])
    assert not policy.is_write_allowed("ANYTHING")


def test_adt_disabled_by_default_requires_nothing():
    settings = ADTConnectionSettings()
    assert settings.enabled is False


def test_adt_enabled_without_credentials_rejected():
    with pytest.raises(ValidationError):
        ADTConnectionSettings(enabled=True)


def test_adt_enabled_with_credentials_valid():
    settings = ADTConnectionSettings(enabled=True, host="h", client="100", user="u", passwd="p")
    assert settings.base_url == "https://h:443"


def test_adt_base_url_respects_use_ssl_and_port():
    settings = ADTConnectionSettings(
        enabled=True, host="h", port=8001, use_ssl=False, client="100", user="u", passwd="p"
    )
    assert settings.base_url == "http://h:8001"


def test_default_deny_patterns_block_mutating_names_even_for_reads():
    # Use an explicit wildcard to exercise deny precedence independently of
    # the deny-by-default read allowlist.
    policy = PolicySettings(read_allow_patterns=["*"])
    assert not policy.is_read_allowed("BAPI_CUSTOMER_CHANGE")
    assert not policy.is_read_allowed("BAPI_SALESORDER_CREATEFROMDAT2")
    assert not policy.is_read_allowed("BAPI_MATERIAL_DELETE")
    assert not policy.is_read_allowed("SUSR_RFC_USER_INTERFACE")
    assert not policy.is_read_allowed("RFC_ABAP_INSTALL_AND_RUN")
    # A genuinely read-shaped function is unaffected.
    assert policy.is_read_allowed("BAPI_CUSTOMER_GETLIST")
    assert policy.is_read_allowed("STFC_CONNECTION")


def test_policy_denies_reads_by_default():
    policy = PolicySettings()
    assert not policy.is_read_allowed("STFC_CONNECTION")
