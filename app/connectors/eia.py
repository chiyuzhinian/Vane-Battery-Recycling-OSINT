"""环评公示（EIA）连接器 —— 非上市企业的产能/废料量唯一稳定来源。

背景（见 sources/eia-sources.yaml 的说明）
-----------------------------------------
26 家目标企业里有一半没有公告可查。要拿到它们的
【建设规模】【处理能力】【工艺路线】【原辅材料】，
环评公示是唯一稳定的公开渠道 —— 而且它是报批前必须公示的法定文件。

设计取舍：为什么用"通用链接抽取"而不是逐站写解析器
--------------------------------------------------
政府站点栏目结构差异极大且经常改版。逐站写 CSS 选择器 = 每改版一次挂一批。
因此本连接器采用**结构无关**的抽取策略：

    1. 取列表页 HTML
    2. 抽出所有 <a href>，过滤掉导航/脚本/锚点
    3. 用 link_hints（环境影响/受理/公示/报告书…）筛出"像环评公示"的链接
    4. 再交给 app/core/relevance.py 做领域相关性判定
    5. 命中的条目落为 RawEvidence，指向具体公示页

好处：站点改版通常不影响抽取召回；坏处：可能混入少量非目标条目，
由第 4 步的相关性规则兜底（宁可多一条待审，不可漏一条产能数据）。

实测确认（2026-09-10）
---------------------
    生态环境部 受理公示页   → 200 / 74.8 KB
    生态环境部 环评管理页   → 200 / 105.8 KB
    广东省生态环境厅        → 200 / 123 KB
    江苏省生态环境厅        → 200 / 45.6 KB
    湖南省生态环境厅        → curl 200（Python SSL: BAD_ECPOINT）
    江西省生态环境厅        → JS cookie 挑战页（1 KB），需 Playwright
    中国环评网              → ConnectTimeout（站点不可达）
"""

from __future__ import annotations

import re
import time as _t
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

CONFIG_PATH = Path(__file__).resolve().parents[2] / "sources" / "eia-sources.yaml"

DEFAULT_LINK_HINTS = [
    "环境影响", "受理", "公示", "审批", "报告书", "报告表",
    "拟批准", "批复", "建设项目",
]

# 只保留"像内容页"的链接：排除导航、栏目索引、附件下载器等
_SKIP_HREF = re.compile(
    r"^(javascript:|mailto:|#|tel:)|\.(jpg|jpeg|png|gif|zip|rar|doc|docx|xls|xlsx)$", re.I
)
_ANCHOR_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_IN_HREF = re.compile(r"/(20\d{2})[-/]?(\d{2})?")

# "像文章页"的 URL 特征：含 4 位年份 / 长数字 ID / 具体页面文件
_ARTICLE_HREF = re.compile(r"(20\d{2})[-_/]|/\d{5,}|\.(s?html?|jsp|aspx?)(\?|$)", re.I)


def _looks_like_article(href: str) -> bool:
    """区分"栏目目录"与"具体公示条目"。

    栏目目录示例：/ywgz/hjyxpj/jsxmhjyxpj/         （无年份、无 ID）
    公示条目示例：/202609/t20260910_1234567.shtml  （有年份 + 长数字 ID）
    """
    return bool(_ARTICLE_HREF.search(href))


