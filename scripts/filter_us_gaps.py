# -*- coding: utf-8 -*-
"""从 US 缺口候选中筛选「边界内」文书（标题级粗筛）。

FR 的 conditions[term] 是 OR 模糊匹配 → 候选里大量噪声。
本脚本按「电池/车辆/黑粉 × 处置语义」在**标题**上过滤，
再用 judge_portal_policy 精筛，输出值得补采的清单。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.core.relevance import judge_portal_policy  # noqa: E402

OUT = ROOT / "outputs"
src = OUT / "_us_gap_candidates.json"
rows = json.loads(src.read_text(encoding="utf-8"))
print(f"候选总数 {len(rows)}")

OBJ = re.compile(r"batter|lithium|black mass|vehicle|shredd", re.I)
NOISE = re.compile(
    r"agency information collection|special permits?|medicare|arms sales|"
    r"procurement list|reactor|oil and gas|fish and wildlife|"
    r"conservation practices|e911|transmission planning|fuel economy|"
    r"climate-related disclosures|rail construction|inpatient|"
    r"physician fee|postmarketing|public hearing", re.I)

hits = []
for r in rows:
    t = r["title"]
    if not OBJ.search(t):
        continue
    if NOISE.search(t):
        continue
    v = judge_portal_policy(t + "\n" + (r.get("agencies") or ""), t)
    if v.relevant:
        hits.append((r, v))

print(f"标题粗筛+判定后 {len(hits)} 条：\n")
for r, v in sorted(hits, key=lambda x: x[0]["date"], reverse=True):
    flag = "🟡" if v.needs_human_review else "✅"
    print(f"{flag} [{v.score}] {r['date']} [{r['type']}]")
    print(f"    {r['title']}")
    print(f"    {r['agencies']}")
    print(f"    hits: {v.hits[:2]}")
    print(f"    {r['url']}")
    print()

if hits:
    p = OUT / "_us_gap_filtered.json"
    p.write_text(json.dumps([r for r, _ in hits], ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print(f"→ 已写出 {p}")
