# -*- coding: utf-8 -*-
"""列出重判预览中的状态变更明细（不写盘）。

对比 judge_portal_policy 对库内记录的新旧判定，只打印**状态变化**的行。
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.core.relevance import judge_portal_policy  # noqa: E402

OUT = ROOT / "outputs"
PATTERNS = ["eol_*.jsonl", "policy_EU_*.jsonl", "policy_US_*.jsonl"]

decided: set[str] = set()
rd = OUT / "review_decisions.jsonl"
if rd.exists():
    for line in rd.read_text(encoding="utf-8").splitlines():
        try:
            decided.add(json.loads(line)["target_id"])
        except Exception:  # noqa: BLE001
            pass

changed = []
for pat in PATTERNS:
    for fp in sorted(glob.glob(str(OUT / pat))):
        for line in Path(fp).read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if (r.get("evidence_id") or "") in decided:
                continue
            if (r.get("meta") or {}).get("relevance_scenario") == "browser" \
                    or (r.get("channel") == "browser_capture"):
                continue
            old_rel = bool(r.get("relevant"))
            old_rev = bool(r.get("needs_human_review"))
            v = judge_portal_policy(r.get("text") or "", r.get("title") or "")
            new_rel, new_rev = v.relevant, v.needs_human_review
            if (old_rel, old_rev) != (new_rel, new_rev):
                changed.append({
                    "file": Path(fp).name,
                    "eid": r.get("evidence_id"),
                    "old": f"{'rel' if old_rel else 'irr'}{'+rev' if old_rev else ''}",
                    "new": f"{'rel' if new_rel else 'irr'}{'+rev' if new_rev else ''}",
                    "title": (r.get("title") or "")[:100],
                    "hits": v.hits[:3],
                })

print(f"状态变更 {len(changed)} 条：\n")
for c in changed:
    print(f"{c['old']:9s} → {c['new']:9s} {c['eid']}")
    print(f"    {c['title']}")
    print(f"    hits: {c['hits']}")
    print()
