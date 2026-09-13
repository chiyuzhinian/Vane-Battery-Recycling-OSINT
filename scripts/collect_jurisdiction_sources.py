# -*- coding: utf-8 -*-
"""collect_jurisdiction_sources.py —— Phase 4B-2A Step 5：pilot 连接器采集执行器。

纪律：
    · 只采集 Source Proof 已验证的直链（DEFAULT_DOCS），不猜 URL
    · 每条记录跑 acceptance（分类 + 主题）后落盘；分类结果如实记录（含 D）
    · 区域口径：EU 成员国 → region=EU（进 EU_MEMBER_STATES scope）；
      US 州 → region=US；jurisdiction 字段用于 jurisdiction 级切片

用法：
    py scripts/collect_jurisdiction_sources.py --jurisdictions SE,PL,FI
    py scripts/collect_jurisdiction_sources.py --all
产物：outputs/jurisdiction_{jid_lower}_{ts}.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402

FAILURES_LOG = ROOT / "outputs" / "audit" / "jurisdiction_collection_failures.json"

#: pilot 连接器注册表（逐步扩充：Step 5a=EU 三国；5b=US 两州；…）
CONNECTOR_MAP: dict[str, tuple[str, str]] = {
    # jid → (region, module.ClassName)
    "SE": ("EU", "app.connectors.sfst_se:SfstSeConnector"),
    "PL": ("EU", "app.connectors.isap_pl:IsapPlConnector"),
    "FI": ("EU", "app.connectors.finlex_fi:FinlexFiConnector"),
    "US-CA": ("US", "app.connectors.leginfo_ca:LeginfoCaConnector"),
    "US-WA": ("US", "app.connectors.rcw_wa:RcwWaConnector"),
}


def _load_connector(path: str):
    mod_name, cls_name = path.split(":")
    import importlib
    return getattr(importlib.import_module(mod_name), cls_name)


def to_record(ev, jid: str, region: str) -> dict:
    """RawEvidence → 语料记录（含 acceptance 分类）。"""
    rec = {
        "evidence_id": ev.evidence_id,
        "channel": ev.channel,
        "source_id": ev.source_id,
        "region": region,
        "url": ev.source_url,
        "title": ev.source_title or "",
        "publish_date": ev.publish_date.date().isoformat() if ev.publish_date else "",
        "meta": {**dict(ev.meta or {}), "region": region, "jurisdiction": jid,
                 "collector": "collect_jurisdiction_sources"},
        "text": ev.raw_text,
    }
    res = classify_record(rec)
    rec["relevant"] = res.relevant
    rec["relevance_score"] = round(res.confidence, 3)
    rec["needs_human_review"] = res.requires_human_review
    rec["hits"] = [f"acceptance:{res.classification}"] + list(res.reason_codes)[:4]
    rec["meta"]["acceptance_class"] = res.classification
    rec["meta"]["topic_ids"] = res.topic_ids
    return rec


async def collect(jid: str, *, max_attempts: int = 2) -> dict:
    region, cls_path = CONNECTOR_MAP[jid]
    cls = _load_connector(cls_path)
    connector = cls()
    expected = len(getattr(cls, "DEFAULT_DOCS", {}) or {})
    merged: dict[str, object] = {}
    failures: list[dict] = []
    attempts_used = 0
    try:
        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt
            evidences = await connector.fetch()
            for ev in evidences:
                merged[ev.evidence_id] = ev
            failures = list(getattr(connector, "last_errors", []))
            if len(merged) >= expected or not failures:
                break
            await asyncio.sleep(3)          # 瞬态网络抖动 → 整轮重试
    finally:
        await connector.aclose()
    evidences = list(merged.values())
    # 失败计数修正：后续尝试已成功的 doc 不再计失败
    ok_docs = {str((ev.meta or {}).get("doc_key", "")) for ev in evidences}
    failures = [f for f in failures if f.get("doc") not in ok_docs]
    records = [to_record(ev, jid, region) for ev in evidences]
    # 防御层：挑战页/JS 壳文本一律不得入语料（不得伪造正文）
    from app.connectors.leg_utils import detect_challenge  # noqa: PLC0415
    clean: list[dict] = []
    for r in records:
        marker = detect_challenge(r["text"])
        if marker:
            failures.append({"doc": r["evidence_id"], "error": f"challenge_page:{marker}"})
        else:
            clean.append(r)
    records = clean
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fp = ROOT / "outputs" / f"jurisdiction_{jid.lower()}_{ts}.jsonl"
    if records:
        with fp.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 失败持久化：SOURCE_FAILURE ≠ 0 结果（不得只留在控制台）
    if failures:
        _log_failures(jid, failures)
    by_class = collections.Counter(r["meta"]["acceptance_class"] for r in records)
    file_note = fp.name if records else "（无记录，未写文件）"
    print(f"  [{jid}] {len(records)} 条 → {file_note} ｜ 分类 {dict(by_class)} "
          f"｜ 失败 {len(failures)}")
    for r in records:
        print(f"       {r['meta']['acceptance_class']:>2s} ｜ "
              f"{r['title'][:70]} ｜ {len(r['text'])} 字符")
    for fl in failures:
        print(f"       ⚠ {fl}")
    return {"jurisdiction": jid, "records": len(records),
            "file": fp.name if records else "（无记录，未写文件）",
            "by_class": dict(by_class), "failed": len(failures),
            "attempts": attempts_used,
            "errors": failures}


def _log_failures(jid: str, failures: list[dict]) -> None:
    """失败产物累积记录（按 jurisdiction+doc+日期 去重）。"""
    FAILURES_LOG.parent.mkdir(parents=True, exist_ok=True)
    data = {"entries": []}
    if FAILURES_LOG.exists():
        try:
            data = json.loads(FAILURES_LOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"entries": []}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen = {(e["jurisdiction"], e["doc"], e["date"]) for e in data["entries"]}
    for fl in failures:
        key = (jid, fl.get("doc", ""), today)
        if key in seen:
            continue
        data["entries"].append({"jurisdiction": jid, "doc": fl.get("doc", ""),
                                "error": fl.get("error", ""), "date": today})
    FAILURES_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdictions", default="",
                    help="逗号分隔（如 SE,PL,FI）；缺省=全部已注册")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    jids = ([j for j in args.jurisdictions.split(",") if j] if args.jurisdictions
            else sorted(CONNECTOR_MAP))
    unknown = [j for j in jids if j not in CONNECTOR_MAP]
    if unknown:
        raise SystemExit(f"❌ 未注册的 pilot 连接器：{unknown}（已注册：{sorted(CONNECTOR_MAP)}）")
    print(f"=== 管辖地采集：{', '.join(jids)} ===")
    summary = []
    for jid in jids:
        summary.append(await collect(jid))
    print("\n汇总：", json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
