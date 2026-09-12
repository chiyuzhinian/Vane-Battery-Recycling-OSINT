# -*- coding: utf-8 -*-
"""audit_instrument_accuracy.py —— Phase 4B-1 Step 8：instrument 精度审计。

产物：outputs/audit/instrument_mismatches.json
用法：py scripts/audit_instrument_accuracy.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.goldset import evaluate  # noqa: E402
from app.policy.instrument_audit import analyze  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "instrument_mismatches.json"
TARGET = 0.95


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    gold = evaluate()
    analysis = analyze(gold["instrument_mismatches"])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instrument_type_accuracy": gold["instrument_type_accuracy"],
        "instrument_total": gold["instrument_total"],
        "instrument_ok": gold["instrument_ok"],
        "target": TARGET,
        "met": (gold["instrument_type_accuracy"] or 0) >= TARGET,
        "by_reason": analysis["by_reason"],
        "mismatches": analysis["mismatches"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    acc = gold["instrument_type_accuracy"]
    print("=== instrument 精度审计 ===")
    print(f"accuracy = {acc}（{gold['instrument_ok']}/{gold['instrument_total']}）"
          f"｜ 目标 {TARGET}｜ {'✅ 达标' if payload['met'] else '❌ 未达标（如实输出）'}")
    print(f"原因分布: {payload['by_reason']}")
    for m in analysis["mismatches"]:
        print(f"  · [{m['reason']}] {m['id']} 期望={m['expected_instrument']} "
              f"实际={m['actual_instrument']} src={m['source_id']} "
              f"title={m['title'][:60]}")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
