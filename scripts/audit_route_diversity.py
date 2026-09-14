# -*- coding: utf-8 -*-
"""audit_route_diversity.py —— Step 8 §十：发现路线多样性矩阵。

独立路线口径（规格 §十）：
    A 官方枚举 ｜ B 官方全文检索 ｜ C 法律关系扩张 ｜ D 开放网缺口
    （NIM/implementation discovery 记为 N——通道就绪后计入）

**同库换词只算 1 类**：B 类内部的多个检索词/端点只构成一个 route；
只有机制不同（枚举/检索/引用扩张/缺口）才算独立路线。

产物：outputs/audit/route_diversity.json
用法：py scripts/audit_route_diversity.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import yaml  # noqa: E402

PLANS_DIR = ROOT / "sources" / "search-plans"
OUT = ROOT / "outputs" / "audit" / "route_diversity.json"
MIN_ROUTES = 3

#: 路线机制（与 convergence_layers.route_families 同一口径）
MECHANISM = {
    "A": "官方枚举（官网/API 直链目录遍历）",
    "B": "官方全文检索（同一库内换词只算本类 1 条）",
    "C": "法律关系扩张（引用链/修订链）",
    "D": "开放网缺口发现（未覆盖号段/词表差集）",
    "N": "NIM/实施措施发现（通道就绪后计入）",
}


def main() -> int:
    plans = []
    for fp in sorted(PLANS_DIR.glob("*.yaml")):
        doc = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        routes = [str(r) for r in (doc.get("discovery_routes") or [])]
        uniq = sorted(set(routes))
        seed_info = {}
        qs = doc.get("query_set") or {}
        for field, mech in (("fr_agencies", "A"), ("fr_terms", "B"),
                            ("eu_keywords", "C"), ("cross_terms", "D"),
                            ("nim_seeds", "N")):
            vals = qs.get(field) or []
            if vals:
                seed_info[field] = {"mechanism": mech, "count": len(vals)}
        plans.append({
            "plan_id": doc.get("plan_id") or fp.stem,
            "jurisdiction": doc.get("jurisdiction") or doc.get("scope"),
            "file": fp.name,
            "discovery_routes": routes,
            "route_families": uniq,
            "families_count": len(uniq),
            "meets_min_3": len(uniq) >= MIN_ROUTES,
            "mechanism_note": {r: MECHANISM.get(r, "未知") for r in uniq},
            "seed_channels": seed_info,
            "same_library_rule": "同库换词只算 1 类（B 内部不拆分）",
        })
    ok = [p for p in plans if p["meets_min_3"]]
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meets_min": MIN_ROUTES,
        "plans_total": len(plans),
        "plans_meeting_min": len(ok),
        "plans": plans,
        "note_zh": ("纪律：同一数据库内换关键词只算 B 类 1 条；"
                    "计划声明 discovery_routes 为机制字母集合，"
                    "审计以字母集合为唯一计数口径。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("=== Route Diversity 矩阵 ===")
    for p in plans:
        mark = "OK " if p["meets_min_3"] else "不足"
        print(f"  {mark} {p['plan_id']:22s} {str(p['jurisdiction']):7s} "
              f"routes={','.join(p['route_families']) or '-'} "
              f"({p['families_count']}/3)")
    print(f"\n→ {doc['plans_meeting_min']}/{doc['plans_total']} 计划 ≥3 类；"
          f"已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
