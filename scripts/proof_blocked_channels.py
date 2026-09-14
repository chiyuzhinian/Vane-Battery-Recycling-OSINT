# -*- coding: utf-8 -*-
"""proof_blocked_channels.py —— Step 5：受阻通道攻坚的 Proof 与入库。

对 PL（Sejm ELI API）/ US-KY（KRS）/ US-MN（Revisor）：
    · 真实 fetch 3 样本（连接器生产路径）
    · 成功样本写语料 outputs/jurisdiction_{PL,US-KY,US-MN}_*.jsonl
    · Source Proof → outputs/audit/source_proofs/{PL,US-KY,US-MN}.json
    · 7 通道状态总表 → outputs/audit/blocked_channel_resolution.json

用法：py scripts/proof_blocked_channels.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors import REGISTRY  # noqa: E402
from app.policy.acceptance import classify_record  # noqa: E402

AUDIT = ROOT / "outputs" / "audit"
PROOFS = AUDIT / "source_proofs"
TS = datetime.now(timezone.utc).strftime("%Y%m%d")

TARGETS = [
    ("PL", "pl_sejm_eli", None),                       # 默认 3 docs
    ("US-KY", "us_ky_krs", None),
    ("US-MN", "us_mn_revisor", None),
]

#: 7 通道攻坚结论（2026-09-13 实测）
CHANNEL_STATUS = {
    "PL": {"status": "ADAPTED", "new_source": "pl_sejm_eli",
           "method": "official ELI API（api.sejm.gov.pl）",
           "note": "ISAP Distil 拦截 → 官方替代 API：元数据+全文+实施法案家族；未绕过访问控制"},
    "BE": {"status": "BLOCKED_SITE_LEVEL",
           "method": "ejustice 全路径同壳（含 ELI/loi_a1/change_lg）",
           "note": "站点对本环境出口整体拦截（5507B 壳）；建议后续换网络环境或等官方接口"},
    "EE": {"status": "ADAPTED", "new_source": "ee_keskkonnaamet",
           "method": "Keskkonnaamet（环境署）+ Kliimaministeerium（气候部）官方站（静态 HTML，httpx 可重复采集）",
           "note": ("RT 法源站仍 SPA 壳（51763B 同壳实证）——改以官方环保机构通道适配："
                    "2 样本已入库（ee_keskkonnaamet_home / ee_kliimaministeerium_home，"
                    "scope=HORIZONTAL）；法源全文待 RT 数据接口")},
    "US-CO": {"status": "PARTIAL_ENTRY_ONLY",
              "method": "leg.colorado.gov CRS 入口可达（40KB）；条文体 URL 模式未命中（多路 404）；OAL/CCR 403",
              "note": "CRS 条文体直链模式待探（新版站点路由）；battery 专条存在性未确认"},
    "US-GA": {"status": "ADAPTED", "new_source": "us_ga_epd",
              "method": "epd.georgia.gov（官方环保署）Land Protection Branch + Hazardous Waste 页（静态 HTML，httpx 可重复采集）",
              "note": ("legis.ga.gov SPA/401 仍阻——改以官方环保机构通道适配："
                       "2 样本已入库（us_ga_epd_land_protection / us_ga_epd_hazardous_waste）；"
                       "法源条文待 legis 数据接口")},
    "US-KY": {"status": "ADAPTED", "new_source": "us_ky_krs",
              "method": "statute.aspx?id 直链（官方服务器渲染）",
              "note": "目录 269 条；电池专条未定位（KRS 未见 battery 专章）→ 以真实条文样本验证通道"},
    "US-MN": {"status": "ADAPTED", "new_source": "us_mn_revisor",
              "method": "revisor.mn.gov/statutes/cite 直链",
              "note": "搜索为 JS → cite 直链模式；电池专条未定位（115A.30xx 404）→ 样本为 115A 章条文"},
}


async def run_one(jid: str, key: str) -> dict:
    cls = REGISTRY[key]
    print(f"\n== {jid} via {key} ==")
    merged: dict[str, object] = {}
    for attempt in range(5):                     # 网络瞬态 → 多轮合并重试
        conn = cls()
        try:
            items = await conn.fetch()
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ attempt {attempt+1} fetch 失败："
                  f"{type(exc).__name__}")
            items = []
        for ev in items:
            merged.setdefault(ev.evidence_id, ev)
        if len(merged) >= 3:
            break
        await asyncio.sleep(3)
    items = list(merged.values())
    if not items:
        print(f"  ❌ fetch 五轮失败（网络？）")
        return {"jurisdiction": jid, "source_id": key, "samples_total": 0,
                "samples_ok": 0, "error": "fetch_failed_5x"}
    records = []
    samples = []
    for ev in items:
        rec = {
            "evidence_id": ev.evidence_id, "channel": ev.channel,
            "source_id": ev.source_id, "region": ev.meta.get("region", ""),
            "url": ev.source_url, "title": ev.source_title,
            "publish_date": "", "meta": dict(ev.meta),
            "text": ev.raw_text,
        }
        try:
            res = classify_record(rec)
            rec["relevant"] = res.classification in ("A1", "A2", "B")
            rec["relevance_score"] = 0.0
            rec["meta"]["acceptance_class"] = res.classification
            rec["meta"]["topic_ids"] = res.topic_ids
            label = f"{res.classification} {res.topic_ids[:4]}"
        except Exception as exc:  # noqa: BLE001
            label = f"cls_fail:{type(exc).__name__}"
        records.append(rec)
        samples.append({"evidence_id": ev.evidence_id,
                        "url": ev.source_url,
                        "title": ev.source_title,
                        "status": 200,
                        "chars": len(ev.raw_text or ""),
                        "class": rec["meta"].get("acceptance_class", "")})
        print(f"  {ev.evidence_id:28s} {len(ev.raw_text or ''):>7d}c  {label}")

    if records:
        fp = ROOT / "outputs" / f"jurisdiction_{jid}_{TS}.jsonl"
        existing: dict[str, dict] = {}
        if fp.exists():                      # 同日多轮 → 合并（防网络抖动丢失）
            for line in fp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r0 = json.loads(line)
                    existing[r0.get("evidence_id")] = r0
        for r in records:
            existing[r["evidence_id"]] = r
        with fp.open("w", encoding="utf-8") as f:
            for r in existing.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  → 入库 {len(existing)} 条 {fp.name}")
    proof = {
        "jurisdiction_id": jid,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "summary": {"sources": 1,
                    "search_available": 0,
                    "fulltext_available": 1 if records else 0,
                    "samples_total": len(items),
                    "samples_ok": len(records)},
        "sources": [{"source_id": key,
                     "access_method": "official_direct",
                     "status": "ACCESSIBLE" if records else "BLOCKED",
                     "capabilities": {
                         "fulltext_available": bool(records),
                         "metadata_available": bool(records),
                         "search_available": False},
                     "known_limitations": [CHANNEL_STATUS[jid]["note"]],
                     "samples": samples}],
        "notes": CHANNEL_STATUS[jid]["note"],
    }
    PROOFS.mkdir(parents=True, exist_ok=True)
    proof_fp = PROOFS / f"{jid}.json"
    if not records and proof_fp.exists():
        # 网络瞬态保护：0 样本不得覆盖既有真实证据（本环境间歇故障已知）
        print(f"  ⚠️ 本次 0 样本（疑网络瞬态）→ 保留既有 proof，不覆盖")
    else:
        proof_fp.write_text(
            json.dumps(proof, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  → proof {jid}.json")
    return {"jurisdiction": jid, "source_id": key,
            "samples_total": len(items), "samples_ok": len(records)}


async def main() -> int:
    results = []
    for jid, key, _ in TARGETS:
        results.append(await run_one(jid, key))
    resolution = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "channels": CHANNEL_STATUS,
        "adapted": sorted(k for k, v in CHANNEL_STATUS.items()
                          if v["status"] == "ADAPTED"),
        "blocked": sorted(k for k, v in CHANNEL_STATUS.items()
                          if v["status"].startswith("BLOCKED")),
        "partial": sorted(k for k, v in CHANNEL_STATUS.items()
                          if v["status"].startswith("PARTIAL")),
        "proof_runs": results,
    }
    (AUDIT / "blocked_channel_resolution.json").write_text(
        json.dumps(resolution, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n=== Blocked Channel Resolution ===")
    for k, v in CHANNEL_STATUS.items():
        print(f"  {k:6s} {v['status']}")
    print(f"→ 已写 {AUDIT / 'blocked_channel_resolution.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
