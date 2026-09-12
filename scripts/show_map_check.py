# -*- coding: utf-8 -*-
"""查看面板 /api/map 的地区统计（脚本化，避免内联引号问题）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

d = json.loads((ROOT / "outputs" / "_map_check.json").read_text(encoding="utf-8"))
rows = sorted(d["regions"], key=lambda r: -r["total"])
print(f"{'代码':6s} {'名称':10s} {'总数':>6s} {'相关':>6s} {'待审':>6s} {'源数':>4s}")
for r in rows:
    print(f"{r['code']:6s} {r['name']:10s} {r['total']:>6d} {r['relevant']:>6d} "
          f"{r['needs_review']:>6d} {r['source_count']:>4d}")
