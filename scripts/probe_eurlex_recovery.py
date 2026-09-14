# -*- coding: utf-8 -*-
"""probe_eurlex_recovery.py —— Phase 4B-2B1R Step 1/2。

EUR-Lex / CELLAR 真实 endpoint probe + RECOVERED/DEGRADED 判定。
纪律：只探测与判定，**不修改 connector/parser**。

产物：outputs/audit/eurlex_recovery_probe.json
用法：py scripts/probe_eurlex_recovery.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

OUT = ROOT / "outputs" / "audit" / "eurlex_recovery_probe.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"}

#: 探测矩阵（主体文书为准；R(N) 更正件单列为 known-limitation——
#: EUR-Lex 对 corrigendum CELEX 无在线变体（202/404，服务正常时亦然））
PROBES = [
    ("eurlex_homepage", "https://eur-lex.europa.eu/homepage.html", "html"),
    ("celex_metadata_landing",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542",
     "html"),
    ("celex_fulltext_html_32023R1542",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023R1542",
     "fulltext"),
    ("celex_fulltext_html_32024R0785",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R0785",
     "fulltext"),
    ("corrigendum_variant_32023R1542R01_known_limit",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
     "?uri=CELEX:32023R1542R(01)",
     "known_limit"),
    ("celar_rdf_52023SC0255",
     "https://publications.europa.eu/resource/celex/52023SC0255", "cellar"),
]

DEGRADED_MARKERS = (
    "temporarily not fully available",
    "under maintenance",
    "service unavailable",
    "just a moment",
    "checking your browser",
    "enable javascript",
)


def probe(name: str, url: str, kind: str) -> dict:
    rec = {"checked_at": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "endpoint": name, "url": url, "kind": kind}
    t0 = time.monotonic()
    try:
        headers = dict(UA)
        if kind == "cellar":
            headers["Accept"] = "application/rdf+xml"
        r = httpx.get(url, timeout=40, follow_redirects=True, headers=headers)
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        rec["http_status"] = r.status_code
        rec["content_length"] = len(r.content)
        rec["content_type"] = r.headers.get("content-type", "")
        body = r.text or ""
        low = body.lower()
        sig = [m for m in DEGRADED_MARKERS if m in low]
        rec["degraded_signals"] = sig
        rec["final_url"] = str(r.url)
        if kind == "fulltext":
            # 正文判定：200 且长度充裕（短决定类 12K 亦为真实全文）且无降级信号
            rec["fulltext_readable"] = (
                r.status_code == 200 and len(r.content) > 8_000
                and not sig)
        if kind == "cellar":
            rec["rdf_ok"] = bool(r.status_code == 200
                                 and "rdf" in rec["content_type"])
        if name == "celex_metadata_landing":
            rec["has_celex_title"] = bool(
                re.search(r"32023R1542", body)) and r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        rec["http_status"] = None
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return rec


def main() -> int:
    probes = [probe(*p) for p in PROBES]

    by = {p["endpoint"]: p for p in probes}
    ft1 = by["celex_fulltext_html_32023R1542"].get(
        "fulltext_readable", False)
    ft2 = by["celex_fulltext_html_32024R0785"].get(
        "fulltext_readable", False)
    meta = (by["celex_metadata_landing"].get("http_status") == 200
            and by["celex_metadata_landing"].get("has_celex_title", False))
    cellar = by["celar_rdf_52023SC0255"].get("rdf_ok", False)
    rn = by["corrigendum_variant_32023R1542R01_known_limit"]

    recovered = bool(meta and (ft1 or ft2))
    detail = {
        "metadata_readable": meta,
        "fulltext_readable_32023R1542": ft1,
        "fulltext_readable_32024R0785": ft2,
        "cellar_rdf_ok": cellar,
        "corrigendum_variant_status": rn.get("http_status"),
        "corrigendum_note": ("R(N) 更正件在 EUR-Lex 无在线变体"
                             "（202/404，服务正常时亦然）——known limitation"
                             "而非降级信号"),
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "probes": probes,
        "evidence": detail,
        "EURLEX_RECOVERED": recovered,
        "verdict": "RECOVERED" if recovered else "DEGRADED",
        "note": ("判定纪律（2B1R §2）：真实 CELEX metadata 可读 + fulltext 可读 + "
                 "内容非 challenge/maintenance/degraded shell → RECOVERED。"
                 "DEGRADED 时停止 backfill（不绕过官方服务故障）。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("=== EUR-Lex / CELLAR Recovery Probe ===")
    for p in probes:
        print(f"  [{p.get('http_status')}] {p['endpoint']:36s} "
              f"{p.get('content_length', '-')}B "
              f"{p.get('content_type', '')[:24]:24s} "
              f"{p.get('latency_ms', '-')}ms "
              f"{'signals=' + str(p['degraded_signals']) if p.get('degraded_signals') else ''}"
              f"{' ERR=' + p['error'][:40] if p.get('error') else ''}")
    print(f"\n  evidence: {detail}")
    print(f"  EURLEX_RECOVERED = {recovered}  → {payload['verdict']}")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
