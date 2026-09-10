"""巨潮资讯（cninfo）连接器 —— 上市公司公告 / 年报。

为什么它是企业侧最重要的源
--------------------------
26 家目标企业里有 13 家是上市公司或其子公司（格林美、光华科技、天奇股份、
中伟股份、赣锋锂业、杰瑞股份、骆驼股份、欣旺达、天能股份、厦门钨业、豪鹏科技…）。
对这些企业，**公告是最早、最权威、且完全免费的信息来源**：
    · 战略合作 / 新项目投资   → strategy 维度
    · 产能与产销量            → operation 维度
    · 年度报告                → 全部 5 个维度
    · 人事任免                → hr 维度

实测确认（2026-09-10）
---------------------
    GET  http://www.cninfo.com.cn/new/fulltextSearch/full
         ?searchkey=动力电池回收&pageNum=1&pageSize=30
         &isfulltext=false&sortName=nothing&sortType=desc
    → HTTP 200 application/json
    → totalAnnouncement=12，首条即"格林美：关于控股子公司动力再生与兰钧新能源
      签署《动力电池绿色回收利用战略合作协议》的公告"

    返回字段（已实测确认，勿臆造）：
      secCode / secName / orgId / announcementId / announcementTitle
      announcementTime(epoch ms) / adjunctUrl(相对 PDF 路径) / adjunctType

    注意：announcementTitle 里含 <em> 高亮标签，入库前必须清洗。

    详情页：http://www.cninfo.com.cn/new/disclosure/detail?stockCode=..&announcementId=..&orgId=..&announcementTime=..
    PDF  ：http://static.cninfo.com.cn/{adjunctUrl}
"""

from __future__ import annotations

import re
import time as _t
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence, parse_date

SEARCH_API = "http://www.cninfo.com.cn/new/fulltextSearch/full"
DETAIL_URL = ("http://www.cninfo.com.cn/new/disclosure/detail"
              "?stockCode={secCode}&announcementId={announcementId}"
              "&orgId={orgId}&announcementTime={ts}")
PDF_URL = "http://static.cninfo.com.cn/{adjunct}"

# 电池回收领域关键词（用于全市场发现，以及给企业侧补充检索）
DEFAULT_KEYWORDS = [
    "动力电池回收", "退役电池", "电池梯次利用", "电池再生利用", "废旧电池",
    "正极材料回收", "黑粉", "电池拆解",
]

# 公告标题关键词 → 对应我方研究维度（多标签，一个标题可能同时命中多个维度）
# 说明：只作为下游抽取器的"提示"，不是最终分类。
# 实测教训：一条"签署动力电池绿色回收利用战略合作协议"同时涉及
#   strategy（战略合作）与 feedstock（回收处理），
#   单标签会丢掉信息，因此改为返回列表。
TITLE_DIMENSION_HINTS: list[tuple[str, str]] = [
    # operation：经营与产能（信息密度最高，优先）
    ("年报", "operation"), ("年度报告", "operation"), ("半年度报告", "operation"),
    ("季报", "operation"), ("业绩", "operation"), ("产销", "operation"),
    ("产能", "operation"), ("产量", "operation"), ("营业收入", "operation"),
    # feedstock：废料量与来源
    ("回收", "feedstock"), ("处理能力", "feedstock"), ("梯次利用", "feedstock"),
    ("再生利用", "feedstock"), ("综合利用", "feedstock"), ("拆解", "feedstock"),
    # technology：工艺技术
    ("专利", "technology"), ("技术", "technology"), ("工艺", "technology"),
    ("研发", "technology"), ("湿法", "technology"),
    # hr：人事
    ("任免", "hr"), ("辞职", "hr"), ("选举", "hr"), ("聘任", "hr"),
    ("高管", "hr"), ("股权激励", "hr"),
    # strategy：战略与资本
    ("合作", "strategy"), ("投资", "strategy"), ("项目", "strategy"),
    ("收购", "strategy"), ("设立", "strategy"), ("战略", "strategy"),
    ("合资", "strategy"), ("备忘录", "strategy"), ("框架协议", "strategy"),
]

_EM_RE = re.compile(r"</?em>")


def clean_title(raw: str) -> str:
    """去掉巨潮返回的 <em> 高亮标签和多余空白。"""
    return _EM_RE.sub("", raw or "").replace("\u200b", "").strip()


def guess_dimensions(title: str) -> list[str]:
    """返回标题命中的全部维度（去重、保序）。"""
    out: list[str] = []
    for kw, dim in TITLE_DIMENSION_HINTS:
        if kw in title and dim not in out:
            out.append(dim)
    return out


