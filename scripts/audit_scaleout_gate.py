# -*- coding: utf-8 -*-
"""audit_scaleout_gate.py —— Phase 4B-2B1 §14：Scale-out Readiness Gate。

读 layers/content_completeness/domain_mismatches/blocked_channels/a1 产物
→ outputs/audit/scaleout_readiness.json（报告数据源）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.saturation_gates import (  # noqa: E402
    aggregate_eligible, evaluate_scaleout_preconditions,
)

AUDIT = ROOT / "outputs" / "audit"
OUT = AUDIT / "scaleout_readiness.json"


def _load(name: str) -> dict:
    fp = AUDIT / name
    return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}


def main() -> int:
    layers = _load("jurisdiction_layers.json")
    completeness = _load("content_completeness.json").get("summary") or {}
    mismatches = _load("domain_acceptance_mismatches.json")
    channels = _load("blocked_channel_resolution.json")
    a1 = _load("a1_goldset_status.json")

    js = layers.get("jurisdictions") or {}
    eligible = [jid for jid, r in js.items() if r.get("jurisdiction_eligible")]
    adapted = len(channels.get("adapted") or [])

    per_jid = {}
    for jid, row in js.items():
        if not row.get("plan_converged"):
            continue
        per_jid[jid] = evaluate_scaleout_preconditions(
            layers_row=row, evidence_summary=completeness,
            domain_mismatches=mismatches, adapted_channels=adapted,
            eligible_count=len(eligible),
            a1_status=str(a1.get("status") or ""),
            a1_verified=int(a1.get("a1_verified_count") or 0))

    # 全局 gate（Phase 4B-2B §2：每一个 eligible 逐一评估，禁止样本代表）
    per_eligible = {jid: per_jid[jid] for jid in eligible if jid in per_jid}
    agg = aggregate_eligible(per_eligible)
    verdict = "READY" if (agg["all_eligible_pass"] and len(eligible) >= 3
                          and adapted >= 5) else "NOT READY"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eligible_count": len(eligible),
        "eligible": sorted(eligible),
        "channels_adapted": adapted,
        "channels_adapted_list": channels.get("adapted") or [],
        "channels_blocked": channels.get("blocked") or [],
        "channels_partial": channels.get("partial") or [],
        "a1": {"status": a1.get("status"), "verified": a1.get("a1_verified_count"),
               "holdout": a1.get("a1_holdout_count")},
        "evidence": {
            "A1": completeness.get("A1"),
            "A2": completeness.get("A2"),
            "B": completeness.get("B"),
            "b_candidates": completeness.get("b_candidates"),
        },
        "domain_contradictions": mismatches.get("contradictions_count"),
        "per_jurisdiction_preconditions": per_jid,
        "eligible_gate": agg,
        "verdict": verdict,
        "note": ("README gate（§14）：eligible≥3 且 通道≥5 且 高价值全文≥95% "
                 "且 B clause≥95% 且 domain 矛盾=0 且 topic 无 P0 且 "
                 "identity≥90% 且 A1 可解释。4B-2B1R 后 EUR-Lex 全文经 "
                 "CELLAR 官方 REST 通道恢复回填（§2/§3 取证见报告）；"
                 "R(N) 更正件等官方无独立在线变体者按 no_online_variant "
                 "豁免（证据链与名单在 content_completeness.json）。"
                 "不满条件则 NOT READY。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"eligible={len(eligible)} {sorted(eligible)}  "
          f"channels_adapted={adapted}")
    print(f"A1 全文={completeness.get('A1', {}).get('fulltext_pct')}%  "
          f"A2={completeness.get('A2', {}).get('fulltext_pct')}%  "
          f"B={completeness.get('B', {}).get('fulltext_pct')}%  "
          f"B_clause={completeness.get('B', {}).get('clause_pct')}%")
    print(f"domain contradictions={mismatches.get('contradictions_count')}")
    print(f"eligible_gate: total={agg['eligible_total']} "
          f"pass={agg['eligible_pass']} fail={agg['eligible_fail']}"
          f" fail_list={agg['fail_list']}")
    for jid, r in per_jid.items():
        print(f"  {jid:6s} all_pass={r['all_pass']} failing={r['failing']}")
    print(f"\nFULL SCALE-OUT: {verdict}")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
