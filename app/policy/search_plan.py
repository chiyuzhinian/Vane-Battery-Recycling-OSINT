# -*- coding: utf-8 -*-
"""Search Plan Versioning（Phase 4B-2A Step 1）—— 纯逻辑 + fail-fast 校验。

背景（Phase 4B-1 真实教训）：
    连续轮次之间搜索空间发生变化（换词表 / 扩 CELEX 年段）却仍计入同一
    convergence streak —— 实验设计缺陷。本模块引入：

        search_plan_id + search_plan_hash（sha256，覆盖 11 类语义字段）

    只有 **plan_hash 完全一致** 的 MODE B（convergence_validation）轮次
    才允许组成 streak；搜索空间任何变化 → 新 plan_id（强制 reset）。

hash 覆盖（规格 §二，至少以下字段）：
    jurisdiction / scope / source_roles / source_endpoints /
    query_taxonomy_version / language_set / time_window / year_segments /
    discovery_routes / acceptance_rule_version / dedupe_rule_version
    （另含 plan_id：一个 plan 文件 ↔ 一个 hash，避免同名混淆）

非语义字段（不参与 hash）：created_at / notes / version（文件 schema 版本）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from app.policy.config import ConfigError, load_acceptance, load_endpoints
from app.policy.rounds import DEDUPE_RULE_VERSION

ROOT = Path(__file__).resolve().parent.parent.parent
PLANS_DIR = ROOT / "sources" / "search-plans"

#: 标准 scope 枚举（jurisdiction 级 plan 的 scope 等于 jurisdiction_id 本身）
STANDARD_SCOPES = ("EU_SUPRANATIONAL", "EU_MEMBER_STATES",
                   "US_FEDERAL", "US_STATES")
VALID_ROUTES = ("A", "B", "C", "D")


class TimeWindow(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from")
    to: str

    @field_validator("from_", "to")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        if len(v) != 10 or v[4] != "-" or v[7] != "-":
            raise ValueError(f"time_window 必须是 ISO 日期（YYYY-MM-DD）：{v!r}")
        return v


class PlanRole(BaseModel):
    role: str
    critical: bool = False


class PlanQuerySet(BaseModel):
    fr_agencies: list[str] = Field(default_factory=list)
    fr_terms: list[str] = Field(default_factory=list)
    eu_keywords: list[str] = Field(default_factory=list)
    cross_terms: list[str] = Field(default_factory=list)
    basel_publications: bool = False

    def total_queries(self) -> int:
        return (len(self.fr_agencies) + len(self.fr_terms)
                + len(self.eu_keywords) + len(self.cross_terms)
                + int(self.basel_publications))


class SearchPlan(BaseModel):
    version: int
    plan_id: str
    jurisdiction: str
    scope: str
    source_roles: list[PlanRole]
    source_endpoints: list[str] = Field(default_factory=list)
    critical_sources: list[str] = Field(default_factory=list)
    query_taxonomy_version: str
    query_set: PlanQuerySet = Field(default_factory=PlanQuerySet)
    language_set: list[str]
    time_window: TimeWindow
    year_segments: list[str] = Field(default_factory=list)
    discovery_routes: list[str]
    acceptance_rule_version: str
    dedupe_rule_version: str
    notes: str = ""                  # 非语义（不参与 hash）
    created_at: str = ""             # 非语义（不参与 hash）

    # -------------------------------------------------- hash
    def semantic_payload(self) -> dict:
        """参与 hash 的全量语义字段（稳定排序由 canonical json 保证）。"""
        return {
            "plan_id": self.plan_id,
            "jurisdiction": self.jurisdiction,
            "scope": self.scope,
            "source_roles": [r.model_dump() for r in self.source_roles],
            "source_endpoints": list(self.source_endpoints),
            "critical_sources": list(self.critical_sources),
            "query_taxonomy_version": self.query_taxonomy_version,
            "query_set": self.query_set.model_dump(),
            "language_set": list(self.language_set),
            "time_window": self.time_window.model_dump(by_alias=True),
            "year_segments": list(self.year_segments),
            "discovery_routes": list(self.discovery_routes),
            "acceptance_rule_version": self.acceptance_rule_version,
            "dedupe_rule_version": self.dedupe_rule_version,
        }

    def plan_hash(self) -> str:
        payload = json.dumps(self.semantic_payload(), sort_keys=True,
                             ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ 装载

def _plan_path(plan_id: str, base: Path | None = None) -> Path:
    return (base or PLANS_DIR) / f"{plan_id}.yaml"


def load_plan(plan_id: str, *, base: Path | None = None) -> SearchPlan:
    """装载 + 结构校验（fail-fast）。文件缺失/字段非法/plan_id 不符 → ConfigError。"""
    fp = _plan_path(plan_id, base)
    if not fp.exists():
        raise ConfigError(f"search-plan 不存在：{fp}")
    try:
        raw = yaml.safe_load(fp.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"search-plan YAML 非法：{fp}：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"search-plan 顶层必须是映射：{fp}")
    try:
        plan = SearchPlan(**raw)
    except Exception as exc:  # pydantic ValidationError
        raise ConfigError(f"search-plan 校验失败：{fp}：{exc}") from exc
    if plan.plan_id != plan_id:
        raise ConfigError(
            f"plan_id 不一致：文件名 {plan_id} vs 内容 {plan.plan_id}")
    return plan


def list_plans(base: Path | None = None) -> list[str]:
    d = base or PLANS_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


# ------------------------------------------------------------ 校验（跨配置）

def validate_plan(plan: SearchPlan, *, check_versions: bool = True) -> list[str]:
    """语义/跨配置校验。返回 warning 列表；硬错误直接 raise ConfigError。"""
    warns: list[str] = []
    # scope
    if plan.scope not in STANDARD_SCOPES and plan.scope != plan.jurisdiction:
        raise ConfigError(
            f"scope 非法：{plan.scope!r}（须为标准 scope 之一，或等于 jurisdiction_id）")
    # routes
    if not plan.discovery_routes:
        raise ConfigError("discovery_routes 不得为空（搜索空间必须显式冻结）")
    bad_routes = [r for r in plan.discovery_routes if r not in VALID_ROUTES]
    if bad_routes:
        raise ConfigError(f"discovery_routes 含非法路线：{bad_routes}")
    # query 物量
    if plan.query_set.total_queries() == 0 and not plan.year_segments:
        raise ConfigError("query_set 与 year_segments 不能同时为空（plan 无搜索物量）")
    # language
    if not plan.language_set:
        raise ConfigError("language_set 不得为空（冻结语言集合）")
    # time window
    if plan.time_window.from_ > plan.time_window.to:
        raise ConfigError("time_window.from 晚于 to")
    # roles/endpoints 必须存在于官方端点注册表
    ep_cfg = load_endpoints()
    by_role = ep_cfg.by_role()
    for pr in plan.source_roles:
        if pr.role not in by_role:
            raise ConfigError(f"source_roles 含注册表不存在的角色：{pr.role}")
    known_eps = {e.id: r.role for r in ep_cfg.roles for e in r.endpoints}
    plan_roles = {pr.role for pr in plan.source_roles}
    for eid in plan.source_endpoints:
        if eid not in known_eps:
            raise ConfigError(f"source_endpoints 含注册表不存在的端点：{eid}")
        if known_eps[eid] not in plan_roles:
            raise ConfigError(
                f"端点 {eid} 属于角色 {known_eps[eid]}，未在 plan.source_roles 中声明")
    # critical_sources 与 critical 角色的一致性（软警告）
    crit_roles = {pr.role for pr in plan.source_roles if pr.critical}
    if crit_roles and not plan.critical_sources:
        warns.append("存在 critical 角色但 critical_sources（source_id 级）为空——"
                     "失效判定将退化为仅靠角色级信息")
    # 版本一致性
    if check_versions:
        acc_ver = str(load_acceptance().version)
        if plan.acceptance_rule_version != acc_ver:
            raise ConfigError(
                f"acceptance_rule_version 不匹配：plan={plan.acceptance_rule_version} "
                f"vs 当前配置={acc_ver}（改规则必须新 plan）")
        if plan.dedupe_rule_version != DEDUPE_RULE_VERSION:
            raise ConfigError(
                f"dedupe_rule_version 不匹配：plan={plan.dedupe_rule_version} "
                f"vs 当前常量={DEDUPE_RULE_VERSION}")
    return warns


def plan_registry_entry(plan: SearchPlan, *, source_file: str = "") -> dict:
    return {
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash(),
        "jurisdiction": plan.jurisdiction,
        "scope": plan.scope,
        "routes": list(plan.discovery_routes),
        "query_taxonomy_version": plan.query_taxonomy_version,
        "language_set": list(plan.language_set),
        "time_window": plan.time_window.model_dump(by_alias=True),
        "year_segments": list(plan.year_segments),
        "source_file": source_file or f"{plan.plan_id}.yaml",
        "created_at": plan.created_at,
    }


def build_registry(base: Path | None = None) -> dict:
    """扫描全部 plan → 注册表（含 hash 与校验警告）。"""
    entries, errors = [], []
    for pid in list_plans(base):
        try:
            plan = load_plan(pid, base=base)
            warns = validate_plan(plan)
            entry = plan_registry_entry(plan)
            if warns:
                entry["warnings"] = warns
            entries.append(entry)
        except ConfigError as exc:
            errors.append({"plan_id": pid, "error": str(exc)})
    return {"plans": entries, "errors": errors}