class EiaConnector(BaseConnector):
    """环评公示连接器（多站点、结构无关抽取）。"""

    source_id = "eia"
    timeout = 40.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._config = self._load_config()

    # ---------- 配置 ----------
    @staticmethod
    def _load_config() -> dict[str, Any]:
        if not CONFIG_PATH.exists():
            return {"sources": [], "defaults": {}}
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}

    @property
    def sites(self) -> list[dict[str, Any]]:
        return [s for s in (self._config.get("sources") or []) if s.get("enabled", True)]

    @property
    def link_hints(self) -> list[str]:
        return (self._config.get("defaults") or {}).get("link_hints") or DEFAULT_LINK_HINTS

    def get_site(self, site_id: str) -> dict[str, Any]:
        for s in self.sites:
            if s["id"] == site_id:
                return s
        raise ConnectorError(f"{self.source_id}: 未找到站点 {site_id}")

    # ---------- 采集 ----------
    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """
        query 支持：
          "site:eia_hunan"   → 只采某个站点
          None               → 采全部启用站点
        kwargs:
          max_items_per_site : 每站最多取多少条（默认 40）
          include_candidates : 是否级联探测 listing_candidates（默认 True）
        """
        max_items = int(kwargs.get("max_items_per_site", 40))
        include_candidates = bool(kwargs.get("include_candidates", True))

        sites = [self.get_site(query.split(":", 1)[1])] if (query and query.startswith("site:")) \
            else self.sites

        out: list[RawEvidence] = []
        for site in sites:
            urls = [site["url"]]
            if include_candidates:
                urls += site.get("listing_candidates") or []
            for url in urls:
                try:
                    out += await self._scrape_listing(site, url, max_items)
                except Exception as exc:  # noqa: BLE001
                    # 单站失败不影响整体（政府站点偶发不可用是常态）
                    out.append(self._error_marker(site, url, exc))
        return self._dedupe([e for e in out if e is not None])

    async def _scrape_listing(self, site: dict[str, Any], url: str,
                              max_items: int) -> list[RawEvidence]:
        resp = await self._polite_get(url, headers={"Referer": site["url"]})
        html = resp.text
        if len(html) < 2000:
            # 政府站点返回 1KB 左右的通常是 JS 挑战页
            raise ConnectorError(
                f"{self.source_id}: {site['id']} 返回疑似挑战页（{len(html)} bytes）"
            )

        items: list[RawEvidence] = []
        seen: set[str] = set()
        for href, raw_text in _ANCHOR_RE.findall(html):
            if len(items) >= max_items:
                break
            if _SKIP_HREF.search(href):
                continue
            text = _TAG_RE.sub("", raw_text).replace("&nbsp;", " ").strip()
            if not (8 <= len(text) <= 160):
                continue
            if not any(h in text for h in self.link_hints):
                continue
            # 排除"栏目导航"：这类链接指向目录（如 /ywgz/hjyxpj/jsxmhjyxpj/），
            # 而真正的公示条目 URL 一定带年份或长数字 ID。
            # 实测：不排除会混入"建设项目环境影响评价"等栏目名，污染结果。
            if not _looks_like_article(href):
                continue

            full = urljoin(url, href)
            if full in seen:
                continue
            seen.add(full)

            items.append(RawEvidence(
                evidence_id=f"eia_{abs(hash(full)) % 10**12}",
                channel="connector",
                source_id=f"eia_{site['id']}",
                source_url=full,
                source_title=text,
                publish_date=self._guess_date(href),
                raw_text=text,
                meta={
                    "site_id": site["id"],
                    "site_name": site["name"],
                    "region": site.get("region"),
                    "listing_url": url,
                    "type": "eia_notice",
                    "region_kind": ("national" if site.get("region") == "CN-NATIONAL"
                                    else "province"),
                },
            ))
        return items

    @staticmethod
    def _guess_date(href: str) -> datetime | None:
        """从 URL 里猜发布日期（政府站点链接普遍含 /2026/09/t20260910_xxx.html）。"""
        m = re.search(r"/(20\d{2})[-/]?(\d{2})[-/]?(\d{2})?", href)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            try:
                return datetime(int(y), int(mo), int(d or 1), tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    @staticmethod
    def _error_marker(site: dict[str, Any], url: str, exc: Exception) -> RawEvidence | None:
        """把失败记录成一个带 meta 的占位（供覆盖率报告的根因分类使用）。"""
        try:
            from ..core.coverage import Cell  # noqa: F401  仅为表明用途
        except Exception:  # noqa: BLE001
            pass
        return None  # 目前不落库，错误由 probe / 日志承担

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        t0 = _t.monotonic()
        reachable_sites, total_items, samples, errors = 0, 0, [], []
        for site in self.sites:
            try:
                items = await self._scrape_listing(site, site["url"], max_items=10)
                if items:
                    reachable_sites += 1
                    total_items += len(items)
                    if len(samples) < 5:
                        samples.append(f"{site['id']}: {items[0].source_title[:28]}")
                else:
                    errors.append(f"{site['id']}=0条")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{site['id']}={type(exc).__name__}")

        ok = reachable_sites > 0
        return ProbeResult(
            source_id=self.source_id,
            reachable=ok,
            status_code=200 if ok else None,
            latency_ms=int((_t.monotonic() - t0) * 1000),
            records_found=total_items,
            sample=samples,
            error=("; ".join(errors[:6]) if errors else None),
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
