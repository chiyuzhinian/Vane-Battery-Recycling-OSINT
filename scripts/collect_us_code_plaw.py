# -*- coding: utf-8 -*-
"""collect_us_code_plaw.py —— Phase 4B-1 Step 4：U.S. Code / Public Law 官方采集。

用法：
    py scripts/collect_us_code_plaw.py                      # 默认目标
    py scripts/collect_us_code_plaw.py --usc 42:82 --usc 49:51
    py scripts/collect_us_code_plaw.py --plaw 117:58 --plaw 117:169
    py scripts/collect_us_code_plaw.py --year 2023

产物：outputs/uscplaw_YYYYmmdd_HHMMSS.jsonl + outputs/cache/govinfo/*
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
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors.govinfo import (  # noqa: E402
    GovInfoPublicLawConnector, GovInfoUsCodeConnector,
)
from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.us_code import (  # noqa: E402
    parse_public_law, parse_us_code_chapter, pl_relations, relevance_excerpts,
    strip_html,
)

CACHE = ROOT / "outputs" / "cache" / "govinfo"
DEFAULT_USC = [(42, "82"), (42, "103")]                 # RCRA 固废 / CERCLA
DEFAULT_PLAW = [(117, 58), (117, 169)]                   # IIJA / IRA


def _prioritized_excerpts(flat: str, *, limit: int = 8) -> str:
    """相关条款摘录 —— **按主题命中优先**排序，保证判定窗口（前 1600 字符）有效。

    背景（实测 2026-09-12）：IRA（PL 117-169）全文能命中 T04/T05/T07/T09/T11/T14，
    但按文档顺序取的头部摘录（电池储能税收条款）不命中任何主题词
    → 被误判 D。摘录必须按"对判定有用的程度"排序，而不是按出现位置。
    """
    from app.policy.acceptance import scan_topics
    chunks = [c for c in relevance_excerpts(flat, limit=40).split("\n…\n") if c]
    scored = []
    for i, c in enumerate(chunks):
        topics, _ = scan_topics(c)
        scored.append((len(topics), -i, c))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    picked = [c for s, _, c in scored[:limit]]
    if not picked:
        picked = [relevance_excerpts(flat, limit=limit)]
    return "\n…\n".join(picked)


def _classify(rec: dict) -> dict:
    res = classify_record(rec)
    rec["relevant"] = res.relevant
    rec["relevance_score"] = round(res.confidence, 3)
    rec["needs_human_review"] = res.requires_human_review
    rec["hits"] = [f"acceptance:{res.classification}"] + list(res.reason_codes)[:4]
    rec["meta"]["acceptance_class"] = res.classification
    rec["meta"]["topic_ids"] = res.topic_ids
    return rec


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usc", action="append", default=[], help="title:chapter")
    ap.add_argument("--plaw", action="append", default=[], help="congress:number")
    ap.add_argument("--year", default="2023", help="USC 版本年（默认 2023）")
    args = ap.parse_args()

    usc_targets = ([tuple(x.split(":")) for x in args.usc] if args.usc
                   else DEFAULT_USC)
    plaw_targets = ([tuple(int(v) for v in x.split(":")) for x in args.plaw]
                    if args.plaw else DEFAULT_PLAW)

    usc_conn, plaw_conn = GovInfoUsCodeConnector(), GovInfoPublicLawConnector()
    CACHE.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    failures: list[dict] = []

    # ---------------- USC ----------------
    for title_s, chap in usc_targets:
        title = int(title_s)
        cache_file = CACHE / f"USCODE-{args.year}-title{title}-chap{chap}.htm"
        try:
            if cache_file.exists():
                html = cache_file.read_text(encoding="utf-8", errors="replace")
                src = "cache"
            else:
                html = await usc_conn.fetch_chapter(args.year, title, chap)
                cache_file.write_text(html, encoding="utf-8")
                src = "network"
            u = parse_us_code_chapter(html, title=title, chapter=chap,
                                      year=args.year)
        except Exception as exc:  # noqa: BLE001
            failures.append({"kind": "USC", "target": f"{title}:{chap}",
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"✗ USC {title} chap{chap}: {type(exc).__name__}: {exc}")
            continue
        rec = _classify({
            "evidence_id": f"us_usc_{title}_{chap}",
            "channel": "connector", "source_id": "us_usc", "region": "US",
            "url": f"https://www.govinfo.gov/content/pkg/USCODE-{args.year}-title{title}/html/"
                   f"USCODE-{args.year}-title{title}-chap{chap}.htm",
            "title": u.canonical_title,
            "publish_date": args.year,
            "relevance_score": 0.0, "needs_human_review": False,
            "hits": [], "rejected_by": "",
            "meta": {"region": "US", "collector": "collect_us_code_plaw",
                     "usc_title": title, "usc_chapter": str(chap),
                     "usc_key": u.key, "year": args.year,
                     "section_count": len(u.sections),
                     "sections_preview": u.sections[:25],
                     "fetch_source": src},
            "text": (u.canonical_title + "\n"
                     + _prioritized_excerpts(strip_html(html)) + "\n"
                     + u.text_head)[:12000],
        })
        records.append(rec)
        print(f"✓ {u.canonical_title[:70]} ｜ {len(u.sections)} 条 ｜ "
              f"{rec['meta']['acceptance_class']}（{src}）")

    # ---------------- Public Law ----------------
    for congress, number in plaw_targets:
        cache_file = CACHE / f"PLAW-{congress}publ{number}.htm"
        try:
            if cache_file.exists():
                html = cache_file.read_text(encoding="utf-8", errors="replace")
                src = "cache"
            else:
                html = await plaw_conn.fetch_public_law(congress, number)
                cache_file.write_text(html, encoding="utf-8")
                src = "network"
            pl = parse_public_law(html)
        except Exception as exc:  # noqa: BLE001
            failures.append({"kind": "PLAW", "target": f"{congress}:{number}",
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"✗ PLAW {congress}-{number}: {type(exc).__name__}: {exc}")
            continue
        rels = pl_relations(pl)
        rec = _classify({
            "evidence_id": f"us_plaw_{congress}_{number}",
            "channel": "connector", "source_id": "us_plaw", "region": "US",
            "url": f"https://www.govinfo.gov/content/pkg/PLAW-{congress}publ{number}/html/"
                   f"PLAW-{congress}publ{number}.htm",
            "title": f"Public Law {congress}-{number}"
                     + (f" — {pl.heading[:120]}" if pl.heading else ""),
            "publish_date": "",
            "relevance_score": 0.0, "needs_human_review": False,
            "hits": [], "rejected_by": "",
            "meta": {"region": "US", "collector": "collect_us_code_plaw",
                     "congress": congress, "law_number": number, "pl_key": pl.key,
                     "stat_citation": pl.stat_citation,
                     "usc_mentions": pl.usc_mentions[:30],
                     "cfr_mentions": pl.cfr_mentions[:20],
                     "relations": rels[:40],
                     "fetch_source": src},
            # ⚠️ 大法（如 IIJA 3.8MB）的电池/回收条款在深处 —— 摘录必须放在
            #    text 前部（acceptance 只扫描前 1600 字符）
            "text": (f"{pl.key} {pl.stat_citation} " + pl.heading + "\n"
                     + _prioritized_excerpts(strip_html(html)) + "\n"
                     + pl.text_head)[:12000],
        })
        records.append(rec)
        print(f"✓ {pl.key} {pl.stat_citation} ｜ USC×{len(pl.usc_mentions)} "
              f"CFR×{len(pl.cfr_mentions)} REL×{len(rels)} ｜ "
              f"{rec['meta']['acceptance_class']}（{src}）")

    if not records:
        print("⚠️ 无记录")
        return 1 if failures else 0
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "outputs" / f"uscplaw_{ts}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n→ 已写 {out.name}（{len(records)} 条；失败 {len(failures)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
