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

    def as_dict(self, *, classified: dict[str, str],
                existing_ids: set[str]) -> dict:
        """classified: evidence_id → acceptance_class；existing_ids: 既有语料 id。"""
        uniq: dict[str, dict] = {}
        for c in self.candidates:
            uniq.setdefault(c["evidence_id"], c)
        new_accepted = dup_accepted = rejected = 0
        new_docs_total = 0
        per_class = {k: 0 for k in ("A1", "A2", "B", "C", "D")}
        for eid in uniq:
            cls = classified.get(eid, "D")
            per_class[cls] = per_class.get(cls, 0) + 1
            accepted = cls in ACCEPTED_CLASSES
            if accepted:
                if eid in existing_ids:
                    dup_accepted += 1
                else:
                    new_accepted += 1
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
            "source_failures": self.source_failures,
            "raw_yield": raw_yield(new_accepted, self.raw_found),
            "accepted_novelty_rate": accepted_novelty_rate(new_accepted,
                                                           dup_accepted),
        }


def build_round_record(*, round_id: str, scope: str, started_at: str,
                       ended_at: str, routes: list[dict],
                       source_roles: list[str] | None = None,
                       notes: str = "") -> dict:
    raw = sum(r["raw_found"] for r in routes)
    new_acc = sum(r["new_unique_accepted_count"] for r in routes)
    dup_acc = sum(r["duplicate_accepted_count"] for r in routes)
    failures = sum(len(r["source_failures"]) for r in routes)
    return {
        "schema_version": "phase4b1.v1",
        "round_id": round_id, "scope_level": scope,
        "started_at": started_at, "ended_at": ended_at,
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
        },
        "raw_yield": raw_yield(new_acc, raw),
        "accepted_novelty_rate": accepted_novelty_rate(new_acc, dup_acc),
        "notes": notes,
    }


def convergence_status(rounds: list[dict]) -> dict:
    """连续 ≥2 轮 accepted_novelty_rate < 阈值（且无 source failure）→ 收敛。"""
    streak = 0
    evidence: list[str] = []
    for r in reversed(rounds or []):
        if r.get("totals", {}).get("source_failures", 0) > 0:
            break                       # 失败轮不得作为收敛证据
        if (r.get("accepted_novelty_rate") or 0.0) < NOVEL_RATE_THRESHOLD:
            streak += 1
            evidence.append(r.get("round_id", "?"))
        else:
            break
    return {"converged": streak >= CONVERGENCE_ROUNDS, "streak": streak,
            "evidence_rounds": evidence,
            "threshold": NOVEL_RATE_THRESHOLD}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