class CninfoConnector(BaseConnector):
    """巨潮资讯公告连接器。"""

    source_id = "cninfo"
    base_url = SEARCH_API
    timeout = 30.0

    # ---------- 采集 ----------
    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """
        query 支持三种写法：
          "keyword:动力电池回收"   → 全市场关键词检索（发现新企业/新动态）
          "stock:002340"           → 指定股票代码（盯住已确认的上市企业）
          None                     → 用默认关键词跑一轮全市场
        kwargs:
          since / until : "2024-01-01" 日期范围
          max_pages     : 翻页上限（默认 3）
          page_size     : 每页条数（默认 30）
        """
        since = kwargs.get("since", "")
        until = kwargs.get("until", "")
        max_pages = int(kwargs.get("max_pages", 3))
        page_size = int(kwargs.get("page_size", 30))

        if query and query.startswith("stock:"):
            # 指定股票代码：走 hisAnnouncement/query 更精确
            code = query.split(":", 1)[1]
            return await self._by_stock(code, since, until, max_pages, page_size)

        keywords = [query.split(":", 1)[1]] if (query and query.startswith("keyword:")) \
            else DEFAULT_KEYWORDS

        out: list[RawEvidence] = []
        for kw in keywords:
            out += await self._search(kw, since, until, max_pages, page_size)
        return self._dedupe(out)

    async def _search(self, keyword: str, since: str, until: str,
                      max_pages: int, page_size: int) -> list[RawEvidence]:
        out: list[RawEvidence] = []
        for page in range(1, max_pages + 1):
            params = {
                "searchkey": keyword,
                "sdate": since, "edate": until,
                "isfulltext": "false",
                "sortName": "nothing", "sortType": "desc",
                "pageNum": str(page), "pageSize": str(page_size),
            }
            resp = await self._polite_get(self.base_url, params=params,
                                          headers={"Referer": "http://www.cninfo.com.cn/"})
            payload = resp.json()
            items = payload.get("announcements") or []
            if not items:
                break
            for it in items:
                out.append(self._to_evidence(it, discovered_by=keyword))
            total_pages = int(payload.get("totalpages") or 0)
            if total_pages and page >= total_pages:
                break
        return out

    async def _by_stock(self, code: str, since: str, until: str,
                        max_pages: int, page_size: int) -> list[RawEvidence]:
        """按股票代码取公告（走 hisAnnouncement/query，需先解析 orgId）。"""
        # 先用全文检索拿到该股票的 orgId（接口要求 stock=code,orgId）
        seed = await self._search_by_code(code)
        org_id = seed[0].meta["org_id"] if seed else ""
        column = "szse" if code.startswith(("00", "30")) else "sse"

        out: list[RawEvidence] = []
        for page in range(1, max_pages + 1):
            data = {
                "pageNum": str(page), "pageSize": str(page_size),
                "column": column, "tabName": "fulltext",
                "plate": "", "stock": f"{code},{org_id}" if org_id else "",
                "searchkey": "", "secid": "", "category": "",
                "trade": "", "seDate": f"{since}~{until}" if since else "",
                "sortName": "", "sortType": "", "isHLtitle": "true",
            }
            resp = await self._polite_get(
                "http://www.cninfo.com.cn/new/hisAnnouncement/query",
                method="POST", data=data,
                headers={"Referer": "http://www.cninfo.com.cn/",
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            payload = resp.json()
            items = payload.get("announcements") or []
            if not items:
                break
            for it in items:
                out.append(self._to_evidence(it, discovered_by=f"stock:{code}"))
        return out

    async def _search_by_code(self, code: str) -> list[RawEvidence]:
        """借全文检索快速拿到某股票的 orgId 与名称。"""
        resp = await self._polite_get(
            self.base_url,
            params={"searchkey": code, "pageNum": "1", "pageSize": "5",
                    "isfulltext": "false", "sortName": "nothing", "sortType": "desc"},
            headers={"Referer": "http://www.cninfo.com.cn/"},
        )
        return [self._to_evidence(it, discovered_by=f"resolve:{code}")
                for it in (resp.json().get("announcements") or [])
                if it.get("secCode") == code]

    # ---------- 解析 ----------
    def _to_evidence(self, it: dict[str, Any], discovered_by: str) -> RawEvidence:
        title = clean_title(it.get("announcementTitle") or "")
        code = it.get("secCode") or ""
        org_id = it.get("orgId") or ""
        ann_id = it.get("announcementId") or ""
        ts = it.get("announcementTime") or 0
        adjunct = it.get("adjunctUrl") or ""

        detail = DETAIL_URL.format(secCode=code, announcementId=ann_id,
                                   orgId=org_id, ts=ts) if ann_id else None
        pdf = PDF_URL.format(adjunct=adjunct) if adjunct else None

        return RawEvidence(
            evidence_id=f"cninfo_{ann_id}",
            channel="connector",
            source_id=self.source_id,
            source_url=detail,
            source_title=f"{it.get('secName', '').strip()}：{title}",
            publish_date=(datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                          if ts else None),
            raw_text=f"{it.get('secName', '').strip()}（{code}）：{title}",
            meta={
                "sec_code": code,
                "sec_name": (it.get("secName") or "").strip(),
                "org_id": org_id,
                "announcement_id": ann_id,
                "pdf_url": pdf,
                "adjunct_type": it.get("adjunctType"),
                "dimension_hint": guess_dimensions(title),
                "discovered_by": discovered_by,
                "region": "CN",
                "source_class": "announcement",
            },
        )

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        try:
            resp = await self._polite_get(
                self.base_url,
                params={"searchkey": "动力电池回收", "pageNum": "1", "pageSize": "5",
                        "isfulltext": "false", "sortName": "nothing", "sortType": "desc"},
                headers={"Referer": "http://www.cninfo.com.cn/"},
            )
            payload = resp.json()
            items = payload.get("announcements") or []
            return ProbeResult(
                source_id=self.source_id,
                reachable=True,
                status_code=resp.status_code,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=int(payload.get("totalAnnouncement") or 0),
                sample=[f"{i.get('secName', '').strip()}({i.get('secCode')})"
                        for i in items[:3]],
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
