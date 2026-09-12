# -*- coding: utf-8 -*-
"""refresh_legal_family.py —— Phase 4B-1 Step 7：官方家族关系刷新（Cellar SPARQL）。

流程：
    ① 对每个 P0 root 取 Cellar work URI（CELEX 精确匹配）
    ② 逐个关系谓词查**入边**（谁修订/废止/转化/提案了本法）
    ③ 写 outputs/audit/legal_family_official.json
    ④ 重建 outputs/audit/legal_family_status.json（语料标题证据 + 官方关系合并）

纪律：关系一律来自官方数据；查询执行且为空 → absent_official（官方缺席，非缺口）。
用法：py scripts/refresh_legal_family.py [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors.eur_lex import CDM, EurLexConnector  # noqa: E402
from app.policy.family_official import (  # noqa: E402
    Q_INCOMING, Q_WORK_BY_CELEX, RELATION_PREDICATES, normalize_rows,
)
from app.policy.legal_graph import P0_ROOTS, write_family_audit  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "legal_family_official.json"


async def run(args: argparse.Namespace) -> int:
    conn = EurLexConnector()
    roots: dict[str, dict] = {}
    for root in P0_ROOTS:
        rows = await conn._sparql(Q_WORK_BY_CELEX.format(celex=root))
        work = rows[0].get("work", {}).get("value") if rows else None
        entry: dict = {"work": work, "relations": {}}
        print(f"\n=== {root}（{P0_ROOTS[root]['name']}）===")
        if not work:
            print("  ✗ 未找到 Cellar work（记为缺失）")
            entry["error"] = "work_not_found"
            roots[root] = entry
            continue
        for rel, pred in RELATION_PREDICATES.items():
            try:
                bindings = await conn._sparql(Q_INCOMING.format(
                    pred=CDM + pred, work=work, limit=200))
            except Exception as exc:  # noqa: BLE001
                print(f"  ✗ {rel}: {type(exc).__name__}")
                continue
            norm = normalize_rows(bindings)
            entry["relations"][rel] = norm
            print(f"  · {rel:18s} {len(norm):3d} 条"
                  + (f"  例: {', '.join(r['celex'] for r in norm[:4])}" if norm else ""))
        roots[root] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Cellar SPARQL（publications.europa.eu）",
        "predicates": RELATION_PREDICATES,
        "roots": roots,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    # 规整 map（{root: {REL: rows}}）传给合并器
    official_map = {r: (e.get("relations") or {}) for r, e in roots.items()}
    status_path = write_family_audit()

    # 汇总
    print("\n=== 家族完整性（官方+语料合并）===")
    from app.policy.legal_graph import build_family_status
    statuses = build_family_status(official=official_map)
    for st in statuses:
        print(f"{st.root_act} {st.root_name[:14]:14s} 完整度={st.family_completeness}"
              f" 官方解决={st.resolved_official or '无'}"
              f" 未解决={st.unresolved_relations or '无'}"
              f" 官方缺席={st.absent_official or '无'}")
    total_unresolved = sum(len(s.unresolved_relations) for s in statuses)
    print(f"\nP0 unresolved 总数 = {total_unresolved}")
    print(f"→ 已写 {OUT.name} / {status_path.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
