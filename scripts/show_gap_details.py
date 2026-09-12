# -*- coding: utf-8 -*-
"""查看指定记录的完整标题、hits、meta。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

TARGETS = ("eu_52025AE3982", "eu_52018DC0266", "eu_52024DC0454",
           "eu_52025SC0501", "eu_52025SC0130", "eu_52019DC0166",
           "eu_52020DC0033")

fp = sorted(glob.glob(str(ROOT / "outputs" / "eol_EU_gap_*.jsonl")))[-1]
rows = {json.loads(line)["evidence_id"]: json.loads(line)
        for line in open(fp, encoding="utf-8")}
for eid in TARGETS:
    r = rows.get(eid)
    if not r:
        continue
    print("=" * 110)
    print(f"{eid}  [score={r['relevance_score']} review={r['needs_human_review']}]")
    print(f"标题: {r['title']}")
    print(f"hits: {r['hits']}")
    print()
