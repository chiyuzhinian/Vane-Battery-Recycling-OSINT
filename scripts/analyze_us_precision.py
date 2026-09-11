"""美国记录的相关性精度分析 —— 回答「现有判定里有多少不是我们要的」。

背景
----
用户在面板上审核美国记录后，给出三个判例（2026-09-12）：

  ❌ `us_fr_2024-08913`  "Interpretation of Foreign Entity of Concern"
     —— DOE 对外国实体定义（FEOC）的司法解释：整篇讲"什么算外国实体"，
        与退役电池怎么处置**毫无关系**。
  ✅ `us_fr_2024-09094`  "Clean Vehicle Credits ... Critical Minerals and
     Battery Components; FEOC" —— IRA 清洁车辆抵免：涉及关键矿物与电池组件
        的实质要求（含回收材料路径），直接驱动电池回收产业。
  ✅ PHMSA "Safety Advisory Notice for the Disposal and Recycling of
     Lithium Batteries in Commercial Transportation" —— 退役锂电池运输去
        处置/回收的合规要求，**标准正样本**。

用户的业务口径（原话）：
    「我需要的是**报废退役电池处置**相关的政策法规，黑粉也有」

据此形成的判据：
  **必须能追到"报废/退役电池的处置链"**（回收 · 处置 · 运输 · 贮存 ·
  拆解 · 黑粉 · 梯次利用 · 报废车），或**直接规制这条链的政策**（如电池
  回收材料含量要求）。
  仅仅"提到电池"的供应链、贸易管制、实体资格、税收抵免程序 → 不算。

本脚本做三件事
--------------
  1. 把"处置链词族"与"周边词族"分开统计 —— 看清 relevant 里有多少
     真落在处置链上；
  2. 列出**仅周边、无处置**的疑似假阳性（含标题），供人工复核；
  3. 按 "文书类型 / 机构 / 标题模板" 聚合疑似假阳性 —— 找出**成批的噪声
     模板**（此前已知：Agency Information Collection Activities 等），
     这样修一条规则能清一片。

用法
----
    py scripts/analyze_us_precision.py
    py scripts/analyze_us_precision.py --dump outputs/_us_suspects.txt
"""
from __future__ import annotations

import io
import re
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

# ============================================================
# 词族：**处置链**（命中即说明真落在"报废退役电池处置"上）
# ------------------------------------------------------------
# ⚠️ 每个词都要能指向"废弃/退出使用"这个状态，而不是"电池"本身。
#    这正是用户判例划出的边界：`battery` 本身不是判据，
#    `battery + 处置动作` 才是。
# ============================================================
DISPOSAL_PATTERNS = [
    r"disposal", r"dispose", r"\brecycl",                 # 回收/处置（recycl* 覆盖 recycling/recycled/recycler）
    r"spent\s+batter", r"end[- ]of[- ]life\s+batter",     # 退役电池
    r"end[- ]of[- ]life\s+vehicle", r"\bELVs?\b",         # 报废车
    r"waste\s+batter", r"batter\w*\s+waste",              # 废电池
    r"black\s+mass", r"masse\s+noire", r"schwarzmasse",   # 黑粉（三语）
    r"second[- ]life", r"repurpos", r"repurposing",       # 梯次利用
    r"salvag", r"dismantl", r"scrap\s+batter",            # 拆解/报废
    r"batter\w*\s+scrap", r"cathode\s+scrap",
    r"damaged[,\s]+defective", r"\bDDR\b",                # 损坏/缺陷/召回电池
    r"\b49\s+CFR\s+17", r"\bUN\s*348[01]\b",              # HMR / UN 编号
    r"battery\s+collection", r"take[- ]back", r"core\s+credit",
]

# ============================================================
# 词族：**周边**（供应链 / 贸易 / 财政工具）—— 单独出现时不构成"处置"
# ============================================================
PERIPHERAL_PATTERNS = [
    r"foreign\s+entit", r"\bFEOC\b", r"supply\s+chain",
    r"domestic\s+content", r"manufactur", r"procurement",
    r"fast[- ]40", r"tax\s+credit", r"income\s+tax",
    r"trade\s+zone", r"tariff", r"export\s+control",
    r"information\s+collection", r"paperwork\s+reduction",
]

_DISP_RE = re.compile("|".join(DISPOSAL_PATTERNS), re.I)
_PERI_RE = re.compile("|".join(PERIPHERAL_PATTERNS), re.I)

# 批量行政文书模板（此前踩过：这些是"固定模板"的成批噪声）
BATCH_TEMPLATES = [
    r"agency information collection activities",
    r"special permits?;", r"notice of application",
    r"foreign[- ]trade zone",
    r"proposed collection", r"submission for omb review",
]


def load_us() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    pats = ["eol_US_*.jsonl", "browser_US*.jsonl"]
    for pat in pats:
        for fp in sorted(glob.glob(str(OUT / pat))):
            for line in io.open(fp, encoding="utf-8").read().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r.get("url") or r.get("evidence_id") or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=None,
                    help="把疑似假阳性清单写到该文件")
    args = ap.parse_args()

    rows = load_us()
    rel = [r for r in rows if r.get("relevant")]
    print(f"US 记录 {len(rows)} 条，其中机器判相关 {len(rel)} 条")
    print(f"待人工复核 {sum(1 for r in rows if r.get('needs_human_review'))} 条\n")

    buckets = collections.Counter()
    suspects: list[dict] = []
    for r in rel:
        blob = f"{r.get('title') or ''} {r.get('text') or ''}"
        d = bool(_DISP_RE.search(blob))
        p = bool(_PERI_RE.search(blob))
        if d and p:
            buckets["处置+周边"] += 1
        elif d:
            buckets["仅处置"] += 1
        elif p:
            buckets["仅周边（疑似假阳性）"] += 1
            suspects.append(r)
        else:
            buckets["两者皆无（需人工看）"] += 1

    print("=" * 78)
    print("分桶（以用户判例建立的判据：必须落在处置链上）")
    print("=" * 78)
    for k, v in buckets.most_common():
        print(f"  {k:24s} {v:5d}")

    print()
    print("=" * 78)
    print("疑似假阳性的**模板聚类**（修一条规则能清一片）")
    print("=" * 78)
    by_temp: dict[str, list[dict]] = collections.defaultdict(list)
    other: list[dict] = []
    for r in suspects:
        t = (r.get("title") or "").lower()
        hit = None
        for pat in BATCH_TEMPLATES:
            if re.search(pat, t):
                hit = pat
                break
        if hit:
            by_temp[hit].append(r)
        else:
            other.append(r)
    for pat, lst in sorted(by_temp.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(lst):4d} 条  模板: /{pat}/")
    print(f"  {len(other):4d} 条  其他（无固定模板）")

    print()
    print("=" * 78)
    print("其他疑似假阳性 —— 前 30 条标题（请人工扫一眼）")
    print("=" * 78)
    for r in other[:30]:
        print(f"  · [{(r.get('meta') or {}).get('type') or '?':10s}] "
              f"{(r.get('title') or '')[:104]}")

    if args.dump:
        p = Path(args.dump)
        with io.open(p, "w", encoding="utf-8") as f:
            for r in suspects:
                f.write(json.dumps({
                    "evidence_id": r.get("evidence_id"),
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "type": (r.get("meta") or {}).get("type"),
                    "agencies": (r.get("meta") or {}).get("agencies"),
                }, ensure_ascii=False) + "\n")
        print(f"\n清单已写入 {p}（{len(suspects)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
