# -*- coding: utf-8 -*-
"""打印指定记录完整标题与 meta。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

TARGETS = {"eu_32025R2289", "eu_32025R0606"}
seen = set()
for fp in sorted(glob.glob(str(ROOT / "outputs" / "eol_*.jsonl"))):
    for line in open(fp, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        eid = r.get("evidence_id")
        if eid in TARGETS and eid not in seen:
            seen.add(eid)
            print("=" * 110)
            print(eid)
            print(r.get("title"))
            print(f"meta: {json.dumps(r.get('meta') or {}, ensure_ascii=False)[:400]}")
            print()
