# -*- coding: utf-8 -*-
"""US-MN Revisor 连接器 —— 明尼苏达法规（revisor.mn.gov）。

Step 5 探测（2026-09-13）：
    · /statutes/cite/{cite} 条文页可达（服务器渲染，如 115A.01）
    · 搜索接口为 JS 壳 → 采集走**按 cite 直链**模式
    · 注：电池专条（2025 版 statutes 未定位到 115A.30xx）——本次样本为
      115A 废物管理章条文（通道验证），电池专条定位列入后续深采

用法：
    async with RevisorMnConnector() as c:
        items = await c.fetch(docs=["115A.01", "115A.02", "115A.03"])
"""
from __future__ import annotations

from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, strip_html, trim_nav

MAX_TEXT = 60_000
MIN_TEXT = 400

BASE = "https://www.revisor.mn.gov"
#: 经 Step 5 验证的高价值样本（电子废物法 + 污染控制法）
DEFAULT_DOCS = ["325E.1251", "325E.125", "116.07"]


class RevisorMnConnector(BaseConnector):
    source_id = "us_mn_revisor"
    base_url = BASE
    timeout = 45.0

    def doc_url(self, cite: str) -> str:
        return f"{BASE}/statutes/cite/{cite}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = list(docs or DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for cite in targets:
            url = self.doc_url(cite)
            try:
                resp = await self._polite_get(url)
                html = resp.text
                if detect_challenge(html):
                    raise RuntimeError("challenge_page")
                body, nav = trim_nav(strip_html(html))
                if len(body) < MIN_TEXT:
                    raise RuntimeError(f"text_too_short({len(body)})")
                title = body[:150].strip()
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": cite,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ us_mn_revisor {cite} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"us_mn_revisor_{cite.replace('.', '_').lower()}",
                channel="connector", source_id=self.source_id,
                source_url=url, source_title=title, publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-MN",
                      "doc_key": f"US-MN:MNStat:{cite}",
                      "nav_trimmed_chars": nav,
                      "collector": "RevisorMnConnector",
                      "official_domain": "revisor.mn.gov",
                      "language": "en",
                      "source_role": "STATE_STATUTES"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url(DEFAULT_DOCS[0]))
            ok = resp.status_code == 200 and len(resp.content) > 500
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.doc_url(DEFAULT_DOCS[0])])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
