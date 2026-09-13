# -*- coding: utf-8 -*-
"""PL ISAP（isap.sejm.gov.pl）连接器 —— 波兰官方法律文书信息系统。

Source Proof（2026-09-13，outputs/audit/source_proofs/PL.json）：
    · DocDetails.xsp?id=WDU... 直链可读（样本 3/3：电池法/ELV/废物法）
    · search.xsp 检索未过主题核验 → 采集走**已知文书直链**（DEFAULT_DOCS）

用法：
    async with IsapPlConnector() as c:
        items = await c.fetch()                    # 默认三部核心法
        items = await c.fetch(docs=["WDU20120000021"])
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ConnectorBlocked, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html

MAX_TEXT = 60000


class IsapPlConnector(BaseConnector):
    source_id = "pl_isap"
    base_url = "https://isap.sejm.gov.pl"
    timeout = 45.0

    #: ISAP id → (标题, Dz.U. 引注)；id 经 Source Proof 实抓验证
    DEFAULT_DOCS: dict[str, tuple[str, str]] = {
        "WDU20090790666": ("Ustawa o bateriach i akumulatorach",
                           "Dz.U. 2009 nr 79 poz. 666"),
        "WDU20050250202": ("Ustawa o recyklingu pojazdów wycofanych z eksploatacji",
                           "Dz.U. 2005 nr 25 poz. 202"),
        "WDU20120000021": ("Ustawa o odpadach", "Dz.U. 2012 poz. 21"),
    }

    def doc_url(self, doc_id: str) -> str:
        return f"{self.base_url}/isap.nsf/DocDetails.xsp?id={doc_id}"

    async def _fetch_doc_html(self, url: str) -> str:
        """浏览器 UA 优先；遇挑战页（Distil/Imperva）再试 curl（SChannel 指纹）。"""
        resp = await self._polite_get(url, headers={"User-Agent": BROWSER_UA})
        if not detect_challenge(resp.text):
            return resp.text
        resp2 = await self._try_curl(url, "GET", {})
        if resp2 is not None and resp2.status_code == 200 \
                and not detect_challenge(resp2.text):
            return resp2.text
        raise ConnectorBlocked(
            f"{self.source_id}: bot 挑战页（Distil/Imperva），UA/curl 均未通过：{url}")

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = docs or list(self.DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for doc_id in targets:
            try:
                html = await self._fetch_doc_html(self.doc_url(doc_id))
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": doc_id, "error": type(exc).__name__})
                print(f"    ⚠️ pl_isap {doc_id} 失败：{type(exc).__name__}")
                continue
            title = extract_title(html)
            fallback, cite = self.DEFAULT_DOCS.get(doc_id, (doc_id, ""))
            out.append(RawEvidence(
                evidence_id=f"pl_isap_{doc_id.lower().replace('wdu', '')}",
                channel="connector", source_id=self.source_id,
                source_url=self.doc_url(doc_id),
                source_title=f"{fallback}" + (f" — {title}" if title and 'isap' not in title.lower() else ""),
                publish_date=None,
                raw_text=strip_html(html)[:MAX_TEXT],
                meta={"region": "EU", "jurisdiction": "PL",
                      "doc_key": f"PL:ISAP:{doc_id}",
                      "citation": cite,
                      "page_title": title,
                      "collector": "IsapPlConnector",
                      "official_domain": "isap.sejm.gov.pl",
                      "language": "pl",
                      "source_role": "MS_LEGISLATION_DATABASE"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url("WDU20090790666"))
            ok = resp.status_code == 200 and len(resp.content) > 1000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
