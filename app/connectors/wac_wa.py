# -*- coding: utf-8 -*-
"""US-WA WAC 连接器 —— 华盛顿行政法规（app.leg.wa.gov/WAC）。

Step 6 探测（2026-09-14）：
    · /WAC/default.aspx?cite=173-303 → 危废章（181KB，含 battery 条款）
    · cite 模式与 RCW 同站同法（default.aspx?cite=）
    · Title 173 目录页（152KB）亦含 battery 词

用法：
    async with WacWaConnector() as c:
        items = await c.fetch(docs=["173-303", ...])
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 120_000
MIN_TEXT = 800

BASE = "https://app.leg.wa.gov"
#: 经 Step 6 验证（173-303 = 危废规章；173-306 = 特殊废物；173 = Title 目录）
DEFAULT_DOCS = ["173-303", "173-306", "173"]


class WacWaConnector(BaseConnector):
    source_id = "us_wa_wac"
    base_url = BASE
    timeout = 60.0

    def doc_url(self, cite: str) -> str:
        return f"{BASE}/WAC/default.aspx?cite={cite}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = list(docs or DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for cite in targets:
            url = self.doc_url(cite)
            try:
                resp = await self._polite_get(url,
                                              headers={"User-Agent": BROWSER_UA})
                html = resp.text
                if detect_challenge(html):
                    raise RuntimeError("challenge_page")
                body, nav = trim_nav(strip_html(html))
                if len(body) < MIN_TEXT:
                    raise RuntimeError(f"text_too_short({len(body)})")
                page_title = extract_title(html)
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": cite,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ us_wa_wac {cite} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"us_wa_wac_{cite.replace('.', '_').lower()}",
                channel="connector", source_id=self.source_id,
                source_url=url,
                source_title=page_title or f"WAC {cite}", publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-WA",
                      "doc_key": f"US-WA:WAC:{cite}",
                      "nav_trimmed_chars": nav,
                      "collector": "WacWaConnector",
                      "official_domain": "app.leg.wa.gov",
                      "language": "en",
                      "source_role": "STATE_ADMIN_CODE"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url("173-303"),
                                          headers={"User-Agent": BROWSER_UA})
            ok = resp.status_code == 200 and len(resp.content) > 5000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.doc_url("173-303")])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
