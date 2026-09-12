# -*- coding: utf-8 -*-
"""govinfo 连接器（Phase 4B-1 Step 4）—— U.S. Code / Public Law 官方通道。

官方通道（实测 2026-09-12）：
    USC 目录   : wssearch/rb/uscode               → 200（年份枚举）
    USC 正文   : content/pkg/USCODE-{y}-title{t}/html/USCODE-{y}-title{t}-chap{c}.htm → 200
    PLAW 枚举  : wssearch/rb/plaw                 → 200（届别 119/118/117… + docCount）
    PLAW 正文  : content/pkg/PLAW-{c}publ{n}/html/PLAW-{c}publ{n}.htm → 200
    congress.gov API → 403（需 Key）→ 记 API_KEY_REQUIRED（官方替代=govinfo）

纪律：uscode.house.gov 在 Python 侧超时（TIMEOUT），不是"没有 USC"——官方替代通道照常工作。
"""

from __future__ import annotations

import time as _t
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

WS = "https://www.govinfo.gov/wssearch/rb"
PKG = "https://www.govinfo.gov/content/pkg"


class GovInfoUsCodeConnector(BaseConnector):
    source_id = "us_usc"
    base_url = PKG
    timeout = 90.0

    async def list_years(self) -> list[str]:
        resp = await self._polite_get(f"{WS}/uscode")
        payload = resp.json()
        years = []
        for node in payload.get("childNodes") or []:
            v = (node.get("nodeValue") or {}).get("displayValue")
            if v and v.isdigit():
                years.append(v)
        return years

    async def fetch_chapter(self, year: str, title: int, chapter: str) -> str:
        url = (f"{PKG}/USCODE-{year}-title{title}/html/"
               f"USCODE-{year}-title{title}-chap{chapter}.htm")
        resp = await self._polite_get(url)
        # ⚠️ 实测：不存在的章节可能 302→伪 404（HTTP 200 + 'Page Not Found'），
        #    或者直接 302。两种都记为失败（ConnectorError），不得当 0 结果。
        if resp.status_code in (301, 302):
            raise ConnectorError(
                f"USC {year} title-{title} chap{chapter} 重定向（文件不存在：{resp.status_code}）")
        if resp.status_code == 404:
            raise ConnectorError(f"USC {year} title-{title} chap{chapter} 不存在（404）")
        return resp.text

    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        return []                     # 结构化采集见 scripts/collect_us_code_plaw.py

    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            years = await self.list_years()
            return ProbeResult(source_id=self.source_id, reachable=True,
                               status_code=200,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=len(years), sample=years[:5])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(source_id=self.source_id, reachable=False,
                               status_code=None,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=0, error=str(exc))


class GovInfoPublicLawConnector(BaseConnector):
    source_id = "us_plaw"
    base_url = PKG
    timeout = 120.0

    async def list_congresses(self) -> list[dict]:
        resp = await self._polite_get(f"{WS}/plaw")
        payload = resp.json()
        out: list[dict] = []
        for node in payload.get("childNodes") or []:
            nv = node.get("nodeValue") or {}
            if nv.get("value"):
                out.append({"congress": str(nv["value"]),
                            "display": nv.get("displayValue", ""),
                            "doc_count": nv.get("docCount", 0)})
        return out

    async def fetch_public_law(self, congress: int, number: int) -> str:
        url = (f"{PKG}/PLAW-{congress}publ{number}/html/"
               f"PLAW-{congress}publ{number}.htm")
        resp = await self._polite_get(url)
        if resp.status_code == 404:
            raise ConnectorError(f"PLAW {congress}-{number} 不存在（404）")
        return resp.text

    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        return []                     # 结构化采集见 scripts/collect_us_code_plaw.py

    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            rows = await self.list_congresses()
            return ProbeResult(source_id=self.source_id, reachable=True,
                               status_code=200,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=len(rows),
                               sample=[r["congress"] for r in rows[:5]])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(source_id=self.source_id, reachable=False,
                               status_code=None,
                               latency_ms=int((_t.monotonic() - t0) * 1000),
                               records_found=0, error=str(exc))
