# -*- coding: utf-8 -*-
"""Convergence Protocol Recheck（Phase 4B-2A Step 1）—— 纯逻辑。

职责（**只读**）：把 Phase 4B-1 的历史轮次按新协议（FULL/PARTIAL/INVALID +
plan 绑定 + mode）重新标记，输出**独立新产物**：

    outputs/audit/convergence_recheck.json

纪律：
    · 不修改 outputs/discovery_rounds/*.json（历史零改动；含 sha256 承诺记录）
    · legacy 轮次无论评级如何都不参与新协议 streak（无 plan 绑定）
    · 网络失败不得解释为"没有新增结果"——失败明细逐条入档

重标记规则（与 rounds.derive_validity 同一口径）：
    INVALID ← critical 源失败 **且该源本轮零成功**（或显式 round_validity）
    PARTIAL ← 存在任何失败（critical 源降级但角色主体完成 / 非 critical 端点失败）
    FULL    ← 无失败
"""
from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ROUNDS_DIR = ROOT / "outputs" / "discovery_rounds"

_SCOPE_JURISDICTION = {"US_FEDERAL": "US", "EU_SUPRANATIONAL": "EU",
                       "EU_MEMBER_STATES": "EU_27", "US_STATES": "US_STATES"}


def critical_sources_for_scope(scope: str) -> set[str]:
    """scope → critical 角色的 source_id 集合（经注册表 + 别名展开）。"""
    from app.policy.config import load_aliases, load_registry
    from app.policy.source_access import expand_role_sources
    from app.policy.source_universe import evidence_counts
    code = _SCOPE_JURISDICTION.get(scope, scope)
    known = sorted(evidence_counts().keys())
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    out: set[str] = set()
    for j in load_registry().jurisdictions:
        if j.code != code:
            continue
        for role in j.source_roles:
            if role.critical:
                out.update(expand_role_sources(list(role.sources), alias_map, known))
    return out


def assess_round(doc: dict, critical_sources: set[str]) -> dict:
    """单轮重标记（不改原文件）。"""
    routes = doc.get("routes") or []
    failures: list[dict] = []
    success_by_source: dict[str, int] = {}
    raw_by_route: dict[str, int] = {}
    for r in routes:
        rid = r.get("id", "?")
        raw_by_route[rid] = int(r.get("raw_found", 0) or 0)
        for src, n in (r.get("source_success") or {}).items():
            success_by_source[src] = success_by_source.get(src, 0) + int(n)
        for f in (r.get("source_failures") or []):
            failures.append({"route": rid, "source": f.get("source", ""),
                             "query": f.get("query", ""),
                             "failure": f.get("failure", "")})
    # 失败源 → 该源在本轮是否零成功（无法归因时取全局近似）
    critical_failed_no_success = False
    for f in failures:
        src = f["source"]
        if src in critical_sources and success_by_source.get(src, 0) == 0:
            # 近似口径：若源无显式成功计数，用承载该失败的路线 raw>0 判定降级
            if raw_by_route.get(f["route"], 0) == 0:
                critical_failed_no_success = True
    explicit = doc.get("round_validity") or ""
    if explicit:
        validity = explicit
    else:
        validity = ("INVALID" if critical_failed_no_success
                    else ("PARTIAL" if failures else "FULL"))
    legacy = not (doc.get("plan_hash") or "")
    return {
        "round_id": doc.get("round_id", "?"),
        "scope": doc.get("scope_level", "?"),
        "legacy_plan": legacy,
        "plan_id": doc.get("plan_id", ""),
        "mode": doc.get("round_mode") or ("legacy" if legacy else ""),
        "validity": validity,
        "critical_degraded": bool(failures
                                  and any(f["source"] in critical_sources
                                          for f in failures)),
        "failures": failures,
        "accepted_novelty_rate": doc.get("accepted_novelty_rate"),
        # legacy 无 plan 绑定 → 无论评级均不参与新协议 streak
        "eligible_for_streak": bool((not legacy)
                                    and validity == "FULL"
                                    and (doc.get("round_mode")
                                         == "convergence_validation")),
        "note": ("Phase 4B-1 历史轮次（无 plan 绑定，只读重标记，不参与新协议 streak）"
                 if legacy else ""),
    }


def sha256_file(fp: Path) -> str:
    return hashlib.sha256(fp.read_bytes()).hexdigest()


def build_recheck(round_files: list[Path]) -> dict:
    docs = []
    for fp in round_files:
        try:
            docs.append((fp, json.loads(fp.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            continue
    docs.sort(key=lambda t: (t[1].get("scope_level", ""),
                             t[1].get("ended_at", "")))
    scopes = {d.get("scope_level") for _fp, d in docs}
    crit: dict[str, set[str]] = {s: critical_sources_for_scope(s) for s in scopes if s}
    rows = []
    for fp, doc in docs:
        row = assess_round(doc, crit.get(doc.get("scope_level"), set()))
        row["file"] = fp.name
        rows.append(row)
    summary = {"total": len(rows),
               "legacy": sum(1 for r in rows if r["legacy_plan"]),
               "full": sum(1 for r in rows if r["validity"] == "FULL"),
               "partial": sum(1 for r in rows if r["validity"] == "PARTIAL"),
               "invalid": sum(1 for r in rows if r["validity"] == "INVALID"),
               "eligible_for_streak": sum(1 for r in rows if r["eligible_for_streak"])}
    return {
        "protocol": "phase4b2a.v1",
        "rounds": rows,
        "summary": summary,
        # 历史零改动承诺：对参与重标记的轮次文件记录 sha256（外部可核验）
        "file_commitments": {fp.name: sha256_file(fp) for fp, _d in docs},
    }


def scan_round_files() -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(ROUNDS_DIR / "round_*.json")))
