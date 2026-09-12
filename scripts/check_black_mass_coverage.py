# -*- coding: utf-8 -*-
"""黑粉（多语言）在库内的覆盖检查 —— 标题优先。"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

BM = re.compile(r"black\s*mass|masse\s*noire|schwarzmasse|zwarte\s*massa|"
                r"masa\s*negra|黑粉", re.I)

rows: dict[str, dict] = {}
for fp in sorted(glob.glob(str(ROOT / "outputs" / "*.jsonl"))):
    if Path(fp).name.startswith(("_", "review")):
        continue
    for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        eid = r.get("evidence_id")
        if eid and eid not in rows:
            rows[eid] = r

title_hits, text_hits = [], []
for eid, r in rows.items():
    t = (r.get("title") or "")
    x = (r.get("text") or "")
    if BM.search(t):
        title_hits.append(r)
    elif BM.search(x):
        text_hits.append(r)

print(f"库内总记录 {len(rows)}")
print(f"\n=== 标题含黑粉词：{len(title_hits)} 条 ===")
for r in title_hits:
    flag = "✅" if r.get("relevant") else "❌"
    print(f"  {flag} [{r.get('source_id')}] {r['title'][:110]}")

print(f"\n=== 仅正文含黑粉词：{len(text_hits)} 条（抽样 15）===")
for r in text_hits[:15]:
    flag = "✅" if r.get("relevant") else "❌"
    print(f"  {flag} [{r.get('source_id')}] {r['title'][:100]}")
