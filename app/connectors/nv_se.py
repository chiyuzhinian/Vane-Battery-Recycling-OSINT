# -*- coding: utf-8 -*-
"""SE Naturvårdsverket 连接器 —— 瑞典环境保护署（naturvardsverket.se）。

Step 6 探测（2026-09-14）：主站与 avfall 主题页（259KB）可达；
/vagledning-och-stod/producentansvar/（生产者责任）、
/vagledning-och-stod/avfall-farligt-avfall/（危险废物）为真实子页。

角色：MS_ENVIRONMENT_MINISTRY_OR_AGENCY（SE 7 角色之一）

用法：
    async with NvSeConnector() as c:
        items = await c.fetch()                     # 默认 3 页
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 120_000
MIN_TEXT = 600

BASE = "https://www.naturvardsverket.se"
DEFAULT_PAGES = [
    "/amnesomraden/avfall/",
    "/vagledning-och-stod/producentansvar/",
    "/vagledning-och-stod/avfall-farligt-avfall/",
]


class NvSeConnector(BaseConnector):
    source_id = "se_naturvardsverket"
    base_url = BASE
    timeout = 45.0

    def page_url(self, path: str) -> str:
        return f"{BASE}{path}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = list(docs or DEFAULT_PAGES)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for path in targets:
            url = self.page_url(path)
            slug = path.strip("/").replace("/", "_") or "root"
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
                self.last_errors.append({"doc": path,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ se_naturvardsverket {path} 失败："
                      f"{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"se_naturvardsverket_{slug}",
                channel="connector", source_id=self.source_id,
                source_url=url,
                source_title=page_title or f"Naturvårdsverket {path}",
                publish_date=None, raw_text=body[:MAX_TEXT],
                meta={"region": "EU", "jurisdiction": "SE",
                      "doc_key": f"SE:NV:{path.strip('/')}",
                      "nav_trimmed_chars": nav,
                      "collector": "NvSeConnector",
                      "official_domain": "naturvardsverket.se",
                      "language": "sv",
                      "source_role": "MS_ENVIRONMENT_MINISTRY_OR_AGENCY"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.page_url(DEFAULT_PAGES[0]),
                                          headers={"User-Agent": BROWSER_UA})
            ok = resp.status_code == 200 and len(resp.content) > 2000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.page_url(DEFAULT_PAGES[0])])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
