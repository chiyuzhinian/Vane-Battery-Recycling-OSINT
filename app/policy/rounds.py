# -*- coding: utf-8 -*-
"""Discovery Rounds（Phase 4B-1 Step 10）—— 纯逻辑。

指标口径（用户修正 2026-09-12）：
    raw_result_count            原始检索结果数（各源返回）
    unique_candidate_count      去重后的候选
    accepted_count              入选（acceptance_class != D；C 进背景语料）
    new_unique_accepted_count   本轮**新**且入选（不在既有语料）
    duplicate_accepted_count    入选但已在语料（重复发现）
    rejected_count              判 D（排除）

    raw_yield             = new_unique_accepted / raw_result_count        ← 仅检索效率
    accepted_novelty_rate = new_unique_accepted / (new_unique_accepted + duplicate_accepted)
                                                                          ← **SG8 主判据**

收敛：连续 ≥2 轮 accepted_novelty_rate < 2% 且该轮**无 source_failure**。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: 入选定义：除 D 之外的分类都进入语料（C = background corpus）
ACCEPTED_CLASSES = ("A1", "A2", "B", "C")

NOVEL_RATE_THRESHOLD = 0.02
CONVERGENCE_ROUNDS = 2

# ---------------------------------------------------------- Phase 4B-2A 协议

#: 去重规则版本（参与 search_plan_hash；改规则必须新 plan）
DEDUPE_RULE_VERSION = "v1"

#: 轮次模式：MODE A 扩张（不入 SG8）｜ MODE B 验证（唯一可组 streak）｜ legacy（4B-1 历史）
ROUND_MODES = ("discovery_expansion", "convergence_validation", "legacy")

#: 轮次有效性：FULL（可计数）｜ PARTIAL（不计且中断扫描）｜ INVALID（critical 失败作废）
VALIDITY_ENUM = ("FULL", "PARTIAL", "INVALID")

#: 高风险 B 主题（出现即触发高价值护栏，不得宣布 SATURATED）
HIGH_RISK_B_TOPICS = ("T01", "T02", "T05", "T10", "T13")

_ROUTE_CLASSES = ("A1", "A2", "B", "C", "D")


def accepted_novelty_rate(new_accepted: int, duplicate_accepted: int) -> float:
    denom = new_accepted + duplicate_accepted
    return round(new_accepted / denom, 4) if denom else 0.0


def raw_yield(new_accepted: int, raw_results: int) -> float:
    return round(new_accepted / raw_results, 4) if raw_results else 0.0


@dataclass
class RouteResult:
    id: str
    name: str
    queries: list[str] = field(default_factory=list)
    raw_found: int = 0
    candidates: list[dict] = field(default_factory=list)      # {evidence_id,...}
    source_failures: list[dict] = field(default_factory=list)
    #: source_id → 成功调用次数（失效判定：critical 源失败且零成功 → INVALID）
    source_success: dict[str, int] = field(default_factory=dict)
    #: 重试后恢复的瞬态失败次数（恢复 → 不判无效，仅记录）
    transient_recovered: int = 0

    def as_dict(self, *, classified: dict[str, str],
                existing_ids: set[str],
                topics_by_id: dict[str, list[str]] | None = None) -> dict:
        """classified: evidence_id → acceptance_class；existing_ids: 既有语料 id。

        topics_by_id: evidence_id → topic_ids（用于 new_high_risk_B 计数）。
        """
        uniq: dict[str, dict] = {}
        for c in self.candidates:
            uniq.setdefault(c["evidence_id"], c)
        new_accepted = dup_accepted = rejected = 0
        new_docs_total = 0
        per_class = {k: 0 for k in _ROUTE_CLASSES}
        new_by_class = {k: 0 for k in _ROUTE_CLASSES}
        new_high_risk_b = 0
        topics_by_id = topics_by_id or {}
        for eid in uniq:
            cls = classified.get(eid, "D")
            per_class[cls] = per_class.get(cls, 0) + 1
            accepted = cls in ACCEPTED_CLASSES
            if accepted:
                if eid in existing_ids:
                    dup_accepted += 1
                else:
                    new_accepted += 1
                    new_by_class[cls] = new_by_class.get(cls, 0) + 1
                    if cls == "B":
                        hit = set(topics_by_id.get(eid) or []) & set(HIGH_RISK_B_TOPICS)
                        if hit:
                            new_high_risk_b += 1
            else:
                rejected += 1
            if eid not in existing_ids:
                new_docs_total += 1
        return {
            "id": self.id, "name": self.name, "queries": self.queries,
            "raw_found": self.raw_found,
            "unique_candidate_count": len(uniq),
            "accepted_count": new_accepted + dup_accepted,
            "new_unique_accepted_count": new_accepted,
            "duplicate_accepted_count": dup_accepted,
            "rejected_count": rejected,
            "new_documents_total": new_docs_total,
            "accepted_by_class": {k: v for k, v in per_class.items() if v},
            "new_by_class": {k: v for k, v in new_by_class.items() if v},
            "new_high_risk_B": new_high_risk_b,
            "source_failures": self.source_failures,
            "source_success": dict(self.source_success),
            "transient_recovered": self.transient_recovered,
            "raw_yield": raw_yield(new_accepted, self.raw_found),
            "accepted_novelty_rate": accepted_novelty_rate(new_accepted,
                                                           dup_accepted),
        }


def derive_validity(*, failures: int, critical_failed_no_success: bool) -> str:
    """失效判定（规格 §六）：
    INVALID = critical 源失败且该源本轮零成功；
    PARTIAL = 存在失败（含 critical 源降级但角色主体仍完成）；
    FULL    = 无失败。
    """
    if critical_failed_no_success:
        return "INVALID"
    return "PARTIAL" if failures else "FULL"


def build_round_record(*, round_id: str, scope: str, started_at: str,
                       ended_at: str, routes: list[dict],
                       source_roles: list[str] | None = None,
                       notes: str = "",
                       plan_id: str = "", plan_hash: str = "",
                       round_mode: str = "legacy", validity: str = "",
                       transient_failures: int = 0) -> dict:
    raw = sum(r["raw_found"] for r in routes)
    new_acc = sum(r["new_unique_accepted_count"] for r in routes)
    dup_acc = sum(r["duplicate_accepted_count"] for r in routes)
    failures = sum(len(r["source_failures"]) for r in routes)
    new_by_class = {k: 0 for k in _ROUTE_CLASSES}
    high_risk_b = 0
    for r in routes:
        for k, v in (r.get("new_by_class") or {}).items():
            new_by_class[k] = new_by_class.get(k, 0) + v
        high_risk_b += int(r.get("new_high_risk_B", 0) or 0)
    if not validity:
        validity = "FULL" if failures == 0 else "PARTIAL"
    return {
        "schema_version": "phase4b2a.v1",
        "round_id": round_id, "scope_level": scope,
        "started_at": started_at, "ended_at": ended_at,
        # ---- 协议绑定（search plan versioning）----
        "plan_id": plan_id, "plan_hash": plan_hash,
        "round_mode": round_mode, "round_validity": validity,
        "source_roles": source_roles or [],
        "routes": routes,
        "totals": {
            "raw_found": raw,
            "unique_candidate_count": sum(r["unique_candidate_count"]
                                          for r in routes),
            "accepted_count": sum(r["accepted_count"] for r in routes),
            "new_unique_accepted_count": new_acc,
            "duplicate_accepted_count": dup_acc,
            "rejected_count": sum(r["rejected_count"] for r in routes),
            "new_documents_total": sum(r["new_documents_total"] for r in routes),
            "source_failures": failures,
            "transient_failures": transient_failures,
            "new_by_class": {k: v for k, v in new_by_class.items() if v},
            "new_high_risk_B": high_risk_b,
        },
        "raw_yield": raw_yield(new_acc, raw),
        "accepted_novelty_rate": accepted_novelty_rate(new_acc, dup_acc),
        "notes": notes,
    }


def _round_validity(r: dict) -> str:
    v = r.get("round_validity")
    if v:
        return v
    # legacy 轮次回退：无 validity 字段 → 按失败数保守判定
    return "FULL" if r.get("totals", {}).get("source_failures", 0) == 0 else "PARTIAL"


def _high_value_block(rounds: list[dict], evidence_ids: list[str]) -> tuple[bool, str]:
    """高价值新颖度护栏（规格 §五）：
    · 证据轮出现 new_A1 → 阻断；
    · 证据轮出现 new_high_risk_B → 阻断；
    · 证据轮**每一轮**都仍有 new_A2 → 阻断（持续出现核心政策语料 ≠ 饱和）。
    """
    if not evidence_ids:
        return False, ""
    by_id = {r.get("round_id"): r for r in rounds}
    a1 = hr = 0
    a2_every_round = True
    for rid in evidence_ids:
        t = (by_id.get(rid) or {}).get("totals") or {}
        cls = t.get("new_by_class") or {}
        a1 += int(cls.get("A1", 0) or 0)
        hr += int(t.get("new_high_risk_B", 0) or 0)
        if not int(cls.get("A2", 0) or 0):
            a2_every_round = False
    if a1 > 0:
        return True, f"evidence rounds contain new_A1={a1}"
    if hr > 0:
        return True, f"evidence rounds contain new_high_risk_B={hr}"
    if len(evidence_ids) >= CONVERGENCE_ROUNDS and a2_every_round:
        return True, "every evidence round still added new_A2 (sustained core-policy novelty)"
    return False, ""


def convergence_status(rounds: list[dict], *, plan_hash: str | None = None,
                       mode_required: str | None = None) -> dict:
    """连续 ≥2 轮 accepted_novelty_rate < 阈值（且轮次 FULL）→ 收敛。

    Phase 4B-2A 协议：
      · 传入 plan_hash → **严格模式**：仅 plan_hash 一致的轮次可计数；
      · mode_required → 仅该模式的轮次可计数（MODE A / legacy 一律排除）；
      · 轮次 validity != FULL（PARTIAL/INVALID）→ 中断扫描且不计数；
      · 高价值护栏（new_A1 / new_high_risk_B / 持续 new_A2）→ converged=False。
    向后兼容：不传 kwargs 且轮次缺少新字段时，退化为 4B-1 语义（失败轮 break）。
    """
    streak = 0
    evidence: list[str] = []
    for r in reversed(rounds or []):
        if plan_hash is not None and r.get("plan_hash") != plan_hash:
            break                       # 搜索空间不同 → 不得跨 plan 计数
        if mode_required is not None and r.get("round_mode") != mode_required:
            break
        if _round_validity(r) != "FULL":
            break                       # PARTIAL/INVALID 均不作为收敛证据（中断）
        if (r.get("accepted_novelty_rate") or 0.0) < NOVEL_RATE_THRESHOLD:
            streak += 1
            evidence.append(r.get("round_id", "?"))
        else:
            break
    blocked, blocked_reason = _high_value_block(rounds, evidence)
    # plan 变更事件（观测用：连续轮次间 hash 变化 → reset）
    changes: list[dict] = []
    prev = None
    for r in rounds or []:
        h = r.get("plan_hash") or ""
        if h and prev and h != prev:
            changes.append({"round_id": r.get("round_id"),
                            "from": (prev or "")[:12], "to": h[:12]})
        if h:
            prev = h
    return {"converged": streak >= CONVERGENCE_ROUNDS and not blocked,
            "streak": streak, "evidence_rounds": evidence,
            "threshold": NOVEL_RATE_THRESHOLD,
            "blocked_by_high_value": blocked, "blocked_reason": blocked_reason,
            "plan_bound": plan_hash is not None,
            "mode_required": mode_required or "",
            "plan_changes": changes}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
