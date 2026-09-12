# -*- coding: utf-8 -*-
"""打印补采文件的全部记录标题，供人工核查判定。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

files = sorted(glob.glob(str(ROOT / "outputs" / "eol_EU_gap_*.jsonl")))
if not files:
    print("未找到 eol_EU_gap_*.jsonl")
    raise SystemExit(1)
fp = files[-1]
print(f"文件: {Path(fp).name}\n")
rows = [json.loads(line) for line in open(fp, encoding="utf-8")]
for r in sorted(rows, key=lambda x: (-(x["relevance_score"] or 0), x["evidence_id"])):
    flag = "✅" if r["relevant"] and not r["needs_human_review"] else (
        "🟡" if r["relevant"] else "❌")
    print(f"{flag} [{r['relevance_score']}] {r['evidence_id']}")
    print(f"    {r['title'][:160]}")
    if r["rejected_by"]:
        print(f"    ↳ rejected_by: {r['rejected_by']}")
    print()
