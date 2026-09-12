# -*- coding: utf-8 -*-
"""抽样核查 NIM 采集质量：每国打印 tier1 前几条 + 统计。"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

fp = sorted(glob.glob(str(ROOT / "outputs" / "eol_MS_nim_*.jsonl")))[-1]
print(f"文件: {Path(fp).name}\n")
rows = [json.loads(l) for l in open(fp, encoding="utf-8")]
print(f"总记录 {len(rows)}")

by_cc = collections.defaultdict(list)
for r in rows:
    cc = (r.get("source_id") or "").replace("eu_nim_", "").upper()
    by_cc[cc].append(r)

for cc in sorted(by_cc):
    items = by_cc[cc]
    auto = [r for r in items if not r["needs_human_review"]]
    rev = [r for r in items if r["needs_human_review"]]
    print(f"\n===== {cc}: {len(items)}（自动 {len(auto)} / 待审 {len(rev)}）=====")
    for r in auto[:4]:
        print(f"  ✅ {r['title'][:120]}")
    for r in rev[:2]:
        print(f"  🟡 {r['title'][:120]}")
