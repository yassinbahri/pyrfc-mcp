"""Configuration models. Pure pydantic — no pyrfc import, no network I/O."""

from __future__ import annotations

import fnmatch
from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PolicyMode(StrEnum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class SAPConnectionSettings(BaseSettings):
    """Connection parameters for pyrfc.Connection.

    Exactly one addressing mode must be supplied: direct application server
    (ashost + sysnr) or load-balanced message server (mshost + msserv + group
    + r3name).
    """

    model_config = SettingsConfigDict(env_prefix="RFC_MCP_SAP_", env_file=".env", extra="ignore")

    ashost: str | None = None
    sysnr: str | None = Field(default=None, pattern=r"^\d{2}$")

    mshost: str | None = None
    msserv: str | None = None
    group: str | None = None
    r3name: str | None = None

    client: str = Field(pattern=r"^\d{3}$")
    user: str
    passwd: SecretStr
    lang: str = "EN"

    pool_size: int = Field(default=4, ge=1, le=32)
    pool_acquire_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_base_seconds: float = Field(default=0.5, gt=0)

    rstrip: bool = True
    dtime: bool = False

    @model_validator(mode="after")
    def _check_addressing_mode(self) -> SAPConnectionSettings:
        direct = bool(self.ashost and self.sysnr)
        load_balanced = bool(self.mshost and self.msserv and self.group and self.r3name)
        if direct == load_balanced:
            raise ValueError(
                "Provide exactly one addressing mode: (ashost + sysnr) for a direct "
                "application server connection, or (mshost + msserv + group + r3name) "
                "for load-balanced connections via message server."
            )
        return self

    def to_pyrfc_kwargs(self) -> dict[str, str]:
        """Build the kwargs pyrfc.Connection(**kwargs) expects."""
        base = {
            "client": self.client,
            "user": self.user,
            "passwd": self.passwd.get_secret_value(),
            "lang": self.lang,
        }
        if self.ashost:
            assert self.sysnr is not None  # validated by _check_addressing_mode
            base.update(ashost=self.ashost, sysnr=self.sysnr)
        else:
            assert self.mshost is not None  # validated by _check_addressing_mode
            assert self.msserv is not None
            assert self.group is not None
            assert self.r3name is not None
            base.update(
                mshost=self.mshost,
                msserv=self.msserv,
                group=self.group,
                r3name=self.r3name,
            )
        return base

    def connection_config(self) -> dict[str, bool]:
        """The `config={...}` dict pyrfc.Connection accepts for result shaping."""
        return {"rstrip": self.rstrip, "dtime": self.dtime}


DEFAULT_DENY_PATTERNS: list[str] = [
    # Common ABAP/BAPI mutating-verb naming conventions. This is a heuristic,
    # not a guarantee — RFC has no universal "this function only reads" flag
    # (see docs/architecture.md). It exists as defense in depth for the case
    # where a caller declares mode="read" on a function that actually
    # mutates data: policy.authorize() applies deny_patterns to BOTH read
    # and write calls, so these block regardless of the declared mode.
    "*_CREATE*",
    "*_CHANGE*",
    "*_UPDATE*",
    "*_DELETE*",
    "*_SAVE*",
    "*_POST*",
    "*_REMOVE*",
    "*_MODIFY*",
    "*_CANCEL*",
    "*_MAINTAIN*",
    "*_INSERT*",
    "*_LOCK*",
    "*_RELEASE*",
    "*_REVERSE*",
    "*_CLOSE*",
    "*_APPROVE*",
    "*_REJECT*",
    "*_SUBMIT*",
    "*_ADD*",
    "*_ASSIGN*",
    # Explicitly dangerous regardless of naming convention.
    "BAPI_TRANSACTION_COMMIT",
    "BAPI_TRANSACTION_ROLLBACK",
    "RFC_ABAP_INSTALL_AND_RUN",
    "SUSR_*",
]


DEFAULT_SENSITIVE_TABLE_PATTERNS: list[str] = [
    # Authentication/authorization-relevant tables. deny_patterns above
    # never blocks RFC_READ_TABLE itself — its own name matches no
    # mutating-verb pattern, since it's a "read" by name. But RFC_READ_TABLE
    # takes the table to dump as a *parameter* (QUERY_TABLE), so a
    # function-name-only blocklist is structurally blind to *what* it reads:
    # nothing stops mode="read" from dumping USR02, AGR_USERS, UST04, etc.
    # This is that second, table-name-level guard. Same philosophy as
    # DEFAULT_DENY_PATTERNS: defense in depth, not a substitute for
    # SAP-side S_TABU_DIS/S_TABU_NAM authorization scoped on the RFC user.
    "USR*",  # user master + password-history tables (USR02, USRPWDHISTORY, ...)
    "UST04",  # direct profile assignments (SAP_ALL/SAP_NEW live here)
    "UST10*",  # composite profiles
    "USH02",  # user master change history
    "AGR_*",  # PFCG role definitions/assignments (AGR_USERS, AGR_TCODES, ...)
    "DEVACCESS",  # developer access keys
    "RFCDES",  # RFC destination definitions (can embed credentials)
    "SNC*",  # Secure Network Communication config
    "RSECTAB",  # table-level authorization config
]

GENERIC_TABLE_READER_FUNCTIONS: list[str] = [
    # Functions that read an arbitrary table named by a caller-supplied
    # parameter (conventionally QUERY_TABLE). DEFAULT_DENY_PATTERNS can't
    # catch these by function name, since the risk is entirely in *which
    # table* gets passed in, not the function's own name. RFC_READ_TABLE is
    # SAP-standard and present on every system; the others are commonly
    # deployed clones/enhancements sharing the same QUERY_TABLE convention
    # (unverified on any specific target system — included for defense in
    # depth, not because their presence is confirmed).
    "RFC_READ_TABLE",
    "RFC_GET_TABLE_ENTRIES",
    "/SDF/RFC_READ_TABLE2",
    "BBP_RFC_READ_TABLE",
]


class PolicySettings(BaseSettings):
    """Read/write execution policy. Fail-closed: unclassified functions are
    treated as writes and blocked unless mode is read_write AND the function
    name matches an allow pattern and no deny pattern. deny_patterns
    defaults to DEFAULT_DENY_PATTERNS (a heuristic mutating-verb blocklist)
    rather than empty — override via RFC_MCP_POLICY_DENY_PATTERNS if you
    need to widen it deliberately. The real, deterministic backstop is
    SAP-side S_RFC authorization scoped to only the function groups you
    intend to expose (see docs/setup.md) — this list is defense in depth on
    top of that, not a substitute for it.

    table_deny_patterns is a second, independent guard specifically for
    generic table-reader functions (see GENERIC_TABLE_READER_FUNCTIONS) —
    deny_patterns operates on the function name being called, this operates
    on the table name it's asked to read, since those are orthogonal risks
    for this class of function.
    """

    model_config = SettingsConfigDict(env_prefix="RFC_MCP_POLICY_", env_file=".env", extra="ignore")

    mode: PolicyMode = PolicyMode.READ_ONLY
    # Deny by default. Operators must deliberately name the RFCs/function
    # groups that this server may expose; SAP-side S_RFC remains the final
    # authorization boundary.
    read_allow_patterns: list[str] = Field(default_factory=list)
    write_allow_patterns: list[str] = Field(default_factory=list)
    deny_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_DENY_PATTERNS))
    table_deny_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_TABLE_PATTERNS)
    )
    generic_table_reader_functions: list[str] = Field(
        default_factory=lambda: list(GENERIC_TABLE_READER_FUNCTIONS)
    )

    def is_denied(self, function_name: str) -> bool:
        return any(
            fnmatch.fnmatchcase(function_name.upper(), p.upper()) for p in self.deny_patterns
        )

    def is_read_allowed(self, function_name: str) -> bool:
        if self.is_denied(function_name):
            return False
        return any(
            fnmatch.fnmatchcase(function_name.upper(), p.upper()) for p in self.read_allow_patterns
        )

    def is_write_allowed(self, function_name: str) -> bool:
        if self.mode is not PolicyMode.READ_WRITE:
            return False
        if self.is_denied(function_name):
            return False
        return any(
            fnmatch.fnmatchcase(function_name.upper(), p.upper()) for p in self.write_allow_patterns
        )

    def is_generic_table_reader(self, function_name: str) -> bool:
        upper = function_name.upper()
        return any(upper == f.upper() for f in self.generic_table_reader_functions)

    def is_table_denied(self, table_name: str) -> bool:
        return any(
            fnmatch.fnmatchcase(table_name.upper(), p.upper()) for p in self.table_deny_patterns
        )


