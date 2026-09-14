# -*- coding: utf-8 -*-
"""evaluate_a1_goldset.py —— A1 Gold Set 专项状态（Phase 4B-2B0 §六）。

纪律：A1 案例必须真实可验证（title/正文级 EV 对象），不得凑数；
不足阈值（<5，用户口径 2026-09-12）→ 明确 INSUFFICIENT_A1_GOLDSET。

输出：outputs/audit/a1_goldset_status.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import yaml  # noqa: E402

from app.policy.goldset import evaluate  # noqa: E402

GOLDSET = ROOT / "sources" / "policy-goldset.yaml"
OUT = ROOT / "outputs" / "audit" / "a1_goldset_status.json"


def main() -> int:
    res = evaluate(include_holdout=True)
    cases = yaml.safe_load(GOLDSET.read_text(encoding="utf-8"))["cases"]
    a1_ids = {c["id"] for c in cases if c.get("expected_class") == "A1"}
    jid = {c["id"]: c.get("jurisdiction") for c in cases}

    detail = {d["id"]: d for d in res["details"]}
    a1_cases = []
    for cid in sorted(a1_ids):
        d = detail.get(cid, {})
        a1_cases.append({
            "id": cid,
            "jurisdiction": jid.get(cid),
            "status": d.get("status", "NOT_FOUND"),
            "expected": d.get("expected"),
            "got": d.get("got"),
            "holdout": d.get("holdout", False),
        })

    doc = {
        "a1_verified_count": res["a1_verified_count"],
        "a1_holdout_count": res["a1_holdout_count"],
        "threshold": 5,
        "status": res["a1_goldset_status"],
        "by_jurisdiction": sorted({c["jurisdiction"] for c in a1_cases}),
        "cases": a1_cases,
        "note_zh": ("A1 阈值=5（用户口径 2026-09-12）。"
                    "当前仅 SB 615 一个真实案例（US-CA），"
                    "如实维持 INSUFFICIENT_A1_GOLDSET，不得降门槛。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"A1 verified={doc['a1_verified_count']} "
          f"holdout={doc['a1_holdout_count']} status={doc['status']}")
    for c in a1_cases:
        print(f"  {c['id']:28s} {c['status']:8s} "
              f"期望 {c['expected']} 实得 {c['got']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
