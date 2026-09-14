# -*- coding: utf-8 -*-
"""backfill_non_eu_gaps.py —— 非 EU 缺口回填（Phase 4B-2B1 §5）。

1) us_fr 3 条：Federal Register API → raw_text 全文 → 原地合并
2) browser_france 1 条：检查 meta.full_text_path / 抓数据集页
3) 预览 Basel 8 条处理（PDF → 单独脚本）
幂等；日志追加到 content_backfill_log.json。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

OUTPUTS = ROOT / "outputs"
LOG = OUTPUTS / "audit" / "content_backfill_log.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"}
FR_DOCS = {
    "us_fr_2026-15813": "2026-15813",
    "us_fr_2026-15814": "2026-15814",
    "us_fr_2026-15815": "2026-15815",
}
TEXT_CAP = 400_000


def fetch_fr_raw(doc_no: str) -> str:
    api = (f"https://www.federalregister.gov/api/v1/documents/{doc_no}"
           ".json?fields[]=raw_text_url&fields[]=full_text_xml_url")
    r = httpx.get(api, timeout=30, follow_redirects=True, headers=UA)
    r.raise_for_status()
    meta = r.json()
    raw_url = meta.get("raw_text_url") or ""
    if raw_url:
        rr = httpx.get(raw_url, timeout=60, follow_redirects=True, headers=UA)
        if rr.status_code == 200 and len(rr.text) > 500:
            return rr.text
    xml_url = meta.get("full_text_xml_url") or ""
    if xml_url:
        rx = httpx.get(xml_url, timeout=60, follow_redirects=True, headers=UA)
        if rx.status_code == 200:
            import re
            txt = re.sub(r"<[^>]+>", " ", rx.text)
            return re.sub(r"\s+", " ", txt)
    return ""


def main() -> int:
    updated = []
    for eid, doc_no in FR_DOCS.items():
        try:
            body = fetch_fr_raw(doc_no)
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ {eid}: {type(exc).__name__} {str(exc)[:60]}")
            continue
        if len(body) < 600:
            print(f"  ⚠️ {eid}: 正文过短（{len(body)}）")
            continue
        # 原地更新
        for fp in sorted(OUTPUTS.glob("*.jsonl")):
            if fp.name.startswith(("_", "review")):
                continue
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            changed = False
            out = []
            for line in lines:
                if not line.strip():
                    out.append(line)
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    out.append(line)
                    continue
                if rec.get("evidence_id") == eid and \
                        len(rec.get("text") or "") < 600:
                    rec["text"] = body[:TEXT_CAP]
                    meta = rec.get("meta") or {}
                    meta["content_state"] = "FULLTEXT"
                    meta["backfilled_from"] = f"federalregister.gov/{doc_no} (raw_text)"
                    meta["full_chars"] = len(body)
                    rec["meta"] = meta
                    out.append(json.dumps(rec, ensure_ascii=False))
                    changed = True
                else:
                    out.append(line)
            if changed:
                fp.write_text("\n".join(out) + "\n", encoding="utf-8")
        updated.append({"evidence_id": eid, "chars": len(body)})
        print(f"  ✅ {eid}: {len(body)} 字符")

    # ademe FR 记录检查
    from app.policy.backfill import load_records
    recs = {r["evidence_id"]: r for r in load_records(ROOT)}
    fr_rec = recs.get("69431a63b9fbd463") or {}
    meta = fr_rec.get("meta") or {}
    ftp = meta.get("full_text_path")
    print(f"\nFR 记录 full_text_path={ftp}")
    if ftp:
        p = Path(ftp)
        if not p.is_absolute():
            p = ROOT / ftp
        print(f"  exists={p.exists()}  size="
              f"{p.stat().st_size if p.exists() else '-'}")

    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    log.setdefault("runs", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "non_eu", "updated": updated})
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n→ 更新 {len(updated)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
