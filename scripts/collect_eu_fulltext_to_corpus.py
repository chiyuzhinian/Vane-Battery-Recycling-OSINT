# -*- coding: utf-8 -*-
"""collect_eu_fulltext_to_corpus.py —— 把 sources/eurlex-fulltext/*.txt 接入语料。

背景（2B0 审计 Q3 深挖）：7 部 EU 核心法案全文（含电池法 354K 字符）
早已落盘 sources/eurlex-fulltext/，但 outputs/*.jsonl 里的对应记录
**只有 CELEX 占位（111 字符）**——全文从未进入语料 → topic/黑粉矩阵贫瘠。

本脚本（真实深采接入，不改任何历史文件）：
    · 逐个 .txt：解析头部（CELEX/URL），正文 = 第 4 行起
    · title：优先复用旧语料中 eu_{celex} 占位记录的完整标题（不猜）
    · classify_record 现算 acceptance_class + topic_ids
    · 写 outputs/eu_fulltext_{YYYYMMDD}.jsonl（evidence_id=eu_fulltext_{celex}）

用法：py scripts/collect_eu_fulltext_to_corpus.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.topic_audit import extract_topics_full  # noqa: E402

FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"
MAKE_TEXT_CAP = 400_000          # 单记录文本上限（电池法 354K 可全量）


def _parse_txt(fp: Path) -> tuple[str, str, str]:
    """→ (celex, url, body)。头部为 '# CELEX …' 三行注释。"""
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    celex = fp.stem
    url = ""
    body_start = 0
    for i, ln in enumerate(lines[:6]):
        if ln.startswith("# CELEX"):
            celex = ln.replace("# CELEX", "").strip()
        elif ln.startswith("# http"):
            url = ln.replace("#", "").strip()
        elif not ln.startswith("#") and ln.strip():
            body_start = i
            break
    body = "\n".join(lines[body_start:]).strip()
    return celex, url, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    old = {str(r.get("evidence_id")): r for r in load_records(ROOT)}
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_fp = ROOT / "outputs" / f"eu_fulltext_{ts}.jsonl"
    records: list[dict] = []
    for fp in sorted(FULLTEXT_DIR.glob("*.txt")):
        celex, url, body = _parse_txt(fp)
        if len(body) < 2000:
            print(f"  ⚠️ 跳过 {fp.name}（正文不足 {len(body)}）")
            continue
        placeholder = old.get(f"eu_{celex}") or {}
        title = (placeholder.get("title") or "").strip() \
            or body[:120].replace("\n", " ")
        rec = {
            "evidence_id": f"eu_fulltext_{celex}",
            "channel": "connector", "source_id": "eu_eurlex_fulltext",
            "region": "EU", "url": url or
            f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
            "title": title, "publish_date": "",
            "meta": {"region": "EU", "jurisdiction": "EU",
                     "doc_key": f"EU:CELEX:{celex}", "celex": celex,
                     "language": "en", "source_role": "EURLEX_PRIMARY",
                     "collector": "eu_fulltext_attach",
                     "official_domain": "eur-lex.europa.eu",
                     "fulltext_source": f"sources/eurlex-fulltext/{fp.name}",
                     "complements": f"eu_{celex}",
                     "full_chars": len(body)},
            "text": body[:MAKE_TEXT_CAP],
        }
        try:
            res = classify_record(rec)
            rec["relevant"] = res.classification in ("A1", "A2", "B")
            rec["relevance_score"] = 0.0
            rec["meta"]["acceptance_class"] = res.classification
            # 主题用**全文口径**（分类器短窗 1600 字符对长法规是 extractor gap）
            topics_full = extract_topics_full(rec)
            rec["meta"]["topic_ids"] = topics_full
            label = f"{res.classification} topics={topics_full}"
        except Exception as exc:  # noqa: BLE001
            label = f"classify_fail:{type(exc).__name__}"
        records.append(rec)
        print(f"  {celex:14s} {len(body):7d} chars → {label}")

    if args.dry_run:
        print(f"[dry-run] 将写 {len(records)} 条 → {out_fp}")
        return 0
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    with out_fp.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ 已写 {len(records)} 条至 {out_fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
