# -*- coding: utf-8 -*-
"""audit_jurisdiction_convergence.py —— Step 9：管辖地收敛审计。

读 outputs/audit/discovery_rounds.json（轮索引 + plan_convergence 严格视图），
输出 outputs/audit/jurisdiction_convergence.json：每个管辖地计划的
MODE A/MODE B 轮数、streak、converged、证据轮、累计新发现。

用法：py scripts/audit_jurisdiction_convergence.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
OUT = ROOT / "outputs" / "audit" / "jurisdiction_convergence.json"


def main() -> int:
    if not INDEX.exists():
        print("❌ 缺少 discovery_rounds.json（先运行管辖地轮）")
        return 2
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    rounds = data.get("rounds") or []
    plan_conv = data.get("plan_convergence") or {}

    by_plan: dict[str, dict] = {}
    for r in rounds:
        pid = r.get("plan_id") or ""
        if not pid or pid in ("US_FED_PLAN_V1", "EU_SUPRA_PLAN_V1"):
            continue
        e = by_plan.setdefault(pid, {
            "plan_id": pid, "scope": r.get("scope_level"),
            "plan_hash": r.get("plan_hash", ""),
            "rounds_total": 0, "modea_rounds": 0, "modeb_rounds": 0,
            "full": 0, "partial": 0, "invalid": 0, "legacy": 0,
            # 轮次级 new_accepted 求和（跨路线同 id 会双计；入库口径见语料）
            "new_accepted_sum_modeA": 0, "new_accepted_sum_modeB": 0,
        })
        e["rounds_total"] += 1
        mode = r.get("round_mode")
        if mode == "discovery_expansion":
            e["modea_rounds"] += 1
            e["new_accepted_sum_modeA"] += int(
                (r.get("totals") or {}).get("new_unique_accepted_count") or 0)
        elif mode == "convergence_validation":
            e["modeb_rounds"] += 1
            e["new_accepted_sum_modeB"] += int(
                (r.get("totals") or {}).get("new_unique_accepted_count") or 0)
        else:
            e["legacy"] += 1
        v = r.get("round_validity")
        if v == "FULL":
            e["full"] += 1
        elif v == "PARTIAL":
            e["partial"] += 1
        elif v == "INVALID":
            e["invalid"] += 1

    for pid, e in by_plan.items():
        c = plan_conv.get(e["plan_hash"][:12]) or {}
        e["convergence"] = {
            "converged": c.get("converged"),
            "streak": c.get("streak"),
            "blocked_by_high_value": c.get("blocked_by_high_value"),
            "evidence_rounds": c.get("evidence_rounds") or [],
            "threshold": c.get("threshold"),
            "mode_required": c.get("mode_required"),
        }

    converged = sum(1 for e in by_plan.values()
                    if (e["convergence"] or {}).get("converged"))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "plans": by_plan,
        "summary": {
            "plans_total": len(by_plan),
            "converged": converged,
            "not_converged": len(by_plan) - converged,
            "rounds_total": sum(e["rounds_total"] for e in by_plan.values()),
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    s = payload["summary"]
    print("=== Jurisdiction Convergence ===")
    print(f"计划 {s['plans_total']} ｜ 收敛 {s['converged']} ｜ "
          f"未收敛 {s['not_converged']} ｜ 轮次 {s['rounds_total']}")
    for pid, e in sorted(by_plan.items()):
        c = e["convergence"]
        print(f"  {pid:16s} A{e['modea_rounds']}/B{e['modeb_rounds']} "
              f"FULL {e['full']}｜converged={c['converged']} "
              f"streak={c['streak']} newA={e['new_accepted_sum_modeA']} "
              f"newB={e['new_accepted_sum_modeB']}")
    print(f"→ 已写 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
