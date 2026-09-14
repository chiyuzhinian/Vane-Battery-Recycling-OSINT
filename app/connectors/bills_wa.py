# -*- coding: utf-8 -*-
"""US-WA Bills 连接器 —— 华盛顿州立法法案（app.leg.wa.gov/billsummary）。

Step 6 探测（2026-09-14）：SB 5144 (2023) = 电池管理法（84KB，
含 battery 条款）✓；billsummary 页为服务器渲染。

用法：
    async with BillsWaConnector() as c:
        items = await c.fetch(docs=["5144/2023"])
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 120_000
MIN_TEXT = 800

BASE = "https://app.leg.wa.gov"
#: 经 Step 6 验证：SB 5144 (2023) 电池管理法
DEFAULT_DOCS = ["5144/2023"]


class BillsWaConnector(BaseConnector):
    source_id = "us_wa_bills"
    base_url = BASE
    timeout = 45.0

    def doc_url(self, doc: str) -> str:
        num, year = doc.split("/")
        return (f"{BASE}/billsummary?BillNumber={num}&Year={year}")

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = list(docs or DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for doc in targets:
            num, year = doc.split("/")
            url = self.doc_url(doc)
            try:
                resp = await self._polite_get(
                    url, headers={"User-Agent": BROWSER_UA})
                html = resp.text
                if detect_challenge(html):
                    raise RuntimeError("challenge_page")
                body, nav = trim_nav(strip_html(html))
                if len(body) < MIN_TEXT:
                    raise RuntimeError(f"text_too_short({len(body)})")
                page_title = extract_title(html)
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": doc,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ us_wa_bills {doc} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"us_wa_bills_{num}_{year}",
                channel="connector", source_id=self.source_id,
                source_url=url,
                source_title=page_title or f"WA Bill {num} ({year})",
                publish_date=None, raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-WA",
                      "doc_key": f"US-WA:Bill:{year}:{num}",
                      "nav_trimmed_chars": nav,
                      "collector": "BillsWaConnector",
                      "official_domain": "app.leg.wa.gov",
                      "language": "en",
                      "source_role": "STATE_LEGISLATURE"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url(DEFAULT_DOCS[0]),
                                          headers={"User-Agent": BROWSER_UA})
            ok = resp.status_code == 200 and len(resp.content) > 2000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.doc_url(DEFAULT_DOCS[0])])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
