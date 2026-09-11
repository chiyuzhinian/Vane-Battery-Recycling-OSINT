"""查看美国记录重判后的最终状态 —— 核验标准样本 + 逐档清单。

为什么需要一个专门的核验脚本
----------------------------
重判把 557 条噪声排出去，但也必须确认**没有把标准样本排掉**：
  · PHMSA 安全通告（用户指定的基准）必须仍在
  · EU 电池法、ELV 相关必须仍在
  · 用户标注 related 的记录必须仍在
另外要能一眼看清「自动相关 / 待人工 / 排除」各档的构成 ——
避免"过滤过头"或"漏掉明显相关"这类沉默错误。

用法
----
    py scripts/show_us_final.py                 # 概览
    py scripts/show_us_final.py --review 30     # 待人工清单前 30 条
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

# 必须存活的基准记录（用户判例 + 关键法规）
MUST_KEEP = {
    "c3cc4ef51af4cfe3": "PHMSA 安全通告（用户指定的标准）",
    "us_fr_2024-09094": "FR 清洁车辆抵免（用户标注 relevant）",
}


def load_unique() -> dict[str, dict]:
    seen: dict[str, dict] = {}
    pats = ["eol_US_*.jsonl", "browser_*.jsonl", "policy_US_*.jsonl"]
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
    return seen


def load_decisions() -> dict[str, str]:
    """evidence_id → 人工 verdict。

    ⚠️ 核验显示**必须叠加人工审核**，否则会把"用户已判不相关"的记录
       重新展示成"自动相关"（重判有意跳过已审核记录，字段仍是旧值）。
    """
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", type=int, default=0,
                    help="打印前 N 条待人工清单")
    ap.add_argument("--relevant", type=int, default=30,
                    help="打印前 N 条自动相关清单（默认 30）")
    args = ap.parse_args()

    rows = list(load_unique().values())
    decisions = load_decisions()
    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        ev = r.get("evidence_id") or ""
        dec = decisions.get(ev)
        if dec == "relevant":
            buckets["👤人工判相关"].append(r)
        elif dec == "irrelevant":
            buckets["👤人工判不相关"].append(r)
        elif r.get("relevant") and not r.get("needs_human_review"):
            buckets["自动相关"].append(r)
        elif r.get("relevant"):
            buckets["待人工"].append(r)
        else:
            buckets["排除"].append(r)

    # 只看美国/浏览器通道的记录（EU 侧另有判据）
    us_ish = [r for r in rows
              if (r.get("source_id") or "").startswith(("us_", "browser_"))
              or (r.get("meta") or {}).get("region") == "US"]
    us_b: dict[str, int] = collections.Counter()
    for r in us_ish:
        ev = r.get("evidence_id") or ""
        dec = decisions.get(ev)
        if dec == "relevant":
            us_b["👤人工相关"] += 1
        elif dec == "irrelevant":
            us_b["👤人工不相关"] += 1
        elif r.get("relevant") and not r.get("needs_human_review"):
            us_b["自动相关"] += 1
        elif r.get("relevant"):
            us_b["待人工"] += 1
        else:
            us_b["排除"] += 1

    print(f"全部记录（去重）{len(rows)} 条")
    print(f"US / browser 通道 {len(us_ish)} 条：{dict(us_b)}\n")

    # ---- 基准样本存活检查 ----
    print("=" * 76)
    print("基准样本存活检查（这些必须在）")
    print("=" * 76)
    by_ev = {}
    for r in rows:
        ev = r.get("evidence_id") or ""
        if ev in MUST_KEEP:
            by_ev[ev] = r
    for ev, why in MUST_KEEP.items():
        r = by_ev.get(ev)
        if not r:
            print(f"  ⚠️ 未找到 {ev} —— {why}")
            continue
        mark = ("✅相关" if r.get("relevant") and not r.get("needs_human_review")
                else ("🟡待人工" if r.get("relevant") else "❌排除"))
        print(f"  {mark}  {why}")
        print(f"         {(r.get('title') or '')[:70]}")
    # PHMSA 相关记录（同站可能多条）
    ph = [r for r in rows if (r.get("source_id") or "") == "browser_phmsa"]
    print(f"  PHMSA 通道共 {len(ph)} 条："
          f"{sum(1 for r in ph if r.get('relevant'))} 相关 / "
          f"{len(ph) - sum(1 for r in ph if r.get('relevant'))} 排除")

    # ---- 自动相关清单（叠加人工判定）----
    print()
    print("=" * 76)
    print(f"自动相关（{len(buckets['自动相关'])} 条 —— 全列）")
    print("=" * 76)
    for r in buckets["自动相关"]:
        print(f"  · [{r.get('source_id')}] {(r.get('title') or '')[:80]}")
        if r.get("hits"):
            print(f"      hits={r['hits'][:2]}")
    for name in ("👤人工判相关", "👤人工判不相关"):
        if not buckets[name]:
            continue
        print()
        print(f"{name}（{len(buckets[name])} 条）")
        for r in buckets[name][:10]:
            print(f"  · {(r.get('title') or '')[:78]}")

    # ---- 待人工清单 ----
    if args.review:
        print()
        print("=" * 76)
        print(f"待人工（{len(buckets['待人工'])} 条 —— 前 {args.review}）")
        print("=" * 76)
        for r in buckets["待人工"][:args.review]:
            why = (r.get("review_reason") or "")[:40]
            print(f"  · {(r.get('title') or '')[:74]}")
            print(f"      {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
