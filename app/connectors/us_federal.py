"""美国联邦公报连接器 —— 走官方公开 API（无需 API Key）。

实测结论（2026-09-10）
--------------------
    GET https://www.federalregister.gov/api/v1/documents.json
        ?conditions[term]=battery+recycling
        &conditions[agencies][]=energy-department
        &per_page=20&order=newest
    → HTTP 200
    → {"count": 48, "total_pages": 16, "results": [...]}

    · 不需要 API Key（官方文档明确："APIs do not require API keys"）
    · 返回体含 html_url / pdf_url / publication_date / agencies / abstract，
      可直接作为溯源 URL

覆盖价值
--------
    DOE / EPA / IRS / FERC 的**规则、拟议规则、通知、资助机会公告**全部在此。
    对美方政策监测，这一个源顶十个新闻站——因为它是最上游的原始出处。
"""

from __future__ import annotations

import time as _t
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence, parse_date

API_BASE = "https://www.federalregister.gov/api/v1/documents.json"

# 与我方 policy-us.yaml 的主题目录对应
DEFAULT_AGENCIES = [
    "energy-department",
    "environmental-protection-agency",
    "internal-revenue-service",
]

DEFAULT_TERMS = [
    "battery recycling",
    "lithium-ion battery",
    "battery material",
    "critical minerals",
]

# 只取需要的字段，减小返回体积
FIELDS = [
    "title", "abstract", "html_url", "pdf_url", "publication_date",
    "document_number", "type", "agencies", "excerpts",
]


class FederalRegisterConnector(BaseConnector):
    """美国联邦公报连接器。"""

    source_id = "us_federal_register"
    base_url = API_BASE
    timeout = 30.0

    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """
        query=None             → 用默认机构 × 默认关键词做一轮
        query="gemm"-style     → 不适用（该源按机构+关键词检索）
        kwargs:
            agencies : list[str]  覆盖默认机构
            terms    : list[str]  覆盖默认关键词
            since    : "2024-01-01" 起始发布日期
            max_pages: int        每个条件的最大翻页数（默认 3）
        """
        agencies = kwargs.get("agencies", DEFAULT_AGENCIES)
        terms = kwargs.get("terms", DEFAULT_TERMS)
        since = kwargs.get("since")
        max_pages = int(kwargs.get("max_pages", 3))
        per_page = int(kwargs.get("per_page", 20))

        out: list[RawEvidence] = []
        for term in terms:
            out += await self._search(
                term=term, agencies=agencies, since=since,
                max_pages=max_pages, per_page=per_page,
            )
        return self._dedupe(out)

    async def _search(
        self, term: str, agencies: list[str], since: str | None,
        max_pages: int, per_page: int,
    ) -> list[RawEvidence]:
        out: list[RawEvidence] = []
        page = 1
        while page <= max_pages:
            params: list[tuple[str, str]] = [
                ("conditions[term]", term),
                ("per_page", str(per_page)),
                ("order", "newest"),
                ("page", str(page)),
            ]
            for ag in agencies:
                params.append(("conditions[agencies][]", ag))
            if since:
                params.append(("conditions[publication_date][gte]", since))
            for f in FIELDS:
                params.append(("fields[]", f))

            resp = await self._polite_get(self.base_url, params=params)
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ConnectorError(f"{self.source_id}: 返回非 JSON") from exc

            results = payload.get("results", [])
            if not results:
                break

            for doc in results:
                out.append(self._to_evidence(doc, term))

            total_pages = int(payload.get("total_pages") or 0)
            if page >= total_pages:
                break
            page += 1
        return out

    def _to_evidence(self, doc: dict[str, Any], term: str) -> RawEvidence:
        agencies = ", ".join(
            (a.get("name") or a.get("raw_name") or "") for a in doc.get("agencies", [])
        ).strip(", ")
        # 摘要 + 摘录一起给下游做相关性判定（excerpts 里是命中片段）
        body = "\n".join(filter(None, [
            doc.get("title"),
            doc.get("abstract"),
            (doc.get("excerpts") or "").replace("<span class=\"match\">", "")
                                     .replace("</span>", ""),
        ]))
        return RawEvidence(
            evidence_id=f"us_fr_{doc.get('document_number', '')}",
            channel="connector",
            source_id=self.source_id,
            source_url=doc.get("html_url"),
            source_title=doc.get("title"),
            publish_date=parse_date(doc.get("publication_date")),
            raw_text=body,
            meta={
                "document_number": doc.get("document_number"),
                "type": doc.get("type"),                 # Rule / Proposed Rule / Notice
                "agencies": doc.get("agencies", []),
                "pdf_url": doc.get("pdf_url"),
                "discovered_by": term,
                "region": "US",
            },
        )

    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            resp = await self._polite_get(self.base_url, params=[
                ("conditions[term]", "battery recycling"),
                ("conditions[agencies][]", "energy-department"),
                ("per_page", "3"),
                ("order", "newest"),
                ("fields[]", "title"),
                ("fields[]", "publication_date"),
                ("fields[]", "document_number"),
            ])
            payload = resp.json()
            return ProbeResult(
                source_id=self.source_id,
                reachable=True,
                status_code=resp.status_code,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=int(payload.get("count") or 0),
                sample=[r.get("document_number", "?") for r in payload.get("results", [])],
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id,
                reachable=False,
                status_code=None,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=0,
                blocked="拦截" in str(exc),
                error=str(exc),
            )

    @staticmethod
    def _dedupe(items: list[RawEvidence]) -> list[RawEvidence]:
        seen: set[str] = set()
        out: list[RawEvidence] = []
        for it in items:
            if it.evidence_id in seen:
                continue
            seen.add(it.evidence_id)
            out.append(it)
        return out
