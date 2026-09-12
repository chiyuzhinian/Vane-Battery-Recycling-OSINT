# -*- coding: utf-8 -*-
"""Phase 4A 配置加载 —— YAML 为单一真源，Pydantic 强校验，fail-fast。

原则（规格 §12）：
    YAML configuration → Pydantic schema → Runtime loader → Judge/Audit → Docs
Python 不得重新手工抄完整规则；配置错误必须立刻炸，而不是静默降级。

用法：
    from app.policy.config import load_topics, load_instruments, load_registry, load_acceptance
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES = ROOT / "sources"


class ConfigError(RuntimeError):
    """配置文件缺失/非法 —— 必须阻断启动（不静默降级）。"""


# ============================================================ 主题本体

class Topic(BaseModel):
    id: str
    name_en: str
    name_zh: str
    description: str = ""
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    business_relevance: str = ""
    risk_level: str = "P1"

    @field_validator("include_patterns", "exclude_patterns")
    @classmethod
    def _patterns_compile(cls, v: list[str]) -> list[str]:
        for p in v:
            try:
                re.compile(p, re.I)
            except re.error as exc:  # fail-fast
                raise ValueError(f"非法正则 {p!r}: {exc}") from exc
        return v


class TopicConfig(BaseModel):
    version: int
    topics: list[Topic]

    def by_id(self) -> dict[str, Topic]:
        return {t.id: t for t in self.topics}


# ============================================================ 文书类型

class InstrumentType(BaseModel):
    id: str
    name_zh: str
    binding_force: str
    detect_patterns: list[str] = Field(default_factory=list)


class KnownCase(BaseModel):
    match: str
    instrument_type: str
    binding_force: str
    note: str = ""


class InstrumentConfig(BaseModel):
    version: int
    instrument_types: list[InstrumentType]
    priority: list[str]
    known_cases: list[KnownCase] = Field(default_factory=list)

    def by_id(self) -> dict[str, InstrumentType]:
        return {i.id: i for i in self.instrument_types}


# ============================================================ 管辖区注册表

class SourceRole(BaseModel):
    role: str
    critical: bool = False
    expected: bool = True
    sources: list[str] = Field(default_factory=list)
    status: str = "NOT_ONBOARDED"
    note: str = ""
    gap_reason: str = ""


class Jurisdiction(BaseModel):
    code: str
    name_zh: str = ""
    name_en: str = ""
    level: str = ""
    source_roles: list[SourceRole] = Field(default_factory=list)
    # member_states / states 层用：
    role_schema: list[str] = Field(default_factory=list)
    countries: list[dict] = Field(default_factory=list)
    states: list[dict] = Field(default_factory=list)
    note: str = ""


class RegistryConfig(BaseModel):
    version: int
    jurisdictions: list[Jurisdiction]


# ============================================================ 官方端点注册表

_CONTENT_KINDS = ("html", "json", "xml", "pdf")
_METADATA_SOURCE_TYPES = ("OFFICIAL_PUBLISHER", "EU_OFFICIAL_REFERENCE",
                          "JRC_REFERENCE", "OTHER_OFFICIAL_REFERENCE", "")


class EndpointCapabilities(BaseModel):
    enumeration: bool = False
    metadata: bool = False
    fulltext: bool = False


class EndpointProbeCfg(BaseModel):
    kind: str = "http_ping"          # http_ping | json_api | html_page | download_head
    expect_keys: list[str] = Field(default_factory=list)
    no_results_key: str = ""
    timeout_s: int = 25


class EndpointCfg(BaseModel):
    id: str
    official_url: str
    official_domain: str = ""
    content_kind: str = "html"
    role_method: str = "page"        # api | page | sparql | bulk | download
    capabilities: EndpointCapabilities = Field(default_factory=EndpointCapabilities)
    metadata_source_type: str = ""   # 仅标准层使用
    probe: EndpointProbeCfg = Field(default_factory=EndpointProbeCfg)
    notes: str = ""

    @field_validator("content_kind")
    @classmethod
    def _kind_ok(cls, v: str) -> str:
        if v not in _CONTENT_KINDS:
            raise ValueError(f"content_kind 非法: {v!r}（允许 {_CONTENT_KINDS}）")
        return v

    @field_validator("metadata_source_type")
    @classmethod
    def _mst_ok(cls, v: str) -> str:
        if v not in _METADATA_SOURCE_TYPES:
            raise ValueError(f"metadata_source_type 非法: {v!r}")
        return v


class RoleEndpoints(BaseModel):
    role: str
    jurisdiction: str = ""
    source_name: str = ""
    official_domain: str = ""
    status_ceiling: str = ""        # 角色状态封顶（如 STANDARDS → PARTIAL）
    notes: str = ""
    endpoints: list[EndpointCfg] = Field(default_factory=list)


class EndpointsConfig(BaseModel):
    version: int
    defaults: dict = Field(default_factory=dict)
    roles: list[RoleEndpoints] = Field(default_factory=list)

    def by_role(self) -> dict[str, RoleEndpoints]:
        return {r.role: r for r in self.roles}


# ============================================================ 验收规则

class AcceptanceClassDef(BaseModel):
    name_en: str = ""
    name_zh: str = ""
    description: str = ""
    gates: dict = Field(default_factory=dict)
    required_any_topics: list[str] = Field(default_factory=list)
    clause_evidence_required: bool = False
    positive_examples: list[str] = Field(default_factory=list)
    negative_guard: list[str] = Field(default_factory=list)
    relevant: bool = False
    corpus: str = "rejected"


class AcceptanceConfig(BaseModel):
    version: int
    classes: dict[str, AcceptanceClassDef]
    decision_order: list[dict] = Field(default_factory=list)
    reason_codes: dict[str, str] = Field(default_factory=dict)
    background_routes: list[str] = Field(default_factory=list)


# ============================================================ 加载器

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"缺少配置文件：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 解析失败 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置必须是映射：{path}")
    return data


@lru_cache(maxsize=1)
def load_topics() -> TopicConfig:
    return TopicConfig.model_validate(_load_yaml(SOURCES / "regulatory-topics.yaml"))


@lru_cache(maxsize=1)
def load_instruments() -> InstrumentConfig:
    return InstrumentConfig.model_validate(
        _load_yaml(SOURCES / "instrument-types.yaml"))


@lru_cache(maxsize=1)
def load_registry() -> RegistryConfig:
    return RegistryConfig.model_validate(
        _load_yaml(SOURCES / "jurisdiction-registry.yaml"))


@lru_cache(maxsize=1)
def load_acceptance() -> AcceptanceConfig:
    return AcceptanceConfig.model_validate(
        _load_yaml(SOURCES / "policy-acceptance-rules.yaml"))


@lru_cache(maxsize=1)
def load_endpoints() -> EndpointsConfig:
    return EndpointsConfig.model_validate(
        _load_yaml(SOURCES / "source-endpoints.yaml"))


@lru_cache(maxsize=1)
def compiled_topics() -> dict[str, tuple[list[re.Pattern], list[re.Pattern]]]:
    """topic_id → (include_re, exclude_re)，进程内编译一次。"""
    out: dict[str, tuple[list[re.Pattern], list[re.Pattern]]] = {}
    for t in load_topics().topics:
        out[t.id] = (
            [re.compile(p, re.I) for p in t.include_patterns],
            [re.compile(p, re.I) for p in t.exclude_patterns],
        )
    return out


def config_status() -> dict:
    """供 audit CLI / 测试查看配置健康度。"""
    status: dict = {"ok": True, "errors": []}
    for name, fn in (("topics", load_topics), ("instruments", load_instruments),
                     ("registry", load_registry), ("acceptance", load_acceptance),
                     ("endpoints", load_endpoints)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            status["ok"] = False
            status["errors"].append(f"{name}: {type(exc).__name__}: {exc}")
    return status


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    s = config_status()
    print("配置健康度:", "✅ 全部通过" if s["ok"] else "❌")
    for e in s["errors"]:
        print("  ", e)
    if s["ok"]:
        t = load_topics()
        print(f"  主题 {len(t.topics)} 个（{t.topics[0].id}…{t.topics[-1].id}）")
        i = load_instruments()
        print(f"  文书类型 {len(i.instrument_types)} 个；判例锚点 {len(i.known_cases)} 条")
        r = load_registry()
        print(f"  管辖区 {len(r.jurisdictions)} 个"
              f"（含{'/'.join(j.code for j in r.jurisdictions)}）")
        a = load_acceptance()
        print(f"  验收类 {list(a.classes)}；判定步骤 {len(a.decision_order)}")
