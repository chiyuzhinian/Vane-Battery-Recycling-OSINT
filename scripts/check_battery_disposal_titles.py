"""核对：标题同时含「电池词」与「处置词」的 FR 记录，各自被判成什么。

用途
----
重判后 FR 侧只剩 3 条自动相关 —— 必须确认这不是漏收。
判据：标题里同时出现
  · 电池词：batter|lithium|accumulator
  · 处置词：recycl|dispos|spent|waste|end-of-life|scrap|black mass|second-life
这样的记录按标准应当至少是「待人工」，若被判「排除」就需要解释。

同时叠加人工审核结果（review_decisions.jsonl）——核验显示必须与面板一致。
"""
from __future__ import annotations

import io
import re
import sys
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BATT = re.compile(r"batter|lithium|accumulator|\bBatterie", re.I)
DISP = re.compile(r"recycl|dispos|spent|waste|end[- ]of[- ]life|scrap|black mass|"
                  r"second[- ]life|salvag|dismantl", re.I)


def load_decisions() -> dict[str, str]:
    """evidence_id -> verdict（人工判定优先）"""
    p = OUT / "review_decisions.jsonl"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("target_type") == "record" and d.get("target_id"):
            out[d["target_id"]] = d.get("verdict") or ""
    return out


def main() -> int:
    decisions = load_decisions()
    seen: dict[str, dict] = {}
    for pat in ("eol_US_*.jsonl", "browser_*.jsonl", "policy_US_*.jsonl"):
        for fp in sorted(glob.glob(str(OUT / pat))):
            for line in io.open(fp, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r.get("url") or r.get("evidence_id") or "").strip()
                if key and key not in seen:
                    seen[key] = r
    rows = list(seen.values())

    hits = [r for r in rows
            if BATT.search(r.get("title") or "")
            and DISP.search(r.get("title") or "")]
    print(f"标题同时含电池词与处置词的记录：{len(hits)} 条\n")

    buckets: dict[str, list[dict]] = {"✅自动相关": [], "🟡待人工": [],
                                      "❌排除": [], "👤人工已判": []}
    for r in hits:
        ev = r.get("evidence_id") or ""
        dec = decisions.get(ev)
        if dec == "relevant":
            buckets["👤人工已判"].append(r)
        elif dec == "irrelevant":
            buckets["👤人工已判"].append(r)
        elif r.get("relevant") and not r.get("needs_human_review"):
            buckets["✅自动相关"].append(r)
        elif r.get("relevant"):
            buckets["🟡待人工"].append(r)
        else:
            buckets["❌排除"].append(r)

    for name, lst in buckets.items():
        print("=" * 76)
        print(f"{name}：{len(lst)} 条")
        print("=" * 76)
        for r in lst[:18]:
            ev = r.get("evidence_id") or ""
            dec = decisions.get(ev)
            note = f"  ← 人工判「{dec}」" if dec else ""
            print(f"  · [{(r.get('meta') or {}).get('type') or r.get('source_id') or '?':18s}]"
                  f" {(r.get('title') or '')[:66]}{note}")
        if len(lst) > 18:
            print(f"  … 另有 {len(lst) - 18} 条")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
