# -*- coding: utf-8 -*-
"""collect_us_trade_sources.py —— Phase 4B-1 Step 5：CBP CROSS + BIS（FR 机构通道）。

用法：
    py scripts/collect_us_trade_sources.py                 # 默认词表
    py scripts/collect_us_trade_sources.py --term "black mass" --term "battery waste"
    py scripts/collect_us_trade_sources.py --skip-fr       # 只跑 CROSS

产物：outputs/trade_YYYYmmdd_HHMMSS.jsonl + outputs/cache/cross/*.json
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

from app.connectors.cbp_cross import CrossConnector  # noqa: E402
from app.connectors.us_federal import FederalRegisterConnector  # noqa: E402
from app.policy.acceptance import classify_record  # noqa: E402

CACHE = ROOT / "outputs" / "cache" / "cross"
CROSS_TERMS = ["black mass", "lithium battery", "battery waste", "battery recycling"]
BIS_AGENCIES = ["industry-and-security-bureau"]
CBP_AGENCIES = ["u-s-customs-and-border-protection"]
FR_TERMS = ["black mass", "lithium battery", "battery recycling",
            "critical minerals export"]


def _finalize(rec: dict, *, instrument_hint: tuple[str, str] | None = None) -> dict:
    if instrument_hint:
        rec["meta"]["instrument_type"] = instrument_hint[0]
        rec["meta"]["binding_force"] = instrument_hint[1]
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
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--skip-fr", action="store_true")
    args = ap.parse_args()
    terms = args.term or CROSS_TERMS

    records: list[dict] = []
    failures: list[dict] = []
    cross = CrossConnector()
    CACHE.mkdir(parents=True, exist_ok=True)

    # ---------------- CROSS 裁定 ----------------
    for term in terms:
        try:
            evidences = await cross.search(term, limit=args.limit)
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": "cbp_cross", "term": term,
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"✗ CROSS '{term}': {type(exc).__name__}: {exc}")
            continue
        print(f"✓ CROSS '{term}': {len(evidences)} 条（已主题过滤）")
        for ev in evidences:
            rec = _finalize({
                "evidence_id": ev.evidence_id, "channel": ev.channel,
                "source_id": ev.source_id, "region": "US",
                "url": ev.source_url, "title": ev.source_title,
                "publish_date": ev.publish_date.date().isoformat() if ev.publish_date else "",
                "meta": dict(ev.meta), "text": ev.raw_text,
            })
            records.append(rec)

    # ---------------- FR：CBP / BIS 机构通道 ----------------
    if not args.skip_fr:
        fr = FederalRegisterConnector()
        for agency, label in ((CBP_AGENCIES, "CBP"), (BIS_AGENCIES, "BIS")):
            for term in FR_TERMS:
                try:
                    evidences = await fr.fetch(agencies=agency, terms=[term],
                                               max_pages=1, per_page=20)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"source": "us_federal_register",
                                     "agency": agency[0], "term": term,
                                     "error": f"{type(exc).__name__}: {exc}"})
                    print(f"✗ FR {label} '{term}': {type(exc).__name__}: {exc}")
                    continue
                if not evidences:
                    continue
                print(f"✓ FR {label} '{term}': {len(evidences)} 条")
                for ev in evidences:
                    ftype = str((ev.meta or {}).get("type") or "")
                    hint = None
                    if ftype == "Rule":
                        hint = ("administrative_rule", "binding")
                    elif ftype == "Proposed Rule":
                        hint = ("proposal", "proposal")
                    rec = _finalize({
                        "evidence_id": ev.evidence_id, "channel": ev.channel,
                        "source_id": ev.source_id, "region": "US",
                        "url": ev.source_url, "title": ev.source_title,
                        "publish_date": ev.publish_date.date().isoformat()
                        if ev.publish_date else "",
                        "meta": dict(ev.meta), "text": ev.raw_text,
                    }, instrument_hint=hint)
                    records.append(rec)

    # 去重
    uniq: dict[str, dict] = {}
    for r in records:
        uniq.setdefault(r["evidence_id"], r)
    records = list(uniq.values())
    if not records:
        print("⚠️ 无记录")
        return 1 if failures else 0
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "outputs" / f"trade_{ts}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    dist = Counter(r["meta"].get("acceptance_class") for r in records)
    print(f"\n→ 已写 {out.name}（{len(records)} 条；失败 {len(failures)}）")
    print(f"   分类分布: {dict(dist)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
