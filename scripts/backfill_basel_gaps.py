# -*- coding: utf-8 -*-
"""backfill_basel_gaps.py —— Basel 8 条缺口回填（Phase 4B-2B1 §5）。

PDF → pypdf 提取；docx → zipfile 解析 word/document.xml；
.doc（旧二进制）→ 如实标记（无法可靠解析）。
幂等；原地更新 outputs/*.jsonl。
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
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
TEXT_CAP = 400_000
BASEL_EIDS = [f"int_basel_doc_{i}" for i in range(8)]

#: 同文书异格式副本（legacy .doc ← 已抓同语言 PDF；内容同一版本）
DOC_ALIAS = {
    "int_basel_doc_3": "int_basel_doc_4",   # Arabic CHW.12 file
    "int_basel_doc_5": "int_basel_doc_6",   # Chinese CHW.12 file
}


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for pg in reader.pages:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    return re.sub(r"[ \t]+", " ", "\n".join(pages)).strip()


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    text = re.sub(r"<w:p[ >]", "\n<", xml)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s{3,}", "\n\n", text).strip()


def main() -> int:
    from app.policy.backfill import load_records
    recs = {r["evidence_id"]: r for r in load_records(ROOT)}
    targets = []
    for eid in BASEL_EIDS:
        r = recs.get(eid)
        if r and len(r.get("text") or "") < 600:
            targets.append((eid, r.get("url") or ""))
    print(f"待回填 {len(targets)} / 8")

    updated, failed = [], []
    bodies: dict[str, str] = {}
    # 前置：alias 记录若已有正文，先收集（同文书 PDF 代填）
    for eid, src_eid in DOC_ALIAS.items():
        src = recs.get(src_eid) or {}
        if len(src.get("text") or "") >= 600:
            bodies[eid] = src["text"]
            print(f"  ↪ {eid} ← {src_eid}（同文书 PDF 代填）")
    for eid, url in targets:
        if eid in bodies:
            continue
        if not url:
            continue
        low = url.lower()
        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True,
                             headers=UA)
            if resp.status_code != 200 or len(resp.content) < 1000:
                failed.append((eid, f"http {resp.status_code}"))
                continue
            if low.endswith(".pdf"):
                text = pdf_text(resp.content)
            elif low.endswith(".docx"):
                text = docx_text(resp.content)
            elif low.endswith(".doc"):
                failed.append((eid, "legacy .doc unparseable"))
                continue
            else:
                failed.append((eid, "unknown format"))
                continue
            if len(text) < 600:
                failed.append((eid, f"extracted too short ({len(text)})"))
                continue
            bodies[eid] = text
            print(f"  ✅ {eid}: {len(text)} 字符")
        except Exception as exc:  # noqa: BLE001
            failed.append((eid, f"{type(exc).__name__}"))
            print(f"  ❌ {eid}: {type(exc).__name__} {str(exc)[:60]}")

    if bodies:
        for fp in sorted(OUTPUTS.glob("*.jsonl")):
            if fp.name.startswith(("_", "review")):
                continue
            lines = fp.read_text(encoding="utf-8",
                                 errors="replace").splitlines()
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
                eid = rec.get("evidence_id")
                if eid in bodies and len(rec.get("text") or "") < 600:
                    rec["text"] = bodies[eid][:TEXT_CAP]
                    meta = rec.get("meta") or {}
                    meta["content_state"] = "FULLTEXT"
                    if eid in DOC_ALIAS:
                        meta["backfilled_from"] = (
                            f"basel.int same-document PDF "
                            f"(alias of {DOC_ALIAS[eid]})")
                    else:
                        meta["backfilled_from"] = "basel.int PDF/docx (pypdf/zip)"
                    meta["full_chars"] = len(bodies[eid])
                    rec["meta"] = meta
                    out.append(json.dumps(rec, ensure_ascii=False))
                    changed = True
                else:
                    out.append(line)
            if changed:
                fp.write_text("\n".join(out) + "\n", encoding="utf-8")
        updated = list(bodies)

    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    log.setdefault("runs", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "basel", "updated": updated,
        "failed": [{"eid": e, "reason": r} for e, r in failed]})
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n→ 更新 {len(updated)}；失败 {len(failed)}")
    for e, r in failed:
        print(f"   ⚠️ {e}: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
