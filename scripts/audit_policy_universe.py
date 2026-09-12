# -*- coding: utf-8 -*-
"""audit_policy_universe.py —— 管辖区×源角色 覆盖审计（Phase 4A §15）。

用法：
    py scripts/audit_policy_universe.py --region EU
    py scripts/audit_policy_universe.py --region US --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.source_universe import build_universe_rows, universe_summary  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="EU")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    region = args.region.upper()
    rows = [r for r in build_universe_rows()
            if r.jurisdiction == region
            or (region == "EU" and r.jurisdiction == "EU_27")
            or (region == "US" and r.jurisdiction == "US_STATES")
            or (region.startswith("US-") and r.jurisdiction == region)]
    summary = universe_summary()

    if args.json:
        print(json.dumps({"region": region,
                          "rows": [r.__dict__ for r in rows],
                          "summary": summary}, ensure_ascii=False, indent=2))
        return 0

    print(f"=== 源宇宙审计 · {region} ===")
    print(f"{'管辖区':10s} {'角色':32s} {'期望':4s} {'采集器':5s} {'状态':13s} 缺口")
    print("-" * 110)
    for r in rows:
        print(f"{r.jurisdiction:10s} {r.source_role:32s} "
              f"{'✓' if r.expected else '—':4s} "
              f"{'✓' if r.collector_available else '✗':5s} "
              f"{r.status:13s} {r.gap_reason[:48]}")
    print("-" * 110)
    print(f"EU 主体覆盖: {summary['EU']['covered']}/{summary['EU']['total']} "
          f"({summary['EU']['pct']}%)")
    print(f"US 联邦覆盖: {summary['US']['covered']}/{summary['US']['total']} "
          f"({summary['US']['pct']}%)")
    ms = summary["MEMBER_STATES"]
    print(f"成员国(逐国): {ms['covered']}/{ms['total']} ({ms['pct']}%)")
    print(f"BLOCKED: {len(summary['blocked'])} 条")
    print(f"未接入(期望): {len(summary['not_onboarded_expected'])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
