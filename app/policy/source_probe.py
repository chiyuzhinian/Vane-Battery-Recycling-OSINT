# -*- coding: utf-8 -*-
"""Source Probe（Phase 4B-1 Step 1）—— 真实 HTTP 探测官方端点。

纪律：
    · 探测只回答「端点是否可用/可获得 metadata 还是 fulltext/失败在哪」
    · 失败必须分类（source_access.FAILURE_TYPES），**不得**把失败写成 0 结果
    · 结果写 outputs/audit/source_probe_results.json，供矩阵脚本消费

用法（见 scripts/probe_source_endpoints.py）：
    results = asyncio.run(probe_all())
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.policy.config import EndpointCfg, RoleEndpoints, load_endpoints
from app.policy.source_access import evaluate_probe_response

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_ACCEPT = {
    "json": "application/json, text/plain, */*",
    "xml": "application/xml, text/xml, */*",
    "html": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "pdf": "*/*",
}


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def probe_endpoint(
    ep: EndpointCfg, *, role: str, default_timeout: float = 25.0,
    user_agent: str = DEFAULT_UA,
    parsers: tuple[str, ...] = ("html", "json", "xml"),
) -> dict:
    """探测单个端点 → EndpointResult dict。"""
    timeout = float(ep.probe.timeout_s or default_timeout)
    headers = {"User-Agent": user_agent,
               "Accept": _ACCEPT.get(ep.content_kind, "*/*")}
    status_code: int | None = None
    content_type = ""
    body = ""
    exc: BaseException | None = None
    attempts = 0
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            for attempt in (1, 2):      # 瞬时网络抖动重试一次（状态码失败不重试）
                attempts = attempt
                try:
                    if ep.probe.kind == "download_head":
                        try:
                            r = await client.head(ep.official_url, headers=headers)
                            if r.status_code >= 400:
                                r = await client.get(ep.official_url, headers={
                                    **headers, "Range": "bytes=0-4095"})
                        except Exception:  # noqa: BLE001 — HEAD 被拒时回退 GET（有界读取）
                            r = await client.get(ep.official_url, headers={
                                **headers, "Range": "bytes=0-4095"})
                    else:
                        r = await client.get(ep.official_url, headers=headers)
                    status_code = r.status_code
                    content_type = r.headers.get("content-type", "")
                    if ep.probe.kind != "download_head":
                        body = r.text[:200_000]
                    exc = None
                    break
                except BaseException as e:  # noqa: BLE001 — 探测必须容错
                    exc = e
                    if attempt == 1:
                        await asyncio.sleep(1.0)
    except BaseException as e:  # noqa: BLE001 — 客户端构造失败等
        exc = e
    latency_ms = int((time.monotonic() - t0) * 1000)

    res = evaluate_probe_response(
        source_role=role, endpoint_id=ep.id, official_url=ep.official_url,
        checked_at=_checked_at(), status_code=status_code,
        content_type=content_type, body=body, latency_ms=latency_ms,
        exception=exc,
        capabilities=ep.capabilities.model_dump(),
        content_kind=ep.content_kind, parsers=parsers,
        expect_keys=list(ep.probe.expect_keys)
        if ep.probe.kind == "json_api" else None,
        payload_empty_for=(ep.probe.no_results_key or None),
        metadata_source_type=ep.metadata_source_type,
        detect_spa=bool(ep.probe.detect_spa),
    )
    d = res.as_dict()
    d["probe_kind"] = ep.probe.kind
    d["role_method"] = ep.role_method
    d["notes"] = ep.notes
    d["attempts"] = attempts
    if exc is not None and not d["failure_detail"]:
        d["failure_detail"] = f"{type(exc).__name__}: {exc!r}"
    return d


async def probe_all(
    *, only_roles: set[str] | None = None, default_timeout: float = 25.0,
    user_agent: str = DEFAULT_UA, concurrency: int = 6,
) -> list[dict]:
    """探测配置中的全部（或指定）角色端点。"""
    cfg = load_endpoints()
    parsers = tuple(cfg.defaults.get("parsers") or ("html", "json", "xml"))
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict] = []

    async def one(role: RoleEndpoints, ep: EndpointCfg) -> None:
        async with sem:
            results.append(await probe_endpoint(
                ep, role=role.role, default_timeout=default_timeout,
                user_agent=user_agent, parsers=parsers))

    tasks = [one(role, ep) for role in cfg.roles
             if not only_roles or role.role in only_roles
             for ep in role.endpoints]
    if tasks:
        await asyncio.gather(*tasks)
    results.sort(key=lambda r: (r["source_role"], r["endpoint_id"]))
    return results
