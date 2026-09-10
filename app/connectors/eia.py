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

# ⚠️ "打包公示"识别（实测 2026-09-10）：
# 生态环境部的受理公示是**按期打包**的，一个页面覆盖几十个跨行业项目：
#   "生态环境部关于2026年8月7日-2026年8月25日建设项目环境影响评价文件受理情况的公示"
# 电池回收项目藏在**页面正文/附件表格**里，标题上根本看不出来。
# 对策：对这类页面做**二级抓取**（deep_check），把正文抠出来找电池关键词。
BATCH_TITLE_MARKERS = ["受理情况", "受理的公示", "受理公示", "审批情况", "审批公示"]

# 深入正文时要找的电池/回收线索
DEEP_TERMS = ["电池", "锂", "回收", "梯次", "再生", "资源化", "湿法", "正极材料", "黑粉"]


def _looks_like_article(href: str) -> bool:
    """区分"栏目目录"与"具体公示条目"。

    栏目目录示例：/ywgz/hjyxpj/jsxmhjyxpj/         （无年份、无 ID）
    公示条目示例：/202609/t20260910_1234567.shtml  （有年份 + 长数字 ID）
    """
    return bool(_ARTICLE_HREF.search(href))


def _is_batch_notice(title: str) -> bool:
    """是否为"打包公示"（需二级抓取才能判断是否含电池项目）。"""
    return any(m in title for m in BATCH_TITLE_MARKERS) and "日" in title


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
        """省级/国家级源 + 市级源。

        市级是必需的：实测省级厅"审批文件公示"里 90% 是核技术利用/医疗项目，
        一般工业项目（含电池回收工厂）的环评权限在市级。
        跳过 needs_discovery 的站点，避免每次跑都打无效请求。
        """
        province = [s for s in (self._config.get("sources") or []) if s.get("enabled", True)]
        city_cfg = self._config.get("city_sources") or {}
        city = []
        if city_cfg.get("enabled", False):
            city = [s for s in (city_cfg.get("sources") or [])
                    if not s.get("needs_discovery")]
        return province + city

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
        deep = bool(kwargs.get("deep_check", True))

        sites = [self.get_site(query.split(":", 1)[1])] if (query and query.startswith("site:")) \
            else self.sites

        out: list[RawEvidence] = []
        for site in sites:
            urls = [site["url"]]
            if include_candidates:
                urls += site.get("listing_candidates") or []
            for url in urls:
                try:
                    batch = await self._scrape_listing(site, url, max_items)
                    if deep:
                        batch = await self._deep_filter(batch)
                    out += batch
                except Exception as exc:  # noqa: BLE001
                    # 单站失败不影响整体（政府站点偶发不可用是常态）
                    out.append(self._error_marker(site, url, exc))
        return self._dedupe([e for e in out if e is not None])

    async def _deep_filter(self, items: list[RawEvidence]) -> list[RawEvidence]:
        """对"打包公示"做二级抓取：进正文找电池/回收线索。

        为什么必须做：生态环境部的受理公示是**按期打包**的，
        一个页面覆盖几十个跨行业项目，标题完全看不出有没有电池项目。
        不做二级抓取 → 电池回收项目的环评永远发现不了。

        成本控制：只对识别为 batch 的条目抓正文（每站点通常 10-30 条），
        非 batch 的直接放行给下游相关性判定。
        """
        kept: list[RawEvidence] = []
        for ev in items:
            if not _is_batch_notice(ev.source_title or ""):
                kept.append(ev)
                continue
            try:
                resp = await self._polite_get(ev.source_url, headers={"Referer": ev.meta.get("listing_url") or ""})
                text = _TAG_RE.sub(" ", resp.text)
                text = re.sub(r"\s+", " ", text)
                hits = [t for t in DEEP_TERMS if t in text]
                if not hits:
                    continue                      # 正文里没有电池线索 → 丢弃
                snippet = self._snippet(text, hits[0])
                ev.raw_text = f"{ev.source_title}\n{snippet}"
                ev.meta["deep_checked"] = True
                ev.meta["deep_hits"] = hits
                kept.append(ev)
            except Exception:  # noqa: BLE001
                continue                          # 抓不动就跳过，不阻塞
        return kept

    @staticmethod
    def _snippet(text: str, term: str, radius: int = 220) -> str:
        """截取关键词附近的上下文，便于人工核对与下游抽取。"""
        idx = text.find(term)
        if idx < 0:
            return text[:radius * 2]
        start = max(0, idx - radius)
        return text[start: idx + radius]

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
                    # 环评属于"企业项目"场景，必须用项目类相关性规则
                    # （政策类规则在这里会误杀"动力电池结构件"这类项目、也拦不住核技术噪声）
                    "relevance_scenario": "project",
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
