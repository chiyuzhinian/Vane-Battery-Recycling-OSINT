# -*- coding: utf-8 -*-
"""Batch 1C —— 语料标题补全 overlay（原始 evidence 不可变纪律）。

问题：
  · 公报型通道的 persisted 记录 title 常是纯编号（"273/2021 Sb."、
    "365/2015 Z. z."、"DECRETO LEGISLATIVO … n. 188"）——正文首段
    才含官方题名（"o výrobcích s ukončenou životností"、"Attuazione della
    direttiva 2006/66/CE concernente pile, accumulatori…"）。
  · 标题缺电池/体系词 → 分类被低估（IT 全 C）＋业务表「政策名称」
    不可读。

方案：
  · 不改写 outputs/*.jsonl（原始 evidence 不可变）；
  · 生成 overlay：outputs/corpus_title_overlay.jsonl
    {evidence_id, title_overlay, method, source_id, added_chars}
  · 验收构建器（build_acceptance_table.py）装载时合并 overlay
    （classification 与业务表均用合并后视图；审计可回溯）。

判定候选：title 不含电池对象词（多语）且不含体系号（2006/66 等），
且正文前 4000 字命中电池词 → 从正文中截取电池词近邻 ≤200 字。

用法：
  py scripts/enrich_corpus_titles.py            # 写 overlay
  py scripts/enrich_corpus_titles.py --show     # 抽样打印不写
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_acceptance_table import BATCH1, jid_of, load_records  # noqa

OUT = ROOT / "outputs" / "overlays" / "corpus_title_overlay.jsonl"

#: 标题已含这些词 → 无需补全；snippet 必须含这些锚词 → 否则丢弃
OBJ_RE = re.compile(
    r"batter|bateri|batteri|akkumul|akumul|accumul|\bpile\b|\bbatterie\b",
    re.I)
SYS_RE = re.compile(r"2006/66|2023/1542|2000/53|2024/1157|2008/98")

#: 公报卷宗（整期）标题——不补全（法律文本在期内独立文档）
ISSUE_WRAP_RE = re.compile(r"^MAGYAR\s+K[OÖ]ZL[OÖ]NY", re.I)

#: CZ psp 详情页头部模板噪音（"Předpis N Sb. Citace N Sb. Název "）
_CZ_HEAD_RE = re.compile(
    r"^P[řr]edpis\s+\S+(?:\s+\S+)?\s+Citace\s+\S+(?:\s+\S+)?\s+"
    r"N[áa]zev\s+", re.I)


def snippet_of(text: str) -> tuple[str, int]:
    """正文 → 电池词近邻截断（≤200 字）。返回 (snippet, hit_pos)。"""
    m = OBJ_RE.search(text[:4000])
    if not m:
        return "", -1
    i = m.start()
    lo = max(0, i - 110)
    seg = text[lo:i + 150]
    seg = re.sub(r"\s+", " ", seg).strip()
    seg = _CZ_HEAD_RE.sub("", seg)
    # 截断到句读（若中途遇到 '. ' 且位置 >30）
    dot = seg.find(". ")
    if 28 < dot < 180:
        seg = seg[:dot + 1]
    seg = seg[:200]
    # 质量门：snippet 必须含电池/体系锚词（否则丢弃）
    if not (OBJ_RE.search(seg) or SYS_RE.search(seg)):
        return "", -1
    return seg, i


def main() -> int:
    args = argparse.ArgumentParser()
    args.add_argument("--show", action="store_true")
    args = args.parse_args()

    records = load_records(ROOT)
    rows = []
    shown = 0
    for r in records:
        if jid_of(r) not in BATCH1:
            continue
        title = str(r.get("title") or "")
        if OBJ_RE.search(title) or SYS_RE.search(title):
            continue                      # 标题已含对象/体系词 → 无需补
        if ISSUE_WRAP_RE.search(title):
            continue                      # 公报整期卷宗 → 不补
        text = str(r.get("text") or "")
        seg, pos = snippet_of(text)
        if not seg or pos < 0:
            continue
        new_title = f"{title} — {seg}"
        if len(new_title) <= len(title) + 30:
            continue
        rows.append({
            "evidence_id": r.get("evidence_id"),
            "source_id": r.get("source_id"),
            "jurisdiction": jid_of(r),
            "title_overlay": new_title[:280],
            "method": "body_battery_neighborhood",
            "added_chars": len(new_title) - len(title),
        })
        if args.show and shown < 24:
            shown += 1
            print(f"[{jid_of(r)}] {r.get('evidence_id')}")
            print(f"  base: {title[:100]}")
            print(f"  new : {new_title[:200]}")

    print(f"\ncandidates: {len(rows)}")
    if args.show:
        return 0
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False)
                             for x in rows) + "\n", encoding="utf-8")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
