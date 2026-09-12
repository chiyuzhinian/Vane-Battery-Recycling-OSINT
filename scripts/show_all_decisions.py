# -*- coding: utf-8 -*-
"""查看全部审核决策 + 关联的记录内容（学习用户的验收标准）。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

decisions = [json.loads(l) for l in
             open(ROOT / "outputs" / "review_decisions.jsonl", encoding="utf-8")]
print(f"决策总数 {len(decisions)}\n")

# 索引全部记录
recs: dict[str, dict] = {}
for fp in glob.glob(str(ROOT / "outputs" / "*.jsonl")):
    if Path(fp).name.startswith("_"):
        continue
    for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        eid = r.get("evidence_id")
        if eid and eid not in recs:
            recs[eid] = r

for d in decisions:
    tid = d.get("target_id", "")
    r = recs.get(tid) or {}
    print("=" * 100)
    print(f"[{d.get('verdict', '?').upper()}] {tid}  @ {d.get('decided_at', '')[:19]}")
    if d.get("reason"):
        print(f"  原因: {d['reason']}")
    t = (r.get("title") or "")[:150]
    print(f"  标题: {t}")
    if r.get("source_id"):
        print(f"  来源: {r['source_id']}  判定: relevant={r.get('relevant')} "
              f"score={r.get('relevance_score')} review={r.get('needs_human_review')}")
    print(f"  hits: {r.get('hits')}")
