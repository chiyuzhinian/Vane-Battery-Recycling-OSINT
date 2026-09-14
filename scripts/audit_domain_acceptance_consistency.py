# -*- coding: utf-8 -*-
"""audit_domain_acceptance_consistency.py —— Phase 4B-2B1 §2。

语义一致性纪律（目标：contradiction = 0）：
    OUT_OF_SCOPE  + final ∈ {A1,A2,B}   → 矛盾
    GENERAL       + final ∈ {A1,A2,B}   → 矛盾
    SUPPORTING    + final ∈ {A1,A2}     → 矛盾
（final = guarded_effective_class；NIM discovery 层单独统计，不入矛盾。）

产物：outputs/audit/domain_acceptance_mismatches.json
用法：py scripts/audit_domain_acceptance_consistency.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.domain_scope import (  # noqa: E402
    classify_domain_scope, guarded_effective_class, is_policy_domain_source)

OUT = ROOT / "outputs" / "audit" / "domain_acceptance_mismatches.json"

FORBIDDEN = {
    "OUT_OF_SCOPE": {"A1", "A2", "B"},
    "GENERAL_BATTERY_BACKGROUND": {"A1", "A2", "B"},
    "SUPPORTING_REGULATION": {"A1", "A2"},
}


def main() -> int:
    recs = load_records(ROOT)
    contradictions: list[dict] = []
    downgrades: list[dict] = []       # 被护栏修正（诊断）
    nim_scopes: Counter = Counter()
    scanned = 0

    for r in recs:
        sid = str(r.get("source_id") or "")
        if not is_policy_domain_source(sid):
            continue
        try:
            scope = classify_domain_scope(r)
        except Exception:  # noqa: BLE001
            continue
        if sid.startswith("eu_nim_"):
            nim_scopes[scope] += 1
            continue
        scanned += 1
        try:
            raw = classify_record(r).classification
            final = guarded_effective_class(r, raw)
        except Exception:  # noqa: BLE001
            continue
        if final in FORBIDDEN.get(scope, ()):  # pragma: no cover - 目标 0
            contradictions.append({
                "evidence_id": r.get("evidence_id"),
                "source_id": sid, "domain_scope": scope,
                "final_class": final, "raw_class": raw,
                "title": (r.get("title") or "")[:90],
            })
        if final != raw:
            downgrades.append({
                "evidence_id": r.get("evidence_id"),
                "domain_scope": scope, "before": raw, "after": final,
            })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus_scanned": scanned,
        "contradictions": contradictions,
        "contradictions_count": len(contradictions),
        "guarded_downgrades_count": len(downgrades),
        "guarded_downgrades_sample": downgrades[:20],
        "nim_scopes": dict(nim_scopes),
        "note": ("contradiction = OUT_OF_SCOPE/GENERAL + 强类 或 SUPPORTING + A1/A2；"
                 "目标 0。NIM discovery 层单独统计（封顶 C）。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"corpus_scanned={scanned}  contradictions="
          f"{len(contradictions)}  downgrades={len(downgrades)}")
    by = Counter(d["domain_scope"] for d in downgrades)
    print("downgrades by scope:", dict(by))
    by2 = Counter((d["before"], d["after"]) for d in downgrades)
    print("downgrades by class:", {f"{a}->{b}": n for (a, b), n in by2.most_common()})
    if contradictions:
        for c in contradictions[:10]:
            print("  ❌", c)
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
