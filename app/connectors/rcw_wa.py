# -*- coding: utf-8 -*-
"""US-WA RCW（app.leg.wa.gov）连接器 —— 华盛顿州修订法典（官方）。

Source Proof（2026-09-13，outputs/audit/source_proofs/US-WA.json）：
    · RCW 70A.555（电池 stewardship 专章）章节页 200 且全文可读 ✅
    · URL 形态：default.aspx?cite={chapter}[&full=true]

用法：
    async with RcwWaConnector() as c:
        items = await c.fetch()          # 默认两个章（电池 stewardship / 废物回收）
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ConnectorError, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 80000
MIN_TEXT = 2000


class RcwWaConnector(BaseConnector):
    source_id = "us_wa_rcw"
    base_url = "https://app.leg.wa.gov"
    timeout = 60.0

    #: (章号, 标题, doc_key)
    DEFAULT_DOCS: list[tuple[str, str, str]] = [
        ("70A.555", "RCW 70A.555 — Battery stewardship（电池管理专章）",
         "US-WA:RCW:70A.555"),
        ("70A.200", "RCW 70A.200 — Waste reduction, recycling（废物减量与回收）",
         "US-WA:RCW:70A.200"),
    ]

    def doc_url(self, cite: str) -> str:
        return f"{self.base_url}/RCW/default.aspx?cite={cite}&full=true"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = [d for d in self.DEFAULT_DOCS
                   if not docs or d[2] in docs or d[0] in docs]
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for cite, label, doc_key in targets:
            url = self.doc_url(cite)
            try:
                resp = await self._polite_get(url, headers={"User-Agent": BROWSER_UA})
                html = resp.text
                if detect_challenge(html):
                    raise ConnectorError("challenge_page")
                text = strip_html(html)
                if len(text) < MIN_TEXT:
                    raise ConnectorError(f"正文不足（{len(text)} 字符）")
                body, nav_removed = trim_nav(text)
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": doc_key, "error": type(exc).__name__})
                print(f"    ⚠️ us_wa_rcw {doc_key} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"us_wa_rcw_{cite.replace('.', '_').lower()}",
                channel="connector", source_id=self.source_id,
                source_url=url, source_title=label, publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-WA",
                      "doc_key": doc_key,
                      "page_title": extract_title(html),
                      "nav_trimmed_chars": nav_removed,
                      "collector": "RcwWaConnector",
                      "official_domain": "app.leg.wa.gov",
                      "language": "en",
                      "source_role": "STATE_STATUTES"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        url = self.doc_url("70A.555")
        try:
            resp = await self._polite_get(url, headers={"User-Agent": BROWSER_UA})
            ok = resp.status_code == 200 and len(resp.content) > 5000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0, sample=[url])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