class ADTConnectionSettings(BaseSettings):
    """Connection parameters for the ADT (ABAP Development Tools) REST API —
    the inspection-plane complement to RFC's execution-plane access (see
    docs/adt_rfc_integration_plan.md). Disabled by default and all fields
    are optional unless enabled=True: unlike SAPConnectionSettings, most
    deployments of this server won't have ADT services activated/reachable
    (see docs/adt_rfc_integration_plan.md's "Status" note — that was true
    for the system this was built against), so requiring these values
    unconditionally would break every deployment that only wants RFC.

    Read-only by design: this settings class and the client it configures
    have no write/activate capability. Source-editing ADT calls are a
    separate, not-yet-built, and deliberately harder-gated concern — see
    the plan doc.
    """

    model_config = SettingsConfigDict(env_prefix="RFC_MCP_ADT_", env_file=".env", extra="ignore")

    enabled: bool = False
    host: str | None = None
    port: int = Field(default=443, ge=1, le=65535)
    use_ssl: bool = True
    verify_ssl: bool = True
    client: str | None = Field(default=None, pattern=r"^\d{3}$")
    user: str | None = None
    passwd: SecretStr | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_base_seconds: float = Field(default=0.5, gt=0)

    @model_validator(mode="after")
    def _check_required_when_enabled(self) -> ADTConnectionSettings:
        if self.enabled and not (self.host and self.client and self.user and self.passwd):
            raise ValueError(
                "RFC_MCP_ADT_ENABLED=true requires host, client, user and passwd to all be set."
            )
        return self

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.host}:{self.port}"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RFC_MCP_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    discovery_cache_ttl_seconds: float = Field(default=300.0, gt=0)
    structure_resolution_max_depth: int = Field(default=8, ge=1, le=32)
    transaction_ttl_seconds: float = Field(default=300.0, gt=0, le=3600)

    sap: SAPConnectionSettings = Field(default_factory=SAPConnectionSettings)  # type: ignore[arg-type]
    policy: PolicySettings = Field(default_factory=PolicySettings)
    adt: ADTConnectionSettings = Field(default_factory=ADTConnectionSettings)
