# -*- coding: utf-8 -*-
"""audit_convergence_protocol.py —— Phase 4B-2A Step 1：Convergence 协议回填审计。

对全部历史轮次（outputs/discovery_rounds/*.json）按**新协议**只读重新标记：
    plan 绑定 / MODE / round_validity（FULL|PARTIAL|INVALID）/ eligible_for_streak

产物（**独立新文件，绝不修改历史轮次 JSON**）：
    outputs/audit/convergence_recheck.json
    （含 file_commitments：参与重标记的轮次文件 sha256 —— 历史零改动承诺）

用法：
    py scripts/audit_convergence_protocol.py
    py scripts/audit_convergence_protocol.py --json
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

from app.policy.convergence_recheck import build_recheck, scan_round_files  # noqa: E402
from app.policy.search_plan import build_registry  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "convergence_recheck.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = scan_round_files()
    if not files:
        print("（outputs/discovery_rounds/ 下没有轮次文件）")
        return 1
    report = build_recheck(files)
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["search_plan_registry"] = build_registry()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    s = report["summary"]
    print("=== Convergence 协议回填（新规则只读重标记）===")
    print(f"轮次总数 {s['total']} ｜ legacy {s['legacy']} ｜ "
          f"FULL {s['full']} ｜ PARTIAL {s['partial']} ｜ INVALID {s['invalid']} ｜ "
          f"可参与新 streak {s['eligible_for_streak']}")
    for r in report["rounds"]:
        flag = {"FULL": "✅", "PARTIAL": "⚠️", "INVALID": "❌"}[r["validity"]]
        degraded = " ｜critical_endpoint_degraded" if r["critical_degraded"] else ""
        print(f"  {flag} {r['round_id']:34s} {r['scope']:17s} "
              f"validity={r['validity']:7s} nov={r['accepted_novelty_rate']} "
              f"failures={len(r['failures'])}{degraded} "
              f"eligible={r['eligible_for_streak']}")
    plans = report["search_plan_registry"]
    print(f"\nSearch Plan 注册表：{len(plans['plans'])} 个 plan，"
          f"{len(plans['errors'])} 个错误")
    for p in plans["plans"]:
        print(f"  ▸ {p['plan_id']}  hash={p['plan_hash'][:12]}  "
              f"scope={p['scope']}  routes={p['routes']}")
    for e in plans["errors"]:
        print(f"  ❌ {e['plan_id']}: {e['error']}")
    print(f"\n→ 已写 {OUT.relative_to(ROOT)}（历史轮次零改动，含 sha256 承诺）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
