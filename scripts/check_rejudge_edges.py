"""重判边界核查 —— 防两类错：误杀（该留的被排）与误收（噪声变相关）。

背景
----
`rejudge_us_standard.py` 预览显示 557 条被排除、6 条新变相关。
在落盘之前必须核查两类边界：

  ① **误杀**：旧「黑粉四线」命中的记录被程序性规则排掉了吗？
     （黑粉四线是用户的业务重点，绝不能整类消失）
  ② **误收**：原本被排除、现在变自动相关的 6 条是什么？
     （突然变相关的必须能解释清楚）
  ③ **疑似漏排**：含危险货物/车辆运输语义、但标题无电池词的记录
     （如 "Hazmat Transportation Risks: Heavy-Duty Electric..."）
     它们被排是否合理？

用法
----
    py scripts/check_rejudge_edges.py
"""
from __future__ import annotations

import io
import sys
import glob
import json
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge_portal_policy as J  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for fp in sorted(glob.glob(str(ROOT / "outputs" / "eol_US_*.jsonl"))):
        for line in io.open(fp, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    rows = load_rows()
    print(f"US 记录 {len(rows)} 行\n")

    # ---- ① 黑粉线命中，但新判据排掉了 ----
    print("=" * 78)
    print("① 旧「黑粉四线」命中 → 现被排除（检查是否误杀）")
    print("=" * 78)
    killed_lines: list[tuple[dict, list[str]]] = []
    for r in rows:
        h = " ".join(r.get("hits") or [])
        if "line:" not in h or not r.get("relevant"):
            continue
        v = J(r.get("text") or "", r.get("title") or "")
        if not v.relevant:
            killed_lines.append((r, v.hits))
    by_title: dict[str, int] = collections.Counter()
    for r, _ in killed_lines:
        t = (r.get("title") or "")[:60]
        by_title[t] += 1
    print(f"  共 {len(killed_lines)} 条；按标题聚类：")
    for t, n in by_title.most_common(20):
        print(f"    {n:3d} × {t}")
    print()
    print("  逐条（前 10）：")
    for r, nh in killed_lines[:10]:
        rr = r.get("review_reason") or ""
        print(f"    · {(r.get('title') or '')[:76]}")
        print(f"       旧hits={(r.get('hits') or [])[:2]} 新hits={nh[:2]}")

    # ---- ② 原排除 → 现自动相关 ----
    print()
    print("=" * 78)
    print("② 原「排除」→ 现「自动相关」（突然变相关的必须能解释）")
    print("=" * 78)
    gained = []
    for r in rows:
        if r.get("relevant"):
            continue
        v = J(r.get("text") or "", r.get("title") or "")
        if v.relevant and not v.needs_human_review:
            gained.append((r, v))
    for r, v in gained:
        print(f"  · {(r.get('title') or '')[:78]}")
        print(f"      hits={v.hits[:3]}  score={v.score}")

    # ---- ③ 疑似漏排：含运输/车辆语义但无处置证据 ----
    print()
    print("=" * 78)
    print("③ 含「危险货物/车辆」语义、现被判排除的（人工扫一眼是否有漏）")
    print("=" * 78)
    suspects = []
    for r in rows:
        if not r.get("relevant"):
            continue
        v = J(r.get("text") or "", r.get("title") or "")
        if not v.relevant:
            t = (r.get("title") or "").lower()
            if "hazmat" in t or "hazardous materials" in t or "vehicle" in t:
                suspects.append(r)
    for r in suspects[:15]:
        print(f"  · [{(r.get('meta') or {}).get('type') or '?':14s}] "
              f"{(r.get('title') or '')[:88]}")
    print(f"  共 {len(suspects)} 条")

    # ---- ④ 标题含电池词、但仍被排除的（最可能藏意外误杀的一类）----
    print()
    print("=" * 78)
    print("④ 标题含「battery/lithium」但被排除的（check 是否有意外）")
    print("=" * 78)
    titled_batt = []
    for r in rows:
        if not r.get("relevant"):
            continue
        t = (r.get("title") or "").lower()
        if "batter" not in t and "lithium" not in t:
            continue
        v = J(r.get("text") or "", r.get("title") or "")
        if not v.relevant:
            titled_batt.append(r)
    for r in titled_batt[:25]:
        print(f"  · [{(r.get('meta') or {}).get('type') or '?':14s}] "
              f"{(r.get('title') or '')[:86]}")
    print(f"  共 {len(titled_batt)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
