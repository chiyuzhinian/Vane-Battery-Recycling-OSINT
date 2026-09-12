# -*- coding: utf-8 -*-
"""collect_eu_crossborder_sources.py —— Phase 4B-1 Step 6：Basel / OECD / Standards。

纪律：
    · Basel 技术导则 = guidance（draft ≠ binding）；COP 决定 = decision/binding
    · OECD：页面为 SPA → 不伪造内容；角色按端点实况判 PARTIAL（记录 blocked/spa）
    · Standards：只登记官方 metadata（EU OJ/JRC 引用 / CEN·ISO 元数据），
      全文不可得 → open_access_status=official_metadata_only，**不生成条款证据**

用法：
    py scripts/collect_eu_crossborder_sources.py            # 全部
    py scripts/collect_eu_crossborder_sources.py --skip-spa # 只跑可解析源
产物：outputs/crossborder_YYYYmmdd_HHMMSS.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.crossborder import (  # noqa: E402
    basel_instrument, basel_status, standard_from_official_reference,
)

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

BASEL_SOURCES = [
    ("basel_tech_guidelines_index",
     "https://www.basel.int/Implementation/TechnicalMatters/DevelopmentofTechnicalGuidelines/tabid/8025/Default.aspx",
     "Technical Guidelines (Development) — Basel Convention"),
    ("basel_publications",
     "https://www.basel.int/Implementation/Publications/TechnicalGuidelines/tabid/2362/Default.aspx",
     "Technical Guidelines Publications — Basel Convention"),
    ("basel_pdf_14_7",
     "https://www.basel.int/Portals/4/download.aspx?d=UNEP-CHW.14-7-Add.1.English.pdf",
     "UNEP/CHW.14/7/Add.1 — Technical guidelines (official PDF)"),
]
STANDARDS_SOURCES = [
    ("eu_harmonised_standards_ref",
     "https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en",
     "EU Harmonised Standards (official reference hub)",
     "EU_OFFICIAL_REFERENCE", "European Commission"),
    ("jrc_repository",
     "https://publications.jrc.ec.europa.eu/repository/",
     "JRC Publications Repository",
     "JRC_REFERENCE", "European Commission JRC"),
]


def _strip(text: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _finalize(rec: dict, itype: str | None = None, bforce: str | None = None) -> dict:
    if itype:
        rec["meta"]["instrument_type"] = itype
        rec["meta"]["binding_force"] = bforce or "non_binding"
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
    ap.add_argument("--skip-spa", action="store_true")
    args = ap.parse_args()

    records: list[dict] = []
    failures: list[dict] = []
    async with httpx.AsyncClient(headers=UA, timeout=60, follow_redirects=True) as client:
        # ---------------- Basel ----------------
        for eid_suffix, url, title in BASEL_SOURCES:
            try:
                r = await client.get(url)
            except Exception as exc:  # noqa: BLE001
                failures.append({"source": "basel", "url": url,
                                 "error": f"{type(exc).__name__}: {exc}"})
                print(f"✗ basel {eid_suffix}: {type(exc).__name__}")
                continue
            is_pdf = "pdf" in r.headers.get("content-type", "").lower() or url.endswith(".pdf")
            text = "" if is_pdf else _strip(r.text)
            status = basel_status(text + " " + title)
            itype, bforce = basel_instrument(status)
            rec = _finalize({
                "evidence_id": f"int_basel_{eid_suffix}",
                "channel": "connector", "source_id": "int_basel", "region": "GLOBAL",
                "url": url, "title": title, "publish_date": "",
                "meta": {"region": "GLOBAL", "collector": "collect_eu_crossborder_sources",
                         "organization": "Basel Convention", "doc_status": status,
                         "format": "pdf" if is_pdf else "html",
                         "fulltext_parseable": not is_pdf},
                "text": (title + "\n" + text[:6000])[:8000],
            }, itype=itype, bforce=bforce)
            records.append(rec)
            print(f"✓ basel {eid_suffix} ｜ {status} ｜ {itype} ｜ "
                  f"{rec['meta']['acceptance_class']}")

        # ---------------- Standards（官方引用 metadata） ----------------
        for eid_suffix, url, title, src_type, publisher in STANDARDS_SOURCES:
            try:
                r = await client.get(url)
            except Exception as exc:  # noqa: BLE001
                failures.append({"source": "standards", "url": url,
                                 "error": f"{type(exc).__name__}: {exc}"})
                print(f"✗ standards {eid_suffix}: {type(exc).__name__}")
                continue
            text = _strip(r.text)
            std = standard_from_official_reference(
                title=title, url=url, publisher=publisher,
                scope="EU harmonised standards / JRC references (metadata level)",
                source_type=src_type)
            rec = _finalize({
                "evidence_id": f"int_std_{eid_suffix}",
                "channel": "connector", "source_id": "int_standards_ref",
                "region": "EU", "url": url, "title": title, "publish_date": "",
                "meta": {"region": "EU", "collector": "collect_eu_crossborder_sources",
                         "organization": publisher, **std.as_meta()},
                "text": (title + "\n" + text[:4000])[:6000],
            })
            records.append(rec)
            print(f"✓ standards {eid_suffix} ｜ {std.open_access_status} ｜ "
                  f"{src_type} ｜ {rec['meta']['acceptance_class']}")

        # ---------------- OECD（SPA 探测记录，不伪造内容） ----------------
        if not args.skip_spa:
            try:
                r = await client.get("https://legalinstruments.oecd.org/en/instruments")
                spa = len(r.content) < 12000 and ("ng-version" in r.text
                                                  or "app-root" in r.text.lower())
                print(f"· OECD legalinstruments -> {r.status_code} "
                      f"len={len(r.content)} ｜ {'SPA（JS 渲染）' if spa else '可解析'}")
                if spa:
                    failures.append({"source": "oecd",
                                     "endpoint": "legalinstruments.oecd.org",
                                     "error": "SPA_JS_RENDERED（需浏览器通道/官方 API）"})
            except Exception as exc:  # noqa: BLE001
                failures.append({"source": "oecd", "error": f"{type(exc).__name__}: {exc}"})

    if not records:
        print("⚠️ 无记录")
        return 1 if failures else 0
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "outputs" / f"crossborder_{ts}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"\n→ 已写 {out.name}（{len(records)} 条；问题 {len(failures)}）")
    print(f"   分类：{dict(Counter(r['meta']['acceptance_class'] for r in records))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
