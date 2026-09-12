# -*- coding: utf-8 -*-
"""拉取单条 US 缺口候选（FR document），判定后落盘为 eol_US_gap_*.jsonl。

用法：
    py scripts/collect_us_gap_doc.py --doc 2019-03812
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.core.relevance import judge_portal_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
API = "https://www.federalregister.gov/api/v1/documents/{doc}.json"
FIELDS = ("title", "abstract", "publication_date", "document_number",
          "type", "agencies", "html_url", "excerpts", "citation")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="FR 文档号，如 2019-03812")
    args = ap.parse_args()

    url = f"{API.format(doc=args.doc)}"
    print(f"抓取 {url}")
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params={"fields[]": list(FIELDS)}, timeout=60)
        r.raise_for_status()
        d = r.json()

    title = d.get("title") or ""
    abstract = d.get("abstract") or ""
    date = d.get("publication_date") or ""
    agencies = ", ".join(a.get("raw_name", "") for a in (d.get("agencies") or []))
    excerpts = " ".join(d.get("excerpts") or [])
    text = (f"FR document {args.doc}\n{title}\nDate: {date}\n"
            f"Agencies: {agencies}\n\n{abstract}\n\n{excerpts}")

    v = judge_portal_policy(text, title)
    print(f"\n标题: {title}")
    print(f"机构: {agencies}")
    print(f"摘要: {abstract[:400]}")
    print(f"\n判定: relevant={v.relevant} score={v.score} "
          f"review={v.needs_human_review}")
    print(f"hits: {v.hits}")
    if v.rejected_by:
        print(f"rejected_by: {v.rejected_by}")
    if v.review_reason:
        print(f"review_reason: {v.review_reason}")

    rec = {
        "evidence_id": f"us_fr_{args.doc}",
        "region": "US",
        "channel": "connector",
        "source_id": "us_federal_register",
        "cluster_hint": None,
        "url": d.get("html_url"),
        "title": title,
        "publish_date": f"{date}T00:00:00+00:00" if date else None,
        "publish_date_hint": None,
        "relevant": v.relevant,
        "relevance_score": v.score,
        "needs_human_review": v.needs_human_review,
        "hits": v.hits[:5],
        "rejected_by": v.rejected_by,
        "meta": {"document_number": args.doc, "type": d.get("type"),
                 "agencies": agencies, "gap_collected": True},
        "text": text[:1200],
        "review_reason": v.review_reason,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT / f"eol_US_gap_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n→ {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
