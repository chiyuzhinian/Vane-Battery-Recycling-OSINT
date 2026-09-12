# -*- coding: utf-8 -*-
"""audit_scope_saturation.py —— Phase 4B-1 Step 10 §13：scope 级饱和审计。

四个 scope 独立评价（禁止把 US Federal 当 "United States complete"）。
用法：py scripts/audit_scope_saturation.py [--scope US_FEDERAL] [--json]
产物：outputs/audit/scope_saturation.json
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

from app.policy.backfill import load_records  # noqa: E402
from app.policy.goldset import evaluate as eval_goldset  # noqa: E402
from app.policy.legal_graph import build_family_status  # noqa: E402
from app.policy.scope_saturation import (  # noqa: E402
    SCOPES, scope_identity, scope_novelty, scope_routes, scope_universe,
)
from app.policy.saturation import THRESHOLDS, status_from  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "scope_saturation.json"


def evaluate_scope(scope: str, records: list[dict], gold: dict,
                   fam_unresolved: int) -> dict:
    uni = scope_universe(scope)
    ident = scope_identity(records, scope)
    routes = scope_routes(records, scope)
    novelty = scope_novelty(scope)
    checks = {
        "SG1_source_universe": {
            "mandatory_pct": uni["mandatory_pct"], "critical_pct": uni["critical_pct"],
            "pass": (uni["available"]
                     and uni["mandatory_pct"] >= THRESHOLDS["sg1_mandatory_covered_pct"]
                     and uni["critical_pct"] >= THRESHOLDS["sg1_critical_covered_pct"]),
        },
        "SG2_source_health": {"blocked": uni.get("blocked", []),
                              "pass": len(uni.get("blocked", [])) == 0},
        "SG3_gold_recall": {"recall": gold["recall"], "insufficient": gold["INSUFFICIENT_GOLDSET"],
                            "pass": (gold["recall"] >= THRESHOLDS["sg3_core_recall"]
                                     and not gold["INSUFFICIENT_GOLDSET"])},
        "SG4_precision": {"precision": gold["precision"],
                          "pass": gold["precision"] >= THRESHOLDS["sg4_ab_precision"]},
        "SG5_legal_identity": {"pct": ident["pct"],
                               "pass": ident["pct"] >= THRESHOLDS["sg5_identity_pct"]},
        "SG6_legal_family": {"p0_unresolved": fam_unresolved,
                             "pass": fam_unresolved <= THRESHOLDS["sg6_p0_unresolved"]},
        "SG7_discovery_routes": {**routes,
                                 "pass": routes["count"] >= THRESHOLDS["sg7_routes"]},
        "SG8_marginal_novelty": {**novelty,
                                 "pass": bool(novelty.get("available")
                                              and novelty.get("consecutive_rounds", 0)
                                              >= THRESHOLDS["sg8_consecutive_rounds"])},
        "SG9_high_risk_gap": {"count": fam_unresolved, "pass": fam_unresolved == 0},
    }
    passed = sum(1 for c in checks.values() if c["pass"])
    status = status_from(passed, len(checks), len(uni.get("blocked", [])))
    return {"scope_level": scope, "status": status,
            "checks_passed": f"{passed}/{len(checks)}", "checks": checks,
            "universe": uni, "identity": {"pct": ident["pct"],
                                          "complete": ident["complete"],
                                          "total": ident["total"]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records(ROOT)
    gold = eval_goldset()
    fam_unresolved = sum(len(s.unresolved_relations) for s in build_family_status())
    scopes = [args.scope] if args.scope else list(SCOPES)
    results = {s: evaluate_scope(s, records, gold, fam_unresolved) for s in scopes}
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "results": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=== Scope-level Saturation（四个 scope 独立）===")
    for s, res in results.items():
        u = res["universe"]
        print(f"\n[{s}] {res['status']}  {res['checks_passed']}")
        print(f"  SG1 源宇宙：mandatory {u['mandatory']['covered']}/{u['mandatory']['total']}"
              f" ({u['mandatory_pct']}%) ｜ critical {u['critical']['covered']}/"
              f"{u['critical']['total']} ({u['critical_pct']}%)")
        print(f"  SG5 身份：{res['identity']['pct']}%"
              f" ｜ SG8：novel={res['checks']['SG8_marginal_novelty'].get('novel_rate')}"
              f" 轮次={res['checks']['SG8_marginal_novelty'].get('total_rounds', 0)}")
        opens = u.get("open_roles") or []
        if opens:
            print(f"  未覆盖角色：{', '.join(o['role'] + '=' + o['status'] for o in opens[:6])}"
                  + (" …" if len(opens) > 6 else ""))
    print(f"\n→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
