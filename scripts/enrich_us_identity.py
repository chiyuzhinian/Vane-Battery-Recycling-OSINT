# -*- coding: utf-8 -*-
"""enrich_us_identity.py —— Phase 4B-1 Step 2：US 联邦记录身份富化（FR 官方 API）。

目标：US 记录不再只有 title+URL —— 解析官方标识
    citation("84 FR 8006") / RIN / docket / cfr_references / type / effective_on

数据源（实测 200，无需 Key）：
    GET https://www.federalregister.gov/api/v1/documents/{document_number}.json

纪律：
    · 默认 --dry-run（抓取+统计，不写文件）；--apply 写 outputs/fr_identity_overlay.jsonl
    · 原始 evidence（outputs/*.jsonl）永不修改
    · 失败分类（HTTP_*/TIMEOUT/…）与 NO_RESULTS 分离，不得静默丢弃
    · 缓存：outputs/cache/fr_documents/{num}.json（避免重复抓取）

用法：
    py scripts/enrich_us_identity.py --limit 40                 # dry-run
    py scripts/enrich_us_identity.py --limit 40 --apply         # 写 overlay
    py scripts/enrich_us_identity.py --document 2019-03812      # 单文档抽查
    py scripts/enrich_us_identity.py --region US --source-role FEDERAL_REGISTER --only-missing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402

from app.policy.backfill import load_jsonl, load_records  # noqa: E402
from app.policy.config import load_aliases  # noqa: E402
from app.policy.identity_us import (  # noqa: E402
    identity_fields_from_fr, parse_fr_document,
)
from app.policy.source_access import classify_exception, classify_http_status  # noqa: E402

API = "https://www.federalregister.gov/api/v1/documents/{num}.json"
OVERLAY = ROOT / "outputs" / "fr_identity_overlay.jsonl"
CACHE = ROOT / "outputs" / "cache" / "fr_documents"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def doc_number_of(record: dict) -> str:
    meta = record.get("meta") or {}
    num = str(meta.get("document_number") or "").strip()
    if num:
        return num
    eid = str(record.get("evidence_id") or "")
    return eid[len("us_fr_"):] if eid.startswith("us_fr_") else ""


async def fetch_document(client: httpx.AsyncClient, num: str,
                         *, use_cache: bool = True) -> tuple[dict | None, str, str]:
    """→ (payload | None, status: cache|ok|failed, failure_type|note)"""
    cache_file = CACHE / f"{num}.json"
    if use_cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8")), "cache", ""
        except json.JSONDecodeError:
            pass
    try:
        r = await client.get(API.format(num=num),
                             headers={"User-Agent": UA,
                                      "Accept": "application/json"})
    except BaseException as e:  # noqa: BLE001
        return None, "failed", classify_exception(e)
    ftype = classify_http_status(r.status_code)
    if ftype != "NONE":
        return None, "failed", ftype
    try:
        payload = r.json()
    except ValueError:
        return None, "failed", "PARSER_FAILURE"
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload, "ok", ""


async def run(args: argparse.Namespace) -> int:
    overlay = load_jsonl(OVERLAY)
    known = {r["evidence_id"]: r for r in overlay.values()}

    # ---- 选记录 ----
    if args.document:
        targets = [{"evidence_id": f"us_fr_{args.document}",
                    "meta": {"document_number": args.document}}]
    else:
        from app.policy.source_universe import evidence_counts
        records = load_records(ROOT)
        alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
        from app.policy.backfill import filter_records
        targets = filter_records(
            records, region=args.region, source_role=args.source_role or "",
            only_missing=args.only_missing, limit=args.limit,
            alias_map=alias_map, known_source_ids=sorted(evidence_counts().keys()))
        if args.only_missing:
            targets = [t for t in targets
                       if t.get("evidence_id") not in known]

    print(f"目标 {len(targets)} 条（{'APPLY' if args.apply else 'DRY-RUN'}）")
    if not targets:
        print("（无可富化记录：检查 --region/--source-role/--only-missing/--limit）")
        return 0

    rows: list[dict] = []
    stats = {"ok": 0, "cache": 0, "failed": 0, "ambiguous": 0, "no_doc_number": 0}
    failures: list[dict] = []
    t0 = time.monotonic()
    sem = asyncio.Semaphore(max(1, args.concurrency))

    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=True) as client:
        async def one(rec: dict) -> None:
            eid = str(rec.get("evidence_id") or "")
            num = doc_number_of(rec)
            if not num:
                stats["no_doc_number"] += 1
                return
            async with sem:
                payload, status, note = await fetch_document(
                    client, num, use_cache=not args.no_cache)
                if args.delay and status == "ok":
                    await asyncio.sleep(args.delay)
            if payload is None:
                stats["failed"] += 1
                failures.append({"evidence_id": eid, "document_number": num,
                                 "failure_type": note})
                return
            fr = parse_fr_document(payload)
            stats[status] += 1
            if fr.ambiguous:
                stats["ambiguous"] += 1
            fields = identity_fields_from_fr(fr)
            fields.update({"issuer": fr.issuer,
                           "instrument_type": fr.instrument_type,
                           "binding_force": fr.binding_force,
                           "legal_status": fr.legal_status})
            rows.append({
                "evidence_id": eid,
                "document_number": num,
                "fr_identity": fields,
                "fr_ambiguous": fr.ambiguous,
                "fr_issues": fr.issues,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source_url": API.format(num=num),
            })

        await asyncio.gather(*(one(r) for r in targets))

    dt = time.monotonic() - t0
    print(f"完成：ok={stats['ok']} cache={stats['cache']} failed={stats['failed']} "
          f"ambiguous={stats['ambiguous']} 无文档号={stats['no_doc_number']} "
          f"耗时 {dt:.1f}s")
    for f in failures[:10]:
        print(f"  ✗ {f['document_number']} → {f['failure_type']}")
    if failures[10:]:
        print(f"  … 另有 {len(failures) - 10} 条失败")

    if not args.apply:
        print("\n（dry-run —— 加 --apply 写 overlay；原始 evidence 不会被修改）")
        if rows:
            sample = rows[0]["fr_identity"]
            print("样本：" + json.dumps(
                {k: sample.get(k) for k in ("canonical_id", "official_identifier",
                                            "issuer", "instrument_type",
                                            "legal_status")},
                ensure_ascii=False))
        return 0

    merged = dict(known)
    for r in rows:
        merged[r["evidence_id"]] = r
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    with OVERLAY.open("w", encoding="utf-8") as f:
        for r in merged.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ 已写 {OVERLAY.name}（{len(merged)} 行；本次 +{len(rows)}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--region", default="US")
    ap.add_argument("--source-role", default="")
    ap.add_argument("--only-missing", action="store_true",
                    help="跳过已在 overlay 中的记录")
    ap.add_argument("--document", default="", help="单个 FR 文档号（抽查）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
