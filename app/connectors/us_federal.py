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

import re
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

# ⚠️⚠️ 联邦公报的**批量行政文书** —— FR 全文检索的固有噪声
#
# 实测（2026-09-11）：把机构从 4 个扩到 15 个、词表从 20 个扩到 27 个之后，
#   “待人工复核”从个位数冲到 **180 条**。抽样发现绝大多数来自这几类文书：
#
#     “Agency Information Collection Activities”            47+17 条 ← ICR 信息收集公告
#     “Notice of Applications/Actions on Special Permits”   23 条   ← PHMSA 许可通告
#     “Alaska/Alabama: ... State Hazardous Waste Program”   18 条   ← 州级 RCRA 授权
#
#   ⚠️ 这与本项目早先踩过的坑是**同一类**：那时是“不要加 `shippers?`” ——
#     每份危险货物文件都含 shipper，64 条命中里绝大多数是 Special Permits 通告。
#     现在换个词，又从另一个门进来了。
#
#   正解**不是收窄关键词**（会漏真政策），而是**按文档类型过滤**：
#   这些是“行政批量公告”，不是“政策法规”。
#
#   ❗ 注意 “foreign-trade zone” **不列入本表**：FTZ 的生产活动通知
#      （如 “FTZ 193; Authorization of Production Activity; Lithionics Battery”）
#      虽然是行政文书，但它是**真实的产能信号**，应归企业情报而不是丢弃。
BATCH_DOC_NOISE = (
    "agency information collection activities",
    "notice of applications for new special permits",
    "notice of actions on special permits",
    "preliminary effluent guidelines",
)


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
        # ⚠️ 关于 conditions[term] 的实测（2026-09-10 初测 / 2026-09-12 复测更正）：
        #   ① 它是**模糊匹配**（按词 OR）。搜 "black mass"（不带引号）返回 2407 条，
        #      因为命中大量含 "mass" 的文件（Massachusetts / Mass Balance…）。
        #   ② ⭐ 复测更正：**英文双引号短语语法现在可用**！
        #      实测同一查询：不带引号 2407 条 → 带引号 `"black mass"` **5 条**
        #      （且 3 条是真正相关的贸易/关键矿产文书）。
        #      2026-09-10 曾记"引号返回 0 条"——已过时（或当时查询构造有误）。
        #      → 边界短语一律加引号（见 sources/policy-eu-us-eol-blackmass.yaml 的
        #        `"black mass"` 写法）。
        #   最终方案：不改造查询，改为**后置整短语过滤**（见 _phrase_ok）。
        #      这样既能压掉 Massachusetts 这类假阳性，又不破坏 API 行为。
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
                # 多词短语：要求**所有词都出现**（顺序不限），压掉模糊匹配的假阳性。
                # 例：搜 "black mass" 时，"Massachusetts ... black-lung" 这类会被剔除。
                if not self._phrase_ok(doc, term):
                    continue
                # 批量行政文书：FR 全文检索的固有噪声（见 BATCH_DOC_NOISE 注释）
                if self._is_batch_noise(doc):
                    continue
                out.append(self._to_evidence(doc, term))

            total_pages = int(payload.get("total_pages") or 0)
            if page >= total_pages:
                break
            page += 1
        return out

    @staticmethod
    def _phrase_ok(doc: dict[str, Any], term: str) -> bool:
        """多词短语的整词共现校验（大小写不敏感、词边界匹配）。"""
        words = [w for w in re.split(r"\s+", term.strip()) if len(w) > 1]
        if len(words) < 2:
            return True
        haystack = " ".join(filter(None, [
            doc.get("title"), doc.get("abstract"), doc.get("excerpts"),
        ])).lower()
        if not haystack:
            return True          # 没内容可比对时不误杀
        return all(re.search(rf"\b{re.escape(w.lower())}", haystack) for w in words)

    @staticmethod
    def _is_batch_noise(doc: dict[str, Any]) -> bool:
        """该文书是否为“行政批量公告”（非政策法规）？

        只看**标题**：这些文书的标题是固定模板，命中即整类剔除；
        而正文里出现相同短语可能是合法的政策引用，不能一概而论。
        """
        title = (doc.get("title") or "").lower()
        return any(noise in title for noise in BATCH_DOC_NOISE)

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
