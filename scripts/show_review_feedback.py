# -*- coding: utf-8 -*-
"""审核反馈汇总 —— 我（规则校准）读取用户拒绝原因/备注的入口。

用户需求（2026-09-12）：「页面审核界面点开附上收录的原因，同时可以填写
拒绝原因，你收到这些后端可以调整」。

本脚本把 review_decisions.jsonl 的**备注**与记录上下文（标题/hits/来源）
拼在一起，按裁决分类输出，供校准判定规则：

    py scripts/show_review_feedback.py            # 摘要 + 全部备注
    py scripts/show_review_feedback.py --last 20  # 只看最近 20 条
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

VERDICT_ZH = {"relevant": "✅相关", "irrelevant": "❌无关", "uncertain": "🟡待定"}


def load_decisions() -> list[dict]:
    p = ROOT / "outputs" / "review_decisions.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def load_records() -> dict[str, dict]:
    recs: dict[str, dict] = {}
    for fp in glob.glob(str(ROOT / "outputs" / "*.jsonl")):
        if Path(fp).name.startswith(("_", "review_decisions")):
            continue
        for line in Path(fp).read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = r.get("evidence_id")
            if eid and eid not in recs:
                recs[eid] = r
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=0, help="只看最近 N 条")
    args = ap.parse_args()

    decisions = load_decisions()
    recs = load_records()
    if args.last:
        decisions = decisions[-args.last:]

    by_v = Counter(d.get("verdict") for d in decisions)
    print(f"审核决策 {len(decisions)} 条："
          + "  ".join(f"{VERDICT_ZH.get(k, k)} {v}" for k, v in by_v.items()))
    n_notes = sum(1 for d in decisions if (d.get("reason") or "").strip())
    print(f"带备注的决策：{n_notes} 条\n")

    # ---- ① 备注明细（校准的核心输入）----
    noted = [d for d in decisions if (d.get("reason") or "").strip()]
    if noted:
        print("=" * 100)
        print("① 带备注的决策（用户原话 —— 校准规则的直接依据）")
        print("=" * 100)
        for d in noted:
            r = recs.get(d.get("target_id", "")) or {}
            print(f"\n[{VERDICT_ZH.get(d.get('verdict'), d.get('verdict'))}] "
                  f"{d.get('target_id')}")
            print(f"   备注: {d['reason']}")
            print(f"   标题: {(r.get('title') or '')[:110]}")
            if r.get("hits"):
                print(f"   机器 hits: {r['hits']}")
            if r.get("source_id"):
                print(f"   来源: {r['source_id']} · channel={r.get('channel')}")

    # ---- ② 最近无备注的裁决（按时间序，便于复盘模式）----
    no_note = [d for d in decisions if not (d.get("reason") or "").strip()]
    if no_note:
        print("\n" + "=" * 100)
        print("② 无备注的裁决（最近 15 条）")
        print("=" * 100)
        for d in no_note[-15:]:
            r = recs.get(d.get("target_id", "")) or {}
            print(f"  [{VERDICT_ZH.get(d.get('verdict'), '?'):6s}] "
                  f"{(r.get('title') or d.get('target_id', ''))[:95]}")

    # ---- ③ 按来源统计裁决分布（找系统性偏差）----
    print("\n" + "=" * 100)
    print("③ 按来源的裁决分布")
    print("=" * 100)
    per_src: dict[str, Counter] = {}
    for d in decisions:
        r = recs.get(d.get("target_id", "")) or {}
        src = r.get("source_id") or "(源级决定)"
        per_src.setdefault(src, Counter())[d.get("verdict")] += 1
    for src, c in sorted(per_src.items()):
        parts = "  ".join(f"{VERDICT_ZH.get(k, k)} {v}" for k, v in c.items())
        print(f"  {src:28s} {parts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
