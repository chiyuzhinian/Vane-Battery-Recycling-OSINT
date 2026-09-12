# -*- coding: utf-8 -*-
"""定向补采欧盟发现缺口（discover_eu_acts 的发现结果 - 库内已有 = 缺口）。

背景
----
`discover_eu_acts.py` 用 6 个标题锚点（电池法/ELV/废物运输/关键原材料/旧电池指令/废物框架）
扫描 EUR-Lex 全库，找到 90 个引用锚点的文书；与库内 CELEX 对比后剩 34 个未收录。
用户要求「在搜索边界范围内，把符合要求的都收录进来」——本脚本把这批缺口拉回，
用判定 2.0（judge_portal_policy）自动分类，落盘为 eol_EU_gap_*.jsonl。

用法
----
    py scripts/collect_eu_gaps.py --dry-run       # 只看缺口清单
    py scripts/collect_eu_gaps.py                 # 抓取 + 判定 + 落盘
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

from app.connectors import get_connector  # noqa: E402
from app.core.relevance import judge_portal_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"


def load_gaps(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("gaps", [])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(OUT / "_gap_discovered.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gaps = load_gaps(Path(args.src))
    celexes = [g["celex"] for g in gaps]
    print(f"缺口 {len(celexes)} 条：")
    for g in gaps:
        print(f"  · {g['celex']:<18} {g['date']}  {g['title'][:70]}")

    if args.dry_run:
        return 0

    print(f"\n🇪🇺 从 EUR-Lex 抓取 {len(celexes)} 个 CELEX …")
    async with get_connector("eur_lex") as conn:
        items = await conn.fetch_celex_batch(celexes)
    print(f"  → 取回 {len(items)} 条\n")

    # 判定（portal 场景，与全库重判一致）
    rows = []
    stats = {"relevant": 0, "review": 0, "rejected": 0}
    for it in items:
        v = judge_portal_policy(it.raw_text or "", it.source_title or "")
        if v.relevant:
            stats["relevant"] += 1
            if v.needs_human_review:
                stats["review"] += 1
        else:
            stats["rejected"] += 1
        rows.append({
            "evidence_id": it.evidence_id,
            "region": "EU",
            "channel": it.channel,
            "source_id": it.source_id,
            "cluster_hint": it.meta.get("cluster_hint"),
            "url": it.source_url,
            "title": it.source_title,
            "publish_date": it.publish_date.isoformat() if it.publish_date else None,
            "publish_date_hint": it.meta.get("publish_date_hint"),
            "relevant": v.relevant,
            "relevance_score": v.score,
            "needs_human_review": v.needs_human_review,
            "hits": v.hits[:5],
            "rejected_by": v.rejected_by,
            "meta": it.meta,
            "text": (it.raw_text or "")[:1200],
            "review_reason": v.review_reason,
        })

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT / f"eol_EU_gap_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  → {path.name}")
    print(f"  总 {len(rows)} | 相关 {stats['relevant']}（待人工 {stats['review']}）| 拒绝 {stats['rejected']}")
    print("\n=== 判定明细 ===")
    for r in sorted(rows, key=lambda x: -(x["relevance_score"] or 0)):
        flag = "✅" if r["relevant"] and not r["needs_human_review"] else (
            "🟡" if r["relevant"] else "❌")
        reason = r["rejected_by"] or ""
        print(f"  {flag} [{r['relevance_score']}] {r['evidence_id']:<20} {reason[:50]}")
        print(f"      {r['title'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
