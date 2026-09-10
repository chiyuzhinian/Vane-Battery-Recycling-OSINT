"""连接器基类 —— 所有定向源直采（通道 B）的统一契约。

设计要点
--------
1. 每个连接器只负责"把源站数据取回来并解析成 RawEvidence"，**不做验证**。
   （验证是 app/engines/validator.py 的职责，见 04 篇 §2.4）
2. 所有连接器必须实现 `probe()` —— 用于回答"这个源到底能不能搜到"。
3. 网络失败一律抛 `ConnectorError`，由调度层决定重试（见 04 篇 §4.2）。
4. 遵守采集礼仪：单域名限速、可识别 User-Agent、尊重 robots.txt。

实测备注（2026-09-10，见 ARCHITECTURE.md §7）
--------------------------------------------
- eur-lex.europa.eu 的 HTML 正文层返回 202 挑战页 → 欧盟侧改走 SPARQL
- echa.europa.eu 返回 403 → 标记 blocked，不写连接器
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

USER_AGENT = "BatteryRecyclingOSINT/1.0 (+research; contact: chiyuzhinian)"

# 单域名限速（秒/请求），与 04 篇 §4.2 RATE_LIMITS 对应
RATE_LIMITS: dict[str, float] = {
    "eur-lex.europa.eu": 3.0,
    "publications.europa.eu": 2.0,
    "environment.ec.europa.eu": 3.0,
    "federalregister.gov": 1.0,
    "www.federalregister.gov": 1.0,
    "cninfo.com.cn": 2.0,
    "epa.gov": 3.0,
    "energy.gov": 3.0,
}

_last_call: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


class ConnectorError(RuntimeError):
    """连接器不可恢复错误（4xx 等）。"""


class ConnectorBlocked(ConnectorError):
    """源站反爬拦截（202/403/429 挑战页）。"""


@dataclass
class RawEvidence:
    """统一证据模型 —— 三条通道归一化成同一个结构（见 04 篇 §2.2）。"""

    evidence_id: str
    channel: str                       # "connector" | "vane" | "manual"
    source_id: str
    source_url: str | None
    source_title: str | None
    publish_date: datetime | None
    raw_text: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    query_id: str | None = None
    company_hint: str | None = None
    dimension_hint: str | None = None
    raw_snapshot_key: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha1(self.raw_text.encode("utf-8", "ignore")).hexdigest()

    def __post_init__(self) -> None:
        if not self.evidence_id:
            seed = f"{self.source_id}|{self.source_url}|{self.source_title}"
            self.evidence_id = hashlib.sha1(seed.encode()).hexdigest()[:16]


@dataclass
class ProbeResult:
    """`probe()` 的返回 —— 直接回答"能不能搜到"。"""

    source_id: str
    reachable: bool
    status_code: int | None
    latency_ms: int
    records_found: int
    blocked: bool = False
    error: str | None = None
    sample: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        flag = "✅" if self.reachable and not self.blocked else ("🚫" if self.blocked else "❌")
        return (f"{flag} {self.source_id}: HTTP {self.status_code} "
                f"{self.latency_ms}ms 命中 {self.records_found} 条"
                + (f" [{self.error}]" if self.error else ""))


class BaseConnector(ABC):
    """定向源连接器基类。

    子类需要实现：
      - source_id      : 与 sources/*.yaml 中一致
      - async fetch()  : 拉取并解析
      - async probe()  : 存活与命中数探测
    """

    source_id: str = "base"
    base_url: str = ""
    timeout: float = 30.0

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    # ---------- HTTP ----------
    async def _polite_get(self, url: str, **kwargs: Any) -> httpx.Response:
        """带单域名限速 + 抖动的 GET，避免把源站打挂。"""
        host = httpx.URL(url).host or ""
        interval = RATE_LIMITS.get(host, 1.0)
        lock = _locks.setdefault(host, asyncio.Lock())
        async with lock:
            elapsed = time.monotonic() - _last_call.get(host, 0.0)
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed + random.uniform(0, 0.3))
            try:
                resp = await self._client.get(url, **kwargs)
            finally:
                _last_call[host] = time.monotonic()

        if resp.status_code in (202, 403, 429):
            # 202 = 挑战页；403/429 = 拦截或限流。实测 EUR-Lex 返回 202。
            raise ConnectorBlocked(
                f"{self.source_id}: 源站拦截 HTTP {resp.status_code} ({url})"
            )
        if resp.status_code >= 400:
            raise ConnectorError(f"{self.source_id}: HTTP {resp.status_code} ({url})")
        return resp

    # ---------- 子类契约 ----------
    @abstractmethod
    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """拉取证据。query 语义由子类定义（关键词 / CELEX / 机构 slug）。"""

    @abstractmethod
    async def probe(self) -> ProbeResult:
        """探测：源站可达？被拦？能命中多少条？"""

    # ---------- 生命周期 ----------
    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def __aenter__(self) -> "BaseConnector":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


# ---------- 通用工具 ----------
def parse_date(value: Any) -> datetime | None:
    """宽容解析日期（ISO / 英文月份 / 中文）。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y年%m月%d日", "%B %d, %Y"):
        try:
            return datetime.strptime(text[: len(fmt) + 4], fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
