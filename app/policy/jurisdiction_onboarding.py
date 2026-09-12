# -*- coding: utf-8 -*-
"""Jurisdiction Onboarding Contract（Phase 4B-2A Step 2）—— 纯逻辑 + fail-fast。

目标：任何新管辖区（国家/州）**只填表、不改框架**。
契约文件：sources/jurisdiction-onboarding/{JURISDICTION_ID}.yaml

校验规则（fail-fast，全部测试锁定）：
    1) jurisdiction_id 必须能在 runtime registry 解析（顶层 code 或
       countries/states 子条目）；
    2) mandatory_source_roles 必须**完整覆盖**该 level 的标准角色集
       （member_state=7 项 / state=8 项）；optional 不得与 mandatory 重叠；
    3) 每个 mandatory 角色必须出现在 official_channel_map **或** known_gaps
       （不得静默遗漏）；
    4) channel 的 source_id 前缀必须符合归属约定（de_/nl_/es_/fr_/us_<st>_/…），
       或属于允许的跨域通道（eu_nim_/browser_/int_/eu_eurlex_/eur_lex/us_*）；
    5) NIM 通道必须显式标注 `discovery_layer_only: true`
       —— **NIM = EU implementation discovery layer，不得替代 national law corpus**。
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from app.policy.config import ConfigError, load_registry

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS_DIR = ROOT / "sources" / "jurisdiction-onboarding"

#: EU Member State 标准角色集（规格 §八）
MS_ROLES = (
    "MS_LEGISLATION_DATABASE", "MS_OFFICIAL_GAZETTE",
    "MS_ENVIRONMENT_MINISTRY_OR_AGENCY", "MS_WASTE_REGULATOR",
    "MS_TRANSPORT_OR_DANGEROUS_GOODS", "MS_CUSTOMS_OR_TRADE",
    "MS_STANDARDS_METADATA",
)
MS_OPTIONAL_ROLES = ("MS_EPR_AUTHORITY", "MS_ELV_AUTHORITY")

#: US State 标准角色集（规格 §九）
STATE_ROLES = (
    "STATE_LEGISLATURE", "STATE_STATUTES", "STATE_ADMIN_CODE", "STATE_REGISTER",
    "STATE_ENVIRONMENT_AGENCY", "STATE_WASTE_PROGRAM",
    "STATE_BATTERY_EPR_OR_STEWARDSHIP", "STATE_TRANSPORT_HAZMAT",
)
STATE_OPTIONAL_ROLES = ("STATE_TAX_INCENTIVES", "STATE_RECYCLING_PROGRAM")

#: level → 标准角色集
ROLES_BY_LEVEL = {
    "member_state": MS_ROLES,
    "state": STATE_ROLES,
}

#: 允许的跨域 source_id 前缀（不受 jurisdiction_id 前缀约束）
_CROSS_PREFIXES = ("eu_nim_", "browser_", "int_", "eu_eurlex_", "eur_lex",
                   "us_federal_register", "us_ecfr", "us_usc", "us_plaw",
                   "cbp_cross", "datafair")

_ACCESS_METHODS = ("api", "xml_api", "html", "sparql", "bulk", "download",
                   "nim_index", "browser", "manual")
_CHANNEL_STATUSES = ("CONNECTED", "COMPLETE", "PARTIAL", "DISCOVERED",
                     "ACCESSIBLE", "NOT_ONBOARDED", "BLOCKED")


class ChannelEntry(BaseModel):
    source_id: str
    official_url: str = ""
    access_method: str = "html"
    status: str = "DISCOVERED"
    connector: str = ""
    discovery_layer_only: bool = False
    note: str = ""

    @model_validator(mode="after")
    def _checks(self) -> "ChannelEntry":
        if self.access_method not in _ACCESS_METHODS:
            raise ValueError(f"access_method 非法：{self.access_method!r}")
        if self.status not in _CHANNEL_STATUSES:
            raise ValueError(f"channel status 非法：{self.status!r}")
        if self.source_id.startswith("eu_nim_") and not self.discovery_layer_only:
            raise ValueError(
                f"NIM 通道必须 discovery_layer_only=true（不得替代 national corpus）：{self.source_id}")
        return self


class JurisdictionName(BaseModel):
    zh: str = ""
    en: str = ""


class ContractStrategies(BaseModel):
    collector_strategy: dict[str, str] = Field(default_factory=dict)
    identity_strategy: dict = Field(default_factory=dict)
    status_strategy: str = ""
    legal_relation_strategy: str = ""


class JurisdictionContract(BaseModel):
    version: int
    jurisdiction_id: str
    jurisdiction_name: JurisdictionName
    level: str
    official_languages: list[str]
    legal_system_type: str = ""
    mandatory_source_roles: list[str]
    optional_source_roles: list[str] = Field(default_factory=list)
    official_channel_map: dict[str, list[ChannelEntry]] = Field(default_factory=dict)
    known_gaps: dict[str, str] = Field(default_factory=dict)
    collector_strategy: dict[str, str] = Field(default_factory=dict)
    identity_strategy: dict = Field(default_factory=dict)
    status_strategy: str = ""
    legal_relation_strategy: str = ""
    notes: str = ""

    # ------------------------------------------------------ 结构校验
    @model_validator(mode="after")
    def _structure(self) -> "JurisdictionContract":
        standard = ROLES_BY_LEVEL.get(self.level)
        if standard is None:
            if not self.mandatory_source_roles:
                raise ValueError(f"level={self.level!r} 须显式声明 mandatory_source_roles")
        else:
            missing = [r for r in standard if r not in self.mandatory_source_roles]
            if missing:
                raise ValueError(
                    f"mandatory_source_roles 缺标准角色：{missing}（level={self.level}）")
        overlap = set(self.mandatory_source_roles) & set(self.optional_source_roles)
        if overlap:
            raise ValueError(f"optional 与 mandatory 重叠：{sorted(overlap)}")
        if not self.official_languages:
            raise ValueError("official_languages 不得为空")
        # 每个 mandatory 角色必须给通道或缺口说明
        declared = set(self.official_channel_map) | set(self.known_gaps)
        silent = [r for r in self.mandatory_source_roles if r not in declared]
        if silent:
            raise ValueError(f"mandatory 角色既无通道也无 gap 说明：{silent}")
        unknown_gap = [r for r in self.known_gaps
                       if r not in self.mandatory_source_roles
                       and r not in self.optional_source_roles]
        if unknown_gap:
            raise ValueError(f"known_gaps 含未声明角色：{unknown_gap}")
        return self


def _allowed_source_prefix(jid: str, source_id: str) -> bool:
    if source_id.startswith(_CROSS_PREFIXES):
        return True
    if jid.startswith("US-"):                    # 州级：us_ca_* / us_mi_*
        return source_id.startswith("us_" + jid.split("-")[1].lower() + "_")
    return source_id.startswith(jid.lower() + "_")


def jurisdiction_exists(jid: str) -> bool:
    for j in load_registry().jurisdictions:
        if j.code == jid:
            return True
        if any(c.get("code") == jid for c in j.countries):
            return True
        if any(s.get("code") == jid for s in j.states):
            return True
    return False


def validate_contract(contract: JurisdictionContract) -> list[str]:
    """跨配置校验；硬错误 raise，返回软警告列表。"""
    warns: list[str] = []
    if not jurisdiction_exists(contract.jurisdiction_id):
        raise ConfigError(
            f"jurisdiction_id 不在 runtime registry：{contract.jurisdiction_id}")
    for role, entries in contract.official_channel_map.items():
        if role not in contract.mandatory_source_roles \
                and role not in contract.optional_source_roles:
            raise ConfigError(f"channel_map 含未声明角色：{role}")
        for e in entries:
            if not _allowed_source_prefix(contract.jurisdiction_id, e.source_id):
                raise ConfigError(
                    f"source_id 前缀不符合归属约定：{e.source_id}"
                    f"（jurisdiction={contract.jurisdiction_id}）")
    for role in contract.mandatory_source_roles:
        if role not in contract.official_channel_map and role not in contract.known_gaps:
            raise ConfigError(f"mandatory 角色缺通道/缺口说明：{role}")
        if role in contract.known_gaps and role in contract.official_channel_map:
            warns.append(f"{role} 同时存在通道与 gap 说明（按通道优先，gap 视为局限）")
    return warns


# ------------------------------------------------------------ 装载 / 扫描

def load_contract(jid: str, *, base: Path | None = None) -> JurisdictionContract:
    fp = (base or CONTRACTS_DIR) / f"{jid}.yaml"
    if not fp.exists():
        raise ConfigError(f"onboarding 契约不存在：{fp}")
    try:
        raw = yaml.safe_load(fp.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"契约 YAML 非法：{fp}：{exc}") from exc
    try:
        contract = JurisdictionContract(**raw)
    except Exception as exc:  # pydantic ValidationError
        raise ConfigError(f"契约校验失败：{fp}：{exc}") from exc
    if contract.jurisdiction_id != jid:
        raise ConfigError(f"契约 id 不一致：文件名 {jid} vs 内容 {contract.jurisdiction_id}")
    return contract


def list_contracts(base: Path | None = None) -> list[str]:
    d = base or CONTRACTS_DIR
    return sorted(p.stem for p in d.glob("*.yaml")) if d.exists() else []


def build_contract_registry(base: Path | None = None) -> dict:
    """全部契约 → 注册表产物（含校验与覆盖摘要）。"""
    entries, errors = [], []
    for jid in list_contracts(base):
        try:
            c = load_contract(jid, base=base)
            warns = validate_contract(c)
            entries.append(contract_summary(c, warnings=warns))
        except ConfigError as exc:
            errors.append({"jurisdiction_id": jid, "error": str(exc)})
    return {"contracts": entries, "errors": errors}


def contract_summary(c: JurisdictionContract, *, warnings: list[str] | None = None) -> dict:
    covered = 0
    roles: list[dict] = []
    for role in c.mandatory_source_roles:
        channels = c.official_channel_map.get(role, [])
        ok = any(ch.status in ("CONNECTED", "COMPLETE", "PARTIAL") for ch in channels)
        if ok:
            covered += 1
        roles.append({
            "role": role,
            "covered": ok,
            "gap": c.known_gaps.get(role, ""),
            "channels": [{"source_id": ch.source_id, "status": ch.status,
                          "access_method": ch.access_method,
                          "discovery_layer_only": ch.discovery_layer_only}
                         for ch in channels],
        })
    out = {
        "jurisdiction_id": c.jurisdiction_id,
        "name": c.jurisdiction_name.model_dump(),
        "level": c.level,
        "official_languages": c.official_languages,
        "legal_system_type": c.legal_system_type,
        "mandatory_roles": len(c.mandatory_source_roles),
        "covered_roles": covered,
        "coverage_pct": round(100.0 * covered / len(c.mandatory_source_roles), 1)
        if c.mandatory_source_roles else 0.0,
        "roles": roles,
    }
    if warnings:
        out["warnings"] = warnings
    return out
