# -*- coding: utf-8 -*-
"""audit_policy_saturation.py —— 饱和门审计（Phase 4A §15）。

用法：
    py scripts/audit_policy_saturation.py --region EU
    py scripts/audit_policy_saturation.py --region US --json

⚠️ 真实结果 PARTIAL 就输出 PARTIAL —— 不得为了报告变绿而降低阈值。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.saturation import evaluate_saturation  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="EU")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = evaluate_saturation(args.region.upper())

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"=== 饱和门审计 · {res['region']} ===")
    print(f"通过 {res['checks_passed']} ｜ 状态: {res['status']}")
    print("-" * 100)
    for name, c in res["checks"].items():
        mark = "✅" if c["pass"] else "❌"
        extra = " ".join(f"{k}={v}" for k, v in c.items()
                         if k not in ("pass",) and not isinstance(v, dict))
        print(f"  {mark} {name:24s} {extra[:88]}")
    g = res["goldset"]
    print("-" * 100)
    print(f"  GoldSet: {g['cases_found']}/{g['cases_total']} 匹配 "
          f"(insufficient={g['INSUFFICIENT_GOLDSET']}) "
          f"P={g['precision']} R={g['recall']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
