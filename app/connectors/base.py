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
import json
import random
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

USER_AGENT = "BatteryRecyclingOSINT/1.0 (+research; contact: chiyuzhinian)"

# 浏览器 UA —— 部分站点（如 recellcenter.org）仅对浏览器 UA 放行
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ⚠️ 实测（2026-09-10）：以下站点 Python(OpenSSL) 连不上，但 curl 完全正常。
#    原因是这些站点使用了非标准 EC 曲线或 TLS 记录行为，OpenSSL 会抛
#    `bad ecpoint` / `DECRYPTION_FAILED_OR_BAD_RECORD_MAC`。
#    curl.exe 在 Windows 上走 SChannel，不受影响 —— 因此需要 curl 回退。
TLS_QUIRK_HOSTS = {
    "gxt.hunan.gov.cn",
    "ec.europa.eu",
}

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
    # 荷兰 KOOP：SRU 检索服务偶发 SSL 握手失败，放慢并靠 curl 回退
    "zoekservice.overheid.nl": 2.0,
    "repository.officiele-overheidspublicaties.nl": 1.5,
}

_last_call: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


class ConnectorError(RuntimeError):
    """连接器不可恢复错误（4xx 等）。"""


class ConnectorBlocked(ConnectorError):
    """源站反爬拦截（202/403/429 挑战页）。"""


@dataclass
class SimpleResponse:
    """与 httpx.Response 兼容的最小响应对象。

    之所以自建：curl 回退路径拿不到 httpx.Response，但连接器只用到
    status_code / text / content / json() 这几个成员，自建一个更干净。
    """

    status_code: int
    content: bytes
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)


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
    async def _polite_get(self, url: str, method: str = "GET", **kwargs: Any) -> SimpleResponse:
        """带单域名限速 + 抖动的请求；遇 TLS 兼容问题自动回退到 curl。

        策略链：
          1. httpx（默认 UA）
          2. 若该站已知有 TLS 兼容问题，或 httpx 抛 SSL/传输错误 → curl.exe 回退
          3. 回退时使用浏览器 UA（部分站点只对浏览器 UA 放行）

        支持 method="POST" + data=（巨潮的公告查询接口即 POST 表单）。

        限速是"有礼貌采集"的底线：宁可慢，不能把对方站点打挂。
        """
        host = httpx.URL(url).host or ""
        interval = RATE_LIMITS.get(host, 1.0)
        lock = _locks.setdefault(host, asyncio.Lock())

        async with lock:
            elapsed = time.monotonic() - _last_call.get(host, 0.0)
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed + random.uniform(0, 0.3))
            try:
                resp = await self._try_httpx(url, method, kwargs)
            except (httpx.TransportError, httpx.HTTPError) as exc:
                resp = await self._try_curl(url, method, kwargs, reason=str(exc))
            finally:
                _last_call[host] = time.monotonic()

            if resp is None:
                raise ConnectorError(f"{self.source_id}: httpx 与 curl 均失败 ({url})")

        if resp.status_code in (202, 403, 429):
            # 202 = 挑战页；403/429 = 拦截或限流。实测 EUR-Lex 返回 202。
            raise ConnectorBlocked(
                f"{self.source_id}: 源站拦截 HTTP {resp.status_code} ({url})"
            )
        if resp.status_code >= 400:
            # ⚠️ **必须带上响应体**。400 的原因（SPARQL 语法错、Virtuoso 规划
            #    失败、参数被拒）**全在 body 里**。只报一句 "HTTP 400" 等于
            #    把唯一线索丢掉 —— 实测就是因此让「批次 2/4/5/8/9 反复失败」
            #    悬了很久，最后只能靠单独写探针脚本才看出是 400 而非超时。
            body = ""
            try:
                body = resp.content[:400].decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 —— 诊断信息不能反过来搞崩请求
                pass
            raise ConnectorError(
                f"{self.source_id}: HTTP {resp.status_code} ({url})"
                + (f" :: {body}" if body else "")
            )
        return resp

    async def _try_httpx(self, url: str, method: str,
                         kwargs: dict[str, Any]) -> SimpleResponse | None:
        if httpx.URL(url).host in TLS_QUIRK_HOSTS:
            return None          # 已知不兼容，直接走 curl，省一次失败往返
        resp = await self._client.request(method, url, **kwargs)
        return SimpleResponse(
            status_code=resp.status_code,
            content=resp.content,
            url=str(resp.url),
            headers=dict(resp.headers),
        )

    async def _try_curl(self, url: str, method: str, kwargs: dict[str, Any],
                        reason: str = "") -> SimpleResponse | None:
        """curl 回退。Windows 上 curl 走 SChannel，可绕过 OpenSSL 的 EC 曲线限制。"""
        exe = shutil.which("curl") or shutil.which("curl.exe")
        if not exe:
            return None

        # 复用限速节奏，保持"有礼貌"
        await asyncio.sleep(RATE_LIMITS.get(httpx.URL(url).host or "", 1.0))

        cmd = [exe, "-s", "-L", "--max-time", str(int(self.timeout)),
               "-A", BROWSER_UA,
               "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8"]

        for k, v in (kwargs.get("headers") or {}).items():
            cmd += ["-H", f"{k}: {v}"]

        if method.upper() == "POST":
            from urllib.parse import urlencode
            data = kwargs.get("data") or {}
            pairs = data.items() if isinstance(data, dict) else data
            cmd += ["-X", "POST",
                    "-H", "Content-Type: application/x-www-form-urlencoded",
                    "--data", urlencode(list(pairs), doseq=True)]

        params = kwargs.get("params")
        if params:
            from urllib.parse import urlencode
            pairs = params.items() if isinstance(params, dict) else params
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(list(pairs), doseq=True)}"

        cmd += ["-w", "\n__HTTP__%{http_code}", url]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return None

        marker = b"\n__HTTP__"
        body, _, code = out.rpartition(marker)
        try:
            status = int(code.strip().decode() or 0)
        except ValueError:
            return None
        if status == 0 and not body:      # curl 000 = 连不上
            return None
        return SimpleResponse(status_code=status, content=body, url=url)

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
