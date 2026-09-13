# -*- coding: utf-8 -*-
"""Convergence Layers（Phase 4B-2B0 Step 1）—— 三层收敛状态**强制分离**。

背景（2B0 审计 Q1/P0-A1）：
    2A 的 `plan_convergence.converged` 只证明「冻结 Search Plan 的搜索空间
    在该管辖地暂时无新增」，**不等于**管辖地合格。此前报告把角色覆盖
    1/7 的 SE 标记为 "convergence-ready" —— 误读通道必须关闭。

三层定义（规格 §二，测试锁定）：

    SOURCE_PLAN_CONVERGED                当前冻结 plan：连续有效轮次 + novelty 达阈值
    JURISDICTION_CONVERGENCE_ELIGIBLE    额外硬闸门（全部满足）：
        · critical Source Roles = 100%（且非 discovery-layer 通道）
        · mandatory 覆盖：EU 成员国 ≥5/7 ｜ US 州 ≥6/8
        · 独立发现路线 ≥3 类（同一数据库换关键词只算 1 类）
        · 专线 corpus identity completeness ≥90%
        · 无未决 critical source failure
    JURISDICTION_NEAR_SATURATED          仅 eligible 后 + SG 体系齐备（4B-2B 合并；
                                         本阶段 near_saturated 恒 False 并注明）

禁止：
    1 个 source role 连续两轮零新增 == jurisdiction saturated  ❌
"""

from __future__ import annotations

#: critical Source Roles（mandatory 中的法源命脉；必须**非 discovery-layer** 通道）
CRITICAL_ROLES_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "member_state": ("MS_LEGISLATION_DATABASE", "MS_OFFICIAL_GAZETTE"),
    "state": ("STATE_LEGISLATURE", "STATE_STATUTES"),
}

#: mandatory 覆盖下限（规格 §二）
MANDATORY_MIN = {"member_state": 5, "state": 6}

ROUTES_MIN = 3
IDENTITY_MIN_PCT = 90.0

#: 覆盖有效的通道状态（与 jurisdiction_onboarding.contract_summary 同口径）
_COVERED_STATUSES = ("CONNECTED", "COMPLETE", "PARTIAL")

STATE_NOT_CONVERGED = "NOT_CONVERGED"
STATE_PLAN_CONVERGED = "SOURCE_PLAN_CONVERGED"
STATE_ELIGIBLE = "JURISDICTION_CONVERGENCE_ELIGIBLE"


def route_families(rounds: list[dict]) -> list[str]:
    """轮次集合 → 独立路线类别（A/B/C/D；同一路线重跑只算 1 类）。

    输入兼容两种形态：索引条目（route_ids）与轮次记录（routes[].id）。

    独立路线口径（规格 §十）：
        A 官方枚举 ｜ B 官方全文检索 ｜ C 法律关系扩张 ｜ D 开放网缺口
        （NIM/implementation discovery 记为 N——通道就绪后计入）
    """
    fams: set[str] = set()
    for r in rounds or []:
        ids = r.get("route_ids")
        if ids is None:
            ids = [rt.get("id") for rt in r.get("routes") or []]
        for rid in ids:
            rid = str(rid or "").strip()
            if rid:
                fams.add(rid)
    return sorted(fams)


def _critical_ok(contract: dict | None, level: str) -> bool:
    crit = CRITICAL_ROLES_BY_LEVEL.get(level, ())
    if not crit:
        return False
    roles = {r.get("role"): r for r in (contract or {}).get("roles", [])}
    for role in crit:
        entry = roles.get(role)
        if not entry or not entry.get("covered"):
            return False
        # 覆盖其该角色的通道必须**非 discovery-layer**（NIM 索引不算法源）
        if not any((not ch.get("discovery_layer_only"))
                   and ch.get("status") in _COVERED_STATUSES
                   for ch in entry.get("channels") or []):
            return False
    return True


def evaluate_jurisdiction(*, jid: str, level: str, contract: dict | None,
                          plan_convergence: dict | None,
                          rounds: list[dict], identity_pct: float,
                          unresolved_critical_failures: list[dict] | None = None,
                          plan_id: str = "") -> dict:
    """单管辖地三层状态评估（纯逻辑；输入全部为已存在的读数）。"""
    unresolved = list(unresolved_critical_failures or [])
    fams = route_families(rounds)
    covered = int((contract or {}).get("covered_roles") or 0)
    total = int((contract or {}).get("mandatory_roles") or 0)
    checks = {
        "critical_roles_100": _critical_ok(contract, level),
        "mandatory_coverage_min": covered >= MANDATORY_MIN.get(level, 99),
        "route_families_min_3": len(fams) >= ROUTES_MIN,
        "identity_min_90": (identity_pct or 0.0) >= IDENTITY_MIN_PCT,
        "no_unresolved_critical_failure": not unresolved,
    }
    plan_ok = bool((plan_convergence or {}).get("converged"))
    eligible = plan_ok and all(checks.values())
    state = (STATE_ELIGIBLE if eligible
             else STATE_PLAN_CONVERGED if plan_ok
             else STATE_NOT_CONVERGED)
    return {
        "jurisdiction_id": jid,
        "level": level,
        "plan_id": plan_id,
        "plan_converged": plan_ok,
        "plan_streak": int((plan_convergence or {}).get("streak") or 0),
        "jurisdiction_eligible": eligible,
        "state": state,
        # 仅 eligible 后 + SG 体系齐备才可近饱和（4B-2B 合并；恒 False）
        "near_saturated": False,
        "near_saturated_note": "需 eligible=true 后合并 SG 体系（4B-2B）",
        "checks": checks,
        "mandatory_coverage": f"{covered}/{total}",
        "route_families": fams,
        "identity_pct": identity_pct,
        "unresolved_critical_failures": unresolved,
    }


def layer_summary(rows: dict[str, dict]) -> dict:
    """批量评估结果 → 摘要。"""
    states = [r.get("state") for r in rows.values()]
    return {
        "total": len(rows),
        "plan_converged": sum(1 for r in rows.values() if r["plan_converged"]),
        "eligible": sum(1 for r in rows.values()
                        if r["jurisdiction_eligible"]),
        "near_saturated": sum(1 for r in rows.values() if r["near_saturated"]),
        "by_state": {s: states.count(s) for s in sorted(set(states))},
    }
