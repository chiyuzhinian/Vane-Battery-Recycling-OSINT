# -*- coding: utf-8 -*-
"""CBP CROSS 连接器（Phase 4B-1 Step 5）—— 海关归类裁定官方 API。

实测结论（2026-09-12）
--------------------
    GET https://rulings.cbp.gov/api/search?term=battery    → 200 JSON
        {"rulings":[{rulingNumber, subject, categories, rulingDate, …}], "totalHits": N}
    · 检索是**模糊**的（搜 battery 会带回巧克力/甘草糖裁定）→ 必须主题过滤（us_trade）
    · 详情页 https://rulings.cbp.gov/ruling/{number}（SPA，需人工打开）
    · www.cbp.gov 主站 → 403 Access Denied（记 HTTP_403，不是"没有 CBP"）
    · CROSS 检索页 https://rulings.cbp.gov/search?... = JS 渲染 SPA（无静态结果）

纪律：CBP 裁定 = official_guidance / non_binding；**不得**判 regulation。
"""

from __future__ import annotations

import time as _t
from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence

API = "https://rulings.cbp.gov/api/search"


class CrossConnector(BaseConnector):
    source_id = "cbp_cross"
    base_url = API
    timeout = 60.0

    async def search(self, term: str, *, limit: int = 20) -> list[RawEvidence]:
        from app.policy.us_trade import cross_record, parse_cross_rulings, parse_ruling_date

        resp = await self._polite_get(API, params=[("term", term)])
        payload = resp.json()
        out: list[RawEvidence] = []
        for ruling in parse_cross_rulings(payload, term=term)[:limit]:
            rec = cross_record(ruling)
            out.append(RawEvidence(
                evidence_id=rec["evidence_id"], channel="connector",
                source_id=self.source_id, source_url=rec["url"],
                source_title=rec["title"],
                publish_date=parse_ruling_date(rec.get("publish_date", "")),
                raw_text=rec["text"],
                meta={**rec["meta"], "query": term},
            ))
        return out

    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        if not query:
            return []
        return await self.search(query, limit=int(kwargs.get("limit", 20)))

    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            resp = await self._polite_get(API, params=[("term", "battery")])
            payload = resp.json()
            n = len(payload.get("rulings") or [])
            return ProbeResult(source_id=self.source_id, reachable=True,
                               status_code=resp.status_code,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=int(payload.get("totalHits") or n),
                               sample=[r.get("rulingNumber") for r in
                                       (payload.get("rulings") or [])[:5]])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(source_id=self.source_id, reachable=False,
                               status_code=None,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=0, error=str(exc))
