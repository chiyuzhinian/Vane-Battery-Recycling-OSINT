# -*- coding: utf-8 -*-
"""Jurisdiction Coverage（Phase 4B-2A Step 7）—— 纯逻辑。

每个管辖地输出（规格 §14/§15/§16/§17）：
    Source Coverage    （契约 mandatory 角色覆盖；不计文档条数）
    Legal Identity     （identity_jurisdiction 完整度）
    Acceptance         （A1/A2/B/C/D 分布）
    Legal Family       （策略 + 全局 P0 状态；成员国=NIM 转置，州=修订链）
    Gold Recall        （按管辖地暂无 gold 案例 → not_available，如实）
    Discovery Routes   （source proof 能力：search/enumeration/fulltext）
    Novelty            （该管辖地 scope 的轮次；未启动 → not_available）
    Failures           （collection failures + source proof limitations）
    Topic Matrix       （T01–T14：COVERED/PARTIAL/MISSING/BLOCKED）
    Black Mass         （六线 jurisdiction 级矩阵）

纪律：**条数只是描述性统计**，不得作为覆盖分子/分母。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT = ROOT / "outputs" / "audit"

TOPIC_STATES = ("COVERED", "PARTIAL", "MISSING", "BLOCKED")


def load_failures() -> list[dict]:
    fp = AUDIT / "jurisdiction_collection_failures.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8")).get("entries", [])
    except json.JSONDecodeError:
        return []


def load_rounds_index() -> list[dict]:
    fp = AUDIT / "discovery_rounds.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8")).get("rounds", [])
    except json.JSONDecodeError:
        return []


def load_proof_summary(jid: str) -> dict | None:
    fp = AUDIT / "source_proofs" / f"{jid}.json"
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data.get("summary")


def topic_status(records: list[dict], *, stuck: bool = False) -> dict[str, str]:
    """T01–T14 五态判定（COVERED=有 A/B 强证据；PARTIAL=有命中无强证据；
    MISSING=无命中；BLOCKED=通道受阻且无记录）。

    2B0 修复（审计 Q3/P0-A2）：
        · 扫描窗口 = 全文（原 text[:4000] 对长法规严重截断）；
        · 强证据分类用 effective_class（meta → 现算回退）。
    """
    from app.policy.config import load_topics
    topics = load_topics().topics
    if stuck and not records:
        return {t.id: "BLOCKED" for t in topics}
    out: dict[str, str] = {}
    for t in topics:
        pats = [re.compile(p, re.I) for p in t.include_patterns]
        matched = strong = 0
        for r in records:
            hay = (r.get("title") or "") + "\n" + (r.get("text") or "")
            if any(p.search(hay) for p in pats):
                matched += 1
                if _is_corpus_strong(r):
                    strong += 1
        out[t.id] = ("COVERED" if strong else
                     "PARTIAL" if matched else "MISSING")
    return out


def derive_level(*, records: int, strong: int, failures: int,
                 covered_roles: int) -> str:
    if records and strong:
        return "ACTIVE"
    if records:
        return "COLLECTED"
    if failures:
        return "BLOCKED"
    if covered_roles:
        return "REFERENCE"
    return "NOT_ONBOARDED"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def unresolved_failures(fails: list[dict], rows: list[dict]) -> list[dict]:
    """过滤：同一 doc 已有成功记录 → 该失败视为已解决（不计未决失败）。

    匹配口径：doc 与 evidence_id 去除非字母数字后互为子串
    （如 '20110646' ↔ 'fi_finlex_20110646'；'US-WA:RCW:70A.555' ↔ 'us_wa_rcw_70a_555'）。
    """
    eids = [_norm(str(r.get("evidence_id") or "")) for r in rows]
    out: list[dict] = []
    for f in fails:
        doc_raw = str(f.get("doc") or "")
        doc = _norm(doc_raw)
        tail = _norm(doc_raw.split(":")[-1])   # 末段（如 US-CA:AB:…:AB2440 → AB2440）
        if doc and any(doc in eid or eid.endswith(doc) or
                       (tail and tail in eid) for eid in eids if eid):
            continue
        out.append(f)
    return out


def _eff_class(record: dict) -> str:
    """有效分类（meta → 现算回退；2B0 审计 Q3/P0-A2 修复）。"""
    from app.policy.topic_audit import effective_class
    return effective_class(record)


_DISCOVERY_STRONG_EXCLUDED = ("eu_nim_",)


def _is_corpus_strong(record: dict) -> bool:
    """强证据（A1/A2/B）且**非 discovery layer**。

    2A 铁律：NIM = discovery layer ≠ national corpus——NIM 记录的自动 A2
    不得充当管辖地强证据（否则每个有 NIM 的国家都假 ACTIVE）。
    """
    sid = str(record.get("source_id") or "")
    if sid.startswith(_DISCOVERY_STRONG_EXCLUDED):
        return False
    return _eff_class(record) in ("A1", "A2", "B")


def build_jurisdiction_coverage(records: list[dict]) -> dict:
    """全量管辖地覆盖矩阵。"""
    from collections import Counter

    from app.policy.black_mass import build_coverage
    from app.policy.jurisdiction_map import jurisdiction_of
    from app.policy.jurisdiction_onboarding import build_contract_registry
    from app.policy.identity_jurisdiction import identity_completeness

    contracts = {c["jurisdiction_id"]: c
                 for c in build_contract_registry()["contracts"]}
    failures = load_failures()
    rounds = load_rounds_index()

    by_jid: dict[str, list[dict]] = {}
    for r in records:
        by_jid.setdefault(jurisdiction_of(r), []).append(r)

    jids = sorted(set(by_jid) | set(contracts))
    out: dict[str, dict] = {}
    for jid in jids:
        rows = by_jid.get(jid, [])
        contract = contracts.get(jid)
        acceptance = Counter(_eff_class(r) or "?" for r in rows)
        strong = sum(1 for r in rows if _is_corpus_strong(r))
        raw_fails = [e for e in failures if e.get("jurisdiction") == jid]
        fails = unresolved_failures(raw_fails, rows)
        # 自有记录（本管辖地采集器产出；NIM 元数据不算）
        own_rows = [r for r in rows
                    if (r.get("meta") or {}).get("jurisdiction") == jid]
        rounds_j = [x for x in rounds if x.get("scope_level") == jid]
        proof = load_proof_summary(jid)
        blocked_only = bool(fails) and not rows
        if fails and not own_rows and strong == 0:
            level = "BLOCKED"          # 仅 NIM 元数据 + 通道未决失败
        else:
            level = derive_level(
                records=len(rows), strong=strong, failures=len(fails),
                covered_roles=(contract or {}).get("covered_roles", 0))
        out[jid] = {
            "jurisdiction_id": jid,
            "level": level,
            "records": len(rows),          # descriptive statistic only
            "sources": ({
                "covered": contract["covered_roles"],
                "mandatory": contract["mandatory_roles"],
                "pct": contract["coverage_pct"],
            } if contract else None),
            "identity": identity_completeness(rows, ""),
            "acceptance": dict(acceptance),
            "topics": topic_status(rows, stuck=blocked_only),
            "black_mass": build_coverage(records, jurisdiction=jid)["summary"],
            "proof": proof,
            "failures": fails,
            "novelty": {"available": bool(rounds_j), "rounds": len(rounds_j)},
            "legal_family": ({
                "strategy": "nim_transposition",
                "p0_unresolved_global": None,   # 由 legal_graph 报告填充（全局）
            } if (contract or {}).get("level") == "member_state" else {
                "strategy": "state_amendment_chain",
                "status": "PENDING (Step 8+)",
            }),
            "gold_recall": {"available": False,
                            "reason": "无管辖地专属 gold 案例（A1 栖息地待深采）"},
        }

    topics_covered = sum(
        1 for jid in out for st in out[jid]["topics"].values() if st == "COVERED")
    return {
        "jurisdictions": out,
        "summary": {
            "total": len(out),
            "active": sum(1 for j in out.values() if j["level"] == "ACTIVE"),
            "collected": sum(1 for j in out.values()
                             if j["level"] == "COLLECTED"),
            "blocked": sum(1 for j in out.values() if j["level"] == "BLOCKED"),
            "reference": sum(1 for j in out.values()
                             if j["level"] == "REFERENCE"),
            "topics_covered_cells": topics_covered,
        },
    }
