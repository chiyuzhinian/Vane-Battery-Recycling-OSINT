"""Vane 通用搜索连接器 —— **通道 A**（对话式检索 / 未知源发现）。

定位（与通道 B 的分工）
-----------------------
    通道 B（定向连接器）  回答「**已知源**里有什么」—— 官方 API/XML 直采，产能主力
    通道 A（本连接器）    回答「**哪里还有我不知道的源**」—— SearXNG 多引擎 + LLM 重排

    两者**互补而非替代**。B 的产出是结构化记录（可直接判定入库），
    A 的产出是「答案 + 引用来源」，价值在于**发现 B 覆盖不到的源**。

⭐ 这是 `RawEvidence.channel` 里那个预留位的真正实现。
   （2026-09-11 之前，`"vane"` 在全仓库 `app/` 内只出现在 `base.py` 的一行注释中，
     2,741 条已采记录里 `channel="vane"` 为 **0 条**。）

部署前提
--------
官方镜像**自带 SearXNG**（`The image includes both Vane and SearxNG`），一条命令：

    docker run -d -p 3000:3000 -v vane-data:/home/vane/data --name vane \
        itzcrazykns1337/vane:latest

⚠️ 两点注意：
  1. 需要 Docker 守护进程在运行
  2. 首次访问 http://localhost:3000 要在 setup 界面**填 LLM API Key**
     （OpenAI / Anthropic / Gemini / Groq / 本地 Ollama 均可）
  3. 国内拉取需走可用镜像源，`~/.docker/daemon.json` 里老牌加速器多已失效

API 契约（官方 `docs/API/SEARCH.md`）
------------------------------------
    GET  /api/providers  → {"providers": [{id, name, chatModels:[{key}], embeddingModels:[{key}]}]}
    POST /api/search     → {"message": "...", "sources": [{content, metadata:{title, url}}]}
                           body 必填: chatModel{providerId,key} / embeddingModel{...} /
                                      sources[] / query

用法
----
    async with get_connector("vane") as c:
        if await c.available():        # 未部署时不要炸掉整条管线
            items = await c.fetch("EU black mass cross-border shipment rules")
"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

# Vane 的 sources 只支持这三种（官方文档明确列出）
VALID_SOURCES = ("web", "academic", "discussions")
# optimizationMode: speed / balanced / quality
VALID_MODES = ("speed", "balanced", "quality")


class VaneConnector(BaseConnector):
    """Vane `/api/search` —— 通用搜索通道（通道 A）。"""

    source_id = "vane"
    timeout = 120.0      # LLM 合成答案比纯搜索慢得多，默认 30s 不够

    def __init__(self, client: Any = None) -> None:
        super().__init__(client)
        # 允许环境变量覆盖（部署在别的机器/端口时）
        self.base_url = os.environ.get("VANE_URL", "http://localhost:3000").rstrip("/")
        self._models: tuple[dict, dict] | None = None

    # ---------------------------------------------------------------- 可用性
    async def available(self) -> bool:
        """Vane 是否在运行。

        ⭐ 单独提供这个方法，是因为**通道 A 是可选通道**：
           没部署 Vane 时，主管线应当**安静地跳过**它，而不是抛异常。
        """
        try:
            await self._polite_get(f"{self.base_url}/api/providers")
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _resolve_models(self) -> tuple[dict, dict]:
        """从 `/api/providers` 取第一个可用的 chat + embedding 模型。

        ⚠️ Vane 要求**显式**传 `providerId` + `key`，不能省略。
           这里取"第一个可用模型"作为默认；需要指定模型时，
           直接构造 payload 调 `search_raw()`。
        """
        if self._models:
            return self._models
        try:
            resp = await self._polite_get(f"{self.base_url}/api/providers")
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(
                f"vane: 无法连接 {self.base_url}（{type(exc).__name__}）。"
                f"请确认容器在运行：docker ps | findstr vane") from exc

        chat = embedding = None
        for p in data.get("providers") or []:
            if chat is None and p.get("chatModels"):
                chat = {"providerId": p["id"], "key": p["chatModels"][0]["key"]}
            if embedding is None and p.get("embeddingModels"):
                embedding = {"providerId": p["id"], "key": p["embeddingModels"][0]["key"]}
        if not chat or not embedding:
            raise ConnectorError(
                "vane: 尚未配置模型。请打开 http://localhost:3000 完成 setup"
                "（填入 LLM API Key；本地模型可用 Ollama）")
        self._models = (chat, embedding)
        return self._models

    # ---------------------------------------------------------------- 搜索
    async def search_raw(self, query: str, chat: dict, embedding: dict,
                         sources: tuple[str, ...] = ("web",),
                         optimization: str = "speed",
                         system: str | None = None) -> dict:
        """最底层调用：直接用指定模型搜索，返回原始 JSON。

        需要精细控制（指定模型 / 传 history / 流式）时走这里。
        """
        bad = [s for s in sources if s not in VALID_SOURCES]
        if bad:
            raise ConnectorError(f"vane: 非法 sources {bad}，可选 {VALID_SOURCES}")
        if optimization not in VALID_MODES:
            raise ConnectorError(f"vane: 非法 optimizationMode {optimization!r}")
        payload: dict[str, Any] = {
            "chatModel": chat,
            "embeddingModel": embedding,
            "optimizationMode": optimization,
            "sources": list(sources),
            "query": query,
            "stream": False,
        }
        if system:
            payload["systemInstructions"] = system
        resp = await self._polite_get(f"{self.base_url}/api/search",
                                      method="POST", json=payload)
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(f"vane: /api/search 返回非 JSON（{type(exc).__name__}）") from exc

    async def fetch(self, query: str | None = None, *,
                    sources: tuple[str, ...] = ("web",),
                    optimization: str = "speed",
                    system: str | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        """一次 Vane 查询 → 若干 `RawEvidence`（**每个引用来源一条**）。

        ⭐ 关键设计：**不把 LLM 答案当证据**。
           `message` 是"给人看的线索"，`sources` 才是可入库、可判定的证据。
           答案存进每条记录的 `meta["vane_answer"]`，用于人工回溯
           「当初为什么认为这条相关」——这符合本项目的可追溯要求。
        """
        if not query:
            raise ConnectorError("vane: 必须提供 query")
        chat, embedding = await self._resolve_models()
        data = await self.search_raw(query, chat, embedding,
                                     sources=sources, optimization=optimization,
                                     system=system)
        answer = (data.get("message") or "")[:600]
        out: list[RawEvidence] = []
        for src in data.get("sources") or []:
            md = src.get("metadata") or {}
            url = (md.get("url") or "").strip()
            if not url:
                continue
            out.append(RawEvidence(
                evidence_id="",
                channel="vane",                 # ⭐ 数据模型里的预留位，终于有了产出
                source_id=self.source_id,
                source_url=url,
                source_title=md.get("title") or url,
                publish_date=None,              # Vane 不返回发布日期；由标题正则兜底
                raw_text=(src.get("content") or "")[:4000],
                meta={
                    "region_hint": "GLOBAL",
                    "query": query,
                    "vane_answer": answer,
                    "sources_used": list(sources),
                    "optimization": optimization,
                    "channel_note": "Vane 通用搜索（SearXNG 多引擎 + LLM 语义重排）",
                },
            ))
        return out

    # ---------------------------------------------------------------- 探测
    async def probe(self) -> ProbeResult:
        """回答"Vane 通道能不能用"。未部署时给**明确可操作的提示**。"""
        t0 = time.monotonic()
        try:
            await self._polite_get(f"{self.base_url}/api/providers")
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"{type(exc).__name__} — Vane 未运行？({self.base_url}) "
                      f"启动：docker run -d -p 3000:3000 --name vane "
                      f"itzcrazykns1337/vane:latest")
        try:
            chat, emb = await self._resolve_models()
            models = f"{chat['key']} / {emb['key']}"
        except ConnectorError as exc:
            return ProbeResult(
                source_id=self.source_id, reachable=True, status_code=200,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=str(exc))
        return ProbeResult(
            source_id=self.source_id, reachable=True, status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
            sample=[f"{self.base_url} (models: {models})"])
