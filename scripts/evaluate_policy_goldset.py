# -*- coding: utf-8 -*-
"""evaluate_policy_goldset.py —— Gold Set 评估（Phase 4A §15）。

用法：
    py scripts/evaluate_policy_goldset.py
    py scripts/evaluate_policy_goldset.py --no-holdout --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.goldset import evaluate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-holdout", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = evaluate(include_holdout=not args.no_holdout)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print("=== Policy Gold Set 评估 ===")
    if res["INSUFFICIENT_GOLDSET"]:
        print("⚠️ INSUFFICIENT_GOLDSET —— 案例不足或匹配率过低，"
              "以下指标仅供诊断，不得用于验收")
    print(f"案例 {res['cases_total']} 条；匹配到 {res['cases_found']} 条")
    print(f"precision={res['precision']}  recall={res['recall']}  "
          f"f1={res['f1']}")
    print(f"A1 recall={res['a1_recall']}  A2 recall={res['a2_recall']}  "
          f"B recall={res['b_recall']}")
    print(f"FP rate={res['false_positive_rate']}  FN rate={res['false_negative_rate']}")
    print(f"instrument accuracy={res['instrument_type_accuracy']}  "
          f"legal_status accuracy={res['legal_status_accuracy']}")
    print("-" * 100)
    for d in res["details"]:
        mark = {"OK": "✅", "MISMATCH": "❌", "NOT_FOUND": "⛔"}.get(d["status"], "?")
        hold = " [holdout]" if d.get("holdout") else ""
        if d["status"] == "OK":
            print(f"  {mark} {d['id']:28s} → {d['got']}{hold}")
        else:
            print(f"  {mark} {d['id']:28s} 期望 {d.get('expected')} "
                  f"实得 {d.get('got', '—')}{hold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
