# -*- coding: utf-8 -*-
"""eCFR 连接器（Phase 4B-1 Step 3）—— 官方 API，无需 API Key。

实测结论（2026-09-12）
--------------------
    GET /api/versioner/v1/titles.json                        → 200 {"titles":[...]}
    GET /api/search/v1/results?query=battery&per_page=1      → 200 {"results":[...]}
    GET /api/versioner/v1/full/{date}/title-40.xml?part=273  → 200（需 Accept: xml）
        · 49 CFR 171 = 242KB ／ 40 CFR 273 = 89KB（实测大小）
        · <DIV8 N="273.1" TYPE="SECTION"> + <HEAD> + <AUTH>
    GET /api/versioner/v1/full/.../part=1（不存在）           → 404 {"error":"No matching content found."}

覆盖价值
--------
    FR 说"最终规则修改 49 CFR 172"，eCFR 是"这些条文现在长什么样"的官方权威。
    FR → codified_in → CFR 的接收端，同时提供 Authority / USC 引用（→ Step 4 的桥）。
"""

from __future__ import annotations

import time as _t
from datetime import date
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

BASE = "https://www.ecfr.gov/api/versioner/v1"
SEARCH = "https://www.ecfr.gov/api/search/v1/results"

#: 与电池回收直接相关的 CFR 目标（Step 3 首批）
DEFAULT_PARTS: list[tuple[int, str]] = [
    (49, "171"),   # 危货运输 通则/定义
    (49, "172"),   # 危货分类/包装/标识
    (49, "173"),   # 危货托运具体要求（锂电池条款）
    (40, "260"),   # RCRA 危废 通则
    (40, "261"),   # 危废 鉴别（black mass 危废定性）
    (40, "273"),   # 通用废物（电池收集的联邦框架）
]

_ACCEPT_XML = {"Accept": "application/xml, text/xml, */*"}


class EcfrConnector(BaseConnector):
    """eCFR 连接器：标题目录 / 全文检索 / 按 Part 取官方 XML。"""

    source_id = "us_ecfr"
    base_url = BASE
    timeout = 60.0

    # ------------------------------------------------------ 通道 1：目录

    async def fetch_titles(self) -> list[dict[str, Any]]:
        resp = await self._polite_get(f"{BASE}/titles.json",
                                      headers=_ACCEPT_XML)
        payload = resp.json()
        return payload.get("titles") or []

    async def latest_issue_date(self, title: int) -> str:
        """该 title 的最新可用版本日期。

        ⚠️ 实测（2026-09-12）：拿当天日期请求会在 title 最新发布日之前时
        返回 404（"requested date ... is past the title's most recent issue date"）。
        必须先从 titles.json 读 latest_issue_date。
        """
        for t in await self.fetch_titles():
            try:
                if int(t.get("number")) == int(title):
                    return str(t.get("latest_issue_date")
                               or t.get("up_to_date_as_of") or "")
            except (TypeError, ValueError):
                continue
        return ""

    # ------------------------------------------------------ 通道 2：检索

    async def search_documents(self, query: str, *,
                               per_page: int = 20) -> list[RawEvidence]:
        resp = await self._polite_get(SEARCH, params=[
            ("query", query), ("per_page", str(per_page))],
            headers=_ACCEPT_XML)
        payload = resp.json()
        out: list[RawEvidence] = []
        for hit in payload.get("results") or []:
            out.append(RawEvidence(
                evidence_id=f"us_ecfr_search_{hit.get('document_number') or hit.get('id') or len(out)}",
                channel="connector",
                source_id=self.source_id,
                source_url=hit.get("link") or hit.get("url"),
                source_title=hit.get("title") or hit.get("heading"),
                publish_date=None,
                raw_text=str(hit.get("excerpt") or hit.get("abstract") or "")[:4000],
                meta={"region": "US", "collector": "ecfr_search",
                      "query": query, "hit": {k: hit.get(k) for k in
                                              ("title", "link", "type", "part", "title_number")}},
            ))
        return out

    # ------------------------------------------------------ 通道 3：官方 XML

    async def fetch_part_xml(self, title: int, part: str,
                             *, as_of: str | None = None) -> str:
        if not as_of:
            as_of = (await self.latest_issue_date(title)) or \
                date.today().isoformat()
        url = f"{BASE}/full/{as_of}/title-{title}.xml"
        try:
            resp = await self._polite_get(url, params=[("part", str(part))],
                                          headers=_ACCEPT_XML)
        except ConnectorError:
            raise
        if resp.status_code == 404:
            raise ConnectorError(f"eCFR: title-{title} part-{part} 不存在（404）")
        return resp.text

    # ------------------------------------------------------ 契约

    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """query 给定时走全文检索；否则返回空（Part 采集请用 collect_ecfr_parts.py）。"""
        if not query:
            return []
        return await self.search_documents(query,
                                           per_page=int(kwargs.get("per_page", 20)))

    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            resp = await self._polite_get(f"{BASE}/titles.json",
                                          headers=_ACCEPT_XML)
            payload = resp.json()
            titles = payload.get("titles") or []
            return ProbeResult(
                source_id=self.source_id, reachable=True,
                status_code=resp.status_code,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=len(titles),
                sample=[str(t.get("number")) for t in titles[:5]],
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((_t.monotonic() - t0) * 1000), records_found=0,
                blocked="拦截" in str(exc), error=str(exc))
