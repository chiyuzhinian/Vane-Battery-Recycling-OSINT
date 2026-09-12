"""看清欧盟侧现状 —— "之前好多都是无关的"到底长什么样（Phase 1）。

用户第二轮确认的核心原话：
    「在内容上相关性强一致就行 后续再考虑字段设计问题
      现在最重要满足内容相关性 **之前好多都是无关的**」

本脚本把欧盟侧（含浏览器通道）当前判为 relevant 的记录**全部列出**，
按来源分组、附命中依据 —— 用于人工快速辨别哪些"其实无关"，
进而定位判定词表的漏洞。

用法
----
    py scripts/show_eu_now.py             # 概览 + 每源前 25 条
    py scripts/show_eu_now.py --all       # 全部列出
"""
from __future__ import annotations

import io
import sys
import glob
import json
import argparse
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="列出全部")
    args = ap.parse_args()

    seen: dict[str, dict] = {}
    pats = ["eol_EU_*.jsonl", "browser_*.jsonl", "policy_EU_*.jsonl"]
    for pat in pats:
        for fp in sorted(glob.glob(str(OUT / pat))):
            try:
                text = io.open(fp, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            for line in text.splitlines():
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

    eu = [r for r in rows
          if (r.get("source_id") or "").startswith(("eu_", "fr_", "de_", "nl_", "es_", "browser_"))]
    rel = [r for r in eu if r.get("relevant")]
    print(f"全库 {len(rows)} 条（去重）；欧盟相关范围 {len(eu)} 条，其中 relevant {len(rel)} 条")
    print(f"relevant 中待人工：{sum(1 for r in rel if r.get('needs_human_review'))} 条\n")

    by_src: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rel:
        by_src[r.get("source_id") or "?"].append(r)

    for sid, lst in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        print("=" * 80)
        print(f"▍{sid} —— {len(lst)} 条")
        print("=" * 80)
        show = lst if args.all else lst[:25]
        for r in show:
            hr = "🟡" if r.get("needs_human_review") else "  "
            hits = ",".join((r.get("hits") or [])[:2])
            print(f" {hr} [{(r.get('evidence_id') or '')[:28]:28s}] "
                  f"{(r.get('title') or '')[:88]}")
            if hits:
                print(f"      └ {hits[:96]}")
        if len(lst) > len(show):
            print(f"  … 另有 {len(lst) - len(show)} 条（--all 全列）")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
