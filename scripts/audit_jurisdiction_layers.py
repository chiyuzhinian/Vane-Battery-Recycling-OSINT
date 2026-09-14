# -*- coding: utf-8 -*-
"""audit_jurisdiction_layers.py —— Step 1：三层收敛状态（plan / eligible / near-sat）。

产物：outputs/audit/jurisdiction_layers.json
数据源：契约注册表 · discovery_rounds（plan_convergence + 轮次）·
        专线 identity 完整度 · collection failures（未决）。

用法：py scripts/audit_jurisdiction_layers.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_records  # noqa: E402
from app.policy.convergence_layers import (  # noqa: E402
    evaluate_jurisdiction, layer_summary,
)
from app.policy.identity_jurisdiction import (  # noqa: E402
    dedicated_identity_completeness,
)
from app.policy.jurisdiction_coverage import (  # noqa: E402
    load_failures, unresolved_failures,
)
from app.policy.jurisdiction_map import records_of  # noqa: E402
from app.policy.jurisdiction_onboarding import build_contract_registry  # noqa: E402

INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
OUT = ROOT / "outputs" / "audit" / "jurisdiction_layers.json"

#: pilot + 参考管辖地（2B0 评估范围）
TARGETS = ("SE", "FI", "US-CA", "US-WA", "DE", "NL", "ES", "FR")

PLAN_BY_JID = {"SE": "SE_PLAN_V2", "FI": "FI_PLAN_V1",
               "US-CA": "US_CA_PLAN_V2", "US-WA": "US_WA_PLAN_V2"}


def main() -> int:
    contracts = {c["jurisdiction_id"]: c
                 for c in build_contract_registry()["contracts"]}
    idx = (json.loads(INDEX.read_text(encoding="utf-8"))
           if INDEX.exists() else {})
    all_rounds = idx.get("rounds") or []
    plan_conv = idx.get("plan_convergence") or {}
    records = load_records(ROOT)
    failures = load_failures()

    rows: dict[str, dict] = {}
    for jid in TARGETS:
        contract = contracts.get(jid)
        level = (contract or {}).get("level", "member_state"
                                     if jid in ("DE", "NL", "ES", "FR", "SE",
                                                "FI") else "state")
        plan_id = PLAN_BY_JID.get(jid, "")
        plan_rounds = [r for r in all_rounds if r.get("plan_id") == plan_id] \
            if plan_id else []
        conv = plan_conv.get(
            next((r.get("plan_hash", "")[:12] for r in plan_rounds
                  if r.get("plan_hash")), ""), None)
        # 专线 identity 口径（P0-A3 修复）
        jrows = records_of(records, jid)
        ident = dedicated_identity_completeness(jrows, jid)
        # 未决 critical 失败：collection failures 中该管辖地未解析项
        raw_f = [e for e in failures if e.get("jurisdiction") == jid]
        unresolved = unresolved_failures(raw_f, jrows)
        rows[jid] = evaluate_jurisdiction(
            jid=jid, level=level, contract=contract, plan_convergence=conv,
            rounds=plan_rounds, identity_pct=ident["pct"],
            unresolved_critical_failures=unresolved, plan_id=plan_id)
        rows[jid]["identity_dedicated"] = ident

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "note": ("plan_converged ≠ jurisdiction_eligible；eligibility 硬闸门见 "
                 "convergence_layers.py（critical 100% / EU≥5·7 US≥6·8 / "
                 "routes≥3 / identity≥90 / 无未决 critical 失败）"),
        "jurisdictions": rows,
        "summary": layer_summary(rows),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    s = payload["summary"]
    print("=== Jurisdiction Layers ===")
    print(f"评估 {s['total']} ｜ plan_converged {s['plan_converged']} ｜ "
          f"eligible {s['eligible']} ｜ near_saturated {s['near_saturated']}")
    for jid, r in rows.items():
        c = r["checks"]
        flags = "".join("✓" if c[k] else "✗" for k in (
            "critical_roles_100", "mandatory_coverage_min",
            "route_families_min_3", "identity_min_90",
            "no_unresolved_critical_failure"))
        print(f"  {jid:6s} {r['state']:32s} cov={r['mandatory_coverage']:5s} "
              f"routes={','.join(r['route_families']) or '-':6s} "
              f"id={r['identity_pct']:5.1f}% 闸门[{flags}]")
    print(f"→ 已写 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
