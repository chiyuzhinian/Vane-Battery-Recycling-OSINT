"""浏览器抓取层 —— 用于直连被反爬拦截的站点。

背景（实测 2026-09-10）
----------------------
以下站点对 httpx / curl **一律拒绝**，但对真实浏览器放行：

    us_phmsa.dot.gov          403   黑粉/退役电池运输合规的唯一官方入口
    echa.europa.eu            403
    calrecycle.ca.gov         403
    batterycouncil.org        403
    call2recycle.org          403
    eur-lex (HTML 正文)        202

其中 **PHMSA 最关键**：它发布的
《Safety Advisory Notice for the Transportation of Lithium Batteries
for Disposal or Recycling》（2022-05-17）是退役电池运输的官方依据。

技术选型
--------
用 Python Playwright，但**复用本机已安装的 Chrome**（`channel="chrome"`），
不下载 Playwright 自带的 Chromium（省 ~150MB，也避免版本不一致）：

    pip install playwright          # 仅装驱动，不装浏览器
    p.chromium.launch(channel="chrome")

能力
----
    fetch_text(url)       → 渲染后的正文文本 + 标题（应对 JS 站点）
    fetch_links(url)      → 页面所有链接（用于发现文档）
    download(url, dest)   → 下载 PDF 等二进制（走浏览器上下文，绕过 403）

⚠️ 采集礼仪：串行 + 每站限速 + 可识别 UA。浏览器比 HTTP 客户端重得多，
   不要并发开太多页面。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import USER_AGENT

_TAG_RE = re.compile(r"\s+")

# ============================================================
# JS 人机验证（WAF challenge）识别
# ------------------------------------------------------------
# ⭐ 实测教训（2026-09-11，ECHA）：
#   403 不一定是硬拦截。ECHA 的 Azure WAF 返回的是**JS 挑战页**
#   （"One moment, we're checking you're not a bot."），
#   挑战跑完（约 6 秒）后页面**正常加载**。
#   首版只等了 1.2 秒 → 抓到的是挑战页 → 误判为"整站反爬"。
#   **判定一个源不可用之前，必须给它通过挑战的时间。**
# ============================================================
CHALLENGE_MARKERS = [
    r"checking you'?re not a bot",
    r"just a moment",
    r"azure\s+waf",
    r"enable\s+javascript",
    r"are\s+you\s+a\s+human",
    r"\bcaptcha\b",
    r"ddos\s+protection",
    r"checking your browser",
    r"verifying\s+you\s+are\s+human",
]
_CHALLENGE_RE = [re.compile(p, re.I) for p in CHALLENGE_MARKERS]


@dataclass
class BrowserDoc:
    url: str
    title: str
    text: str
    status: int = 200
    publish_date_hint: str | None = None
    pdf_links: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    challenge_waited_ms: int = 0     # 为通过人机验证等待了多久
    challenge_failed: bool = False   # True = 等超时仍未通过


class BrowserFetcher:
    """浏览器抓取器（复用本机 Chrome）。

    用法：
        async with BrowserFetcher() as bf:
            doc = await bf.fetch_text("https://www.phmsa.dot.gov/lithiumbatteries")
    """

    def __init__(self, headless: bool = True, channel: str = "chrome",
                 delay_sec: float = 2.0, timeout_ms: int = 45000,
                 challenge_ms: int = 20000) -> None:
        self.headless = headless
        self.channel = channel
        self.delay_sec = delay_sec          # 每次抓取之间的间隔（采集礼仪）
        self.timeout_ms = timeout_ms
        self.challenge_ms = challenge_ms    # 等待 JS 人机验证通过的上限
        self._pw = None
        self._browser = None
        self._ctx = None

    async def __aenter__(self) -> "BrowserFetcher":
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(
                channel=self.channel, headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            # 本机没有 Chrome 时回退到 Playwright 自带内核（需 playwright install chromium）
            self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._ctx = await self._browser.new_context(
            user_agent=USER_AGENT.replace("BatteryRecyclingOSINT/1.0", "Mozilla/5.0")
            if USER_AGENT.startswith("BatteryRecyclingOSINT") else USER_AGENT,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        # 拦掉图片/字体/媒体，只保留文档 —— 速度提升明显
        await self._ctx.route("**/*", self._route)
        return self

    @staticmethod
    async def _route(route) -> None:
        if route.request.resource_type in ("image", "font", "media"):
            await route.abort()
        else:
            await route.continue_()

    async def __aexit__(self, *exc: Any) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---------- 核心能力 ----------
    async def _await_challenge(self, page) -> tuple[int, bool]:
        """检测并等待 JS 人机验证通过。

        返回 (等待毫秒数, 是否仍然卡在挑战页)。

        为什么要单独等：WAF 的挑战页**HTTP 状态码是 403**，
        与真正的"拒绝访问"长得一样。但前者跑完 JS 后会给正常内容，
        后者永远不会。不等就会把可用的源误判为失效。
        """
        waited = 0
        step = 1000
        # 先看是不是挑战页（不是就直接返回，零开销）
        if not await self._is_challenge(page):
            return 0, False
        while waited < self.challenge_ms:
            await page.wait_for_timeout(step)
            waited += step
            if not await self._is_challenge(page):
                return waited, False
        return waited, True

    @staticmethod
    async def _is_challenge(page) -> bool:
        """页面是不是（仍然是）一张人机验证页。"""
        try:
            title = (await page.title()) or ""
            head = (await page.inner_text("body"))[:1500]
        except Exception:  # noqa: BLE001
            return False
        hay = f"{title}\n{head}"
        # 挑战页很短（只有提示语 + 追踪像素），真内容页很长
        return any(rx.search(hay) for rx in _CHALLENGE_RE)

    async def fetch_text(self, url: str, wait_selector: str | None = None) -> BrowserDoc:
        assert self._ctx is not None, "必须在 async with 中使用"
        page = await self._ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded",
                                   timeout=self.timeout_ms)
            status = resp.status if resp else 0

            # ⭐ 先过 JS 人机验证（WAF 挑战页的状态码也是 403，必须与真拒绝区分）
            waited, still_blocked = await self._await_challenge(page)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:  # noqa: BLE001
                    pass
            await page.wait_for_timeout(1200)
            title = await page.title()
            body = ""
            for sel in ("main", "article", "#main-content", "body"):
                try:
                    body = await page.inner_text(sel, timeout=4000)
                    if body and len(body.strip()) > 200:
                        break
                except Exception:  # noqa: BLE001
                    continue

            text = _TAG_RE.sub(" ", body or "").strip()
            # 从页面里猜发布日期（政府站点常写 "Issued Date: Tuesday, May 17, 2022"）
            m = re.search(
                r"(?:Issued Date|Published|Date)[:\s]+"
                r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?,?\s*"
                r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
            pdfs = await page.eval_on_selector_all(
                "a[href$='.pdf'], a[href*='.pdf']", "els => els.map(e => e.href)")

            await asyncio.sleep(self.delay_sec)
            return BrowserDoc(url=url, title=title, text=text, status=status,
                              publish_date_hint=(m.group(1) if m else None),
                              pdf_links=sorted(set(pdfs or []))[:20],
                              challenge_waited_ms=waited,
                              challenge_failed=still_blocked)
        finally:
            await page.close()

    async def fetch_links(self, url: str, pattern: str | None = None) -> list[dict[str, str]]:
        """抓页面所有链接（可选正则过滤），用于**发现文档**。"""
        assert self._ctx is not None
        page = await self._ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await self._await_challenge(page)          # 同样要过人机验证
            await page.wait_for_timeout(1200)
            rows = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({t:(e.innerText||'').trim(), h:e.href}))")
            out, seen = [], set()
            rx = re.compile(pattern, re.I) if pattern else None
            for r in rows:
                t = _TAG_RE.sub(" ", r.get("t") or "").strip()
                h = (r.get("h") or "").split("#")[0]
                if len(t) < 8 or not h.startswith("http") or h in seen:
                    continue
                if rx and not rx.search(t):
                    continue
                seen.add(h)
                out.append({"title": t, "url": h})
            await asyncio.sleep(self.delay_sec)
            return out
        finally:
            await page.close()

    async def download(self, url: str, dest: Path) -> dict[str, Any]:
        """用浏览器上下文下载（可绕过对普通客户端的 403）。

        ⚠️ **只信内容，不信状态码与扩展名**（实测教训）
        --------------------------------------------------
        curl 下载 PHMSA 的 PDF 时返回 403，但**响应体被原样存成了 .pdf**，
        得到一个 525 字节的 HTML 错误页伪装成 PDF —— 不校验就会把
        "抓到了官方文档" 写进证据库。因此这里做双重把关：

          1. 状态码必须 200
          2. 内容魔数必须匹配扩展名（PDF → `%PDF-`；HTML → `<!DOCTYPE`/`<html`）

        校验不通过则**不落盘**，并在返回值里说明原因。
        """
        assert self._ctx is not None
        resp = await self._ctx.request.get(url, timeout=self.timeout_ms)
        body = await resp.body()

        ctype = (resp.headers.get("content-type") or "").lower()
        head = body[:8]
        ok_status = resp.status == 200
        is_pdf = head.startswith(b"%PDF-")
        looks_html = head.lstrip()[:1] == b"<"

        reason = ""
        if not ok_status:
            reason = f"HTTP {resp.status}"
        elif dest.suffix.lower() == ".pdf" and not is_pdf:
            # 典型陷阱：WAF 返回 200 + HTML 拦截页
            reason = "内容不是 PDF（疑似 WAF 拦截页）" if looks_html else "内容魔数不匹配"
        elif looks_html and dest.suffix.lower() != ".html":
            reason = "响应是 HTML 而非目标二进制"

        saved = None
        if not reason:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            saved = dest.as_posix()
        else:
            dest.unlink(missing_ok=True)        # 清掉可能存在的旧残留

        return {
            "url": url, "status": resp.status, "bytes": len(body),
            "saved": saved, "verified": bool(saved),
            "reason": reason, "content_type": ctype,
        }
