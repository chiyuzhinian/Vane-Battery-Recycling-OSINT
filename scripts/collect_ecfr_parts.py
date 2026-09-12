# -*- coding: utf-8 -*-
"""collect_ecfr_parts.py —— Phase 4B-1 Step 3：采集 eCFR 目标 Part（官方 XML）。

流程：fetch XML（缓存）→ 解析（app.policy.cfr）→ 分类（acceptance v2）→ 写 jsonl

用法：
    py scripts/collect_ecfr_parts.py                  # 默认 6 个目标 part
    py scripts/collect_ecfr_parts.py --part 49:173 --part 40:273
    py scripts/collect_ecfr_parts.py --as-of 2026-09-01

产物：outputs/ecfr_YYYYmmdd_HHMMSS.jsonl（原始证据不可变，可直接进判定链）
缓存：outputs/cache/ecfr/title-{n}-part-{p}.xml
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

from app.connectors.ecfr import DEFAULT_PARTS, EcfrConnector  # noqa: E402
from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.cfr import parse_part_document  # noqa: E402

CACHE = ROOT / "outputs" / "cache" / "ecfr"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", action="append", default=[],
                    help="title:part 形式，可多次；默认 6 个目标")
    ap.add_argument("--as-of", default="", help="eCFR 版本日期 YYYY-MM-DD（默认取 title 最新发布日期）")
    ap.add_argument("--from-links", default="",
                    help="按 FR→CFR 链接审计结果选 part（outputs/audit/fr_cfr_links.json）")
    ap.add_argument("--top", type=int, default=12, help="--from-links 时取前 N 个 part")
    args = ap.parse_args()

    if args.from_links:
        import json as _json
        data = _json.loads(Path(args.from_links).read_text(encoding="utf-8"))
        targets = []
        for key in (data.get("unique_parts") or [])[:args.top]:
            try:
                _, t, p = key.split(":", 2)
                targets.append((t, p))
            except ValueError:
                continue
        print(f"按 FR 引用选取 {len(targets)} 个 part（--top {args.top}）")
    else:
        targets = ([tuple(p.split(":")) for p in args.part]
                   if args.part else [(str(t), p) for t, p in DEFAULT_PARTS])
    as_of = args.as_of
    conn = EcfrConnector()
    CACHE.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    failures: list[dict] = []
    for title, part in targets:
        title_i = int(title)
        cache_file = CACHE / f"title-{title_i}-part-{part}.xml"
        xml_text = ""
        source = "cache"
        # ⚠️ 实测：as_of 必须 ≤ 该 title 最新发布日期，否则 404
        currentness = as_of
        if not currentness:
            try:
                currentness = await conn.latest_issue_date(title_i)
            except Exception:  # noqa: BLE001 — 取不到就退化为空（不阻塞采集）
                currentness = ""
        if cache_file.exists():
            xml_text = cache_file.read_text(encoding="utf-8")
        else:
            try:
                xml_text = await conn.fetch_part_xml(title_i, str(part),
                                                     as_of=currentness or None)
                cache_file.write_text(xml_text, encoding="utf-8")
                source = "network"
            except Exception as exc:  # noqa: BLE001
                failures.append({"title": title_i, "part": part,
                                 "error": f"{type(exc).__name__}: {exc}"})
                print(f"✗ {title_i} CFR {part}: {type(exc).__name__}: {exc}")
                continue
        try:
            cfr = parse_part_document(xml_text, title=title_i, part=str(part),
                                      currentness=currentness)
        except ValueError as exc:
            failures.append({"title": title_i, "part": part,
                             "error": f"PARSER_FAILURE: {exc}"})
            print(f"✗ {title_i} CFR {part}: PARSER_FAILURE {exc}")
            continue

        section_heads = "; ".join(
            f"§{s.number} {s.heading[:80]}" for s in cfr.sections[:12] if s.heading)
        text = "\n".join(filter(None, [
            cfr.canonical_title, f"Authority: {cfr.authority}",
            section_heads,
        ]))[:8000]
        rec = {
            "evidence_id": f"us_ecfr_{title_i}_{part}",
            "channel": "connector",
            "source_id": "us_ecfr",
            "region": "US",
            "url": f"https://www.ecfr.gov/current/title-{title_i}/part-{part}",
            "title": cfr.canonical_title,
            "publish_date": as_of or "",
            "relevance_score": 0.0,
            "needs_human_review": False,
            "hits": [],
            "rejected_by": "",
            "meta": {
                "region": "US",
                "collector": "collect_ecfr_parts",
                "cfr_title": title_i,
                "cfr_part": str(part),
                "cfr_key": cfr.key,
                "section_count": len(cfr.sections),
                "sections_preview": [s.number for s in cfr.sections[:20]],
                "authority": cfr.authority[:600],
                "usc_citations": cfr.usc_citations[:20],
                "public_laws": cfr.public_laws[:20],
                "fr_citations": cfr.fr_citations[:20],
                "currentness": currentness,
                "fetch_source": source,
            },
            "text": text,
        }
        res = classify_record(rec)
        rec["relevant"] = res.relevant
        rec["relevance_score"] = round(res.confidence, 3)
        rec["needs_human_review"] = res.requires_human_review
        rec["hits"] = [f"acceptance:{res.classification}"] + list(res.reason_codes)[:4]
        rec["meta"]["acceptance_class"] = res.classification
        rec["meta"]["topic_ids"] = res.topic_ids
        records.append(rec)
        print(f"✓ {cfr.canonical_title[:80]} ｜ {len(cfr.sections)} 段 ｜ "
              f"{res.classification} ｜ USC×{len(cfr.usc_citations)} PL×{len(cfr.public_laws)} "
              f"（{source}）")

    if not records:
        print("⚠️ 无记录（失败见上）")
        return 1 if failures else 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "outputs" / f"ecfr_{ts}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n→ 已写 {out.name}（{len(records)} 条；失败 {len(failures)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
