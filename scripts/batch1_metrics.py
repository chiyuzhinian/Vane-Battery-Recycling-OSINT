# -*- coding: utf-8 -*-
"""batch1_metrics.py —— Phase 4B-2B §13：Batch 1 指标汇总。

从 source_proofs + jurisdiction 产物统计（不把"政策条数"当 KPI）。
产物：outputs/audit/batch1_metrics.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

AUDIT = ROOT / "outputs" / "audit"
PROOFS = AUDIT / "source_proofs"
OUT = AUDIT / "batch1_metrics.json"

BATCH1 = {
    "EU": ["BE", "HU", "IT", "SK", "CZ", "AT"],
    "US": ["US-MI", "US-GA", "US-IL", "US-TN", "US-TX", "US-NV", "US-OH",
           "US-CO"],
}


def main() -> int:
    per: dict = {}
    for group, jids in BATCH1.items():
        for jid in jids:
            pf = PROOFS / f"{jid}.json"
            if not pf.exists():
                per[jid] = {"proof": False}
                continue
            d = json.loads(pf.read_text(encoding="utf-8"))
            srcs = d.get("sources") or []
            connected = [s for s in srcs
                         if sum(1 for x in (s.get("samples") or [])
                                if x.get("status") == 200) > 0]
            partial = [s for s in srcs if s not in connected
                       and (s.get("capabilities") or {}
                            ).get("metadata_available")]
            blocked = [s for s in srcs if s not in connected
                       and s not in partial]
            samples = sum(len([x for x in (s.get("samples") or [])
                               if x.get("status") == 200]) for s in srcs)
            per[jid] = {
                "proof": True,
                "sources": len(srcs),
                "connected_roles": len(connected),
                "partial_roles": len(partial),
                "blocked_roles": len(blocked),
                "samples_ok": samples,
                "onboarded": len(connected) > 0,
                "generated_at": d.get("generated_at", ""),
            }
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "batch": BATCH1,
        "per_jurisdiction": per,
        "EU": {
            "selected": len(BATCH1["EU"]),
            "proof_done": sum(1 for j in BATCH1["EU"] if per[j]["proof"]),
            "onboarded": sum(1 for j in BATCH1["EU"] if per[j].get("onboarded")),
        },
        "US": {
            "selected": len(BATCH1["US"]),
            "proof_done": sum(1 for j in BATCH1["US"] if per[j]["proof"]),
            "onboarded": sum(1 for j in BATCH1["US"] if per[j].get("onboarded")),
        },
        "note": ("onboarded = ≥1 role 有真实样本（samples_ok≥1）；"
                 "proof_done = 已完成 Source Proof 探测（含 0 样本的如实记录）。"
                 "条数仅为描述统计，不是 KPI。"),
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    for jid, r in per.items():
        if r["proof"]:
            print(f"  {jid:6s} connected={r['connected_roles']} "
                  f"partial={r['partial_roles']} blocked={r['blocked_roles']} "
                  f"samples={r['samples_ok']}")
        else:
            print(f"  {jid:6s} NO PROOF")
    print(f"EU onboarded {summary['EU']['onboarded']}/{summary['EU']['selected']}")
    print(f"US onboarded {summary['US']['onboarded']}/{summary['US']['selected']}")
    print(f"→ {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
