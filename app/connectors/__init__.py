"""连接器注册中心。

新增连接器时：
  1. 新建 app/connectors/<name>.py，继承 BaseConnector
  2. 在下面的 REGISTRY 中登记
  3. 在 sources/*.yaml 中把对应 source 的 connector 字段改成 <key>
  4. 跑 scripts/verify-sources.ps1 确认能搜到
"""

from __future__ import annotations

import asyncio
from typing import Type

from .base import (
    RATE_LIMITS,
    USER_AGENT,
    BaseConnector,
    ConnectorBlocked,
    ConnectorError,
    ProbeResult,
    RawEvidence,
)
from .cninfo import CninfoConnector
from .datafair import DataFairConnector
from .eia import EiaConnector
from .eur_lex import EurLexConnector
from .gesetze_de import GesetzeDeConnector
from .us_federal import FederalRegisterConnector

REGISTRY: dict[str, Type[BaseConnector]] = {
    # ---- 政策侧 ----
    "eur_lex": EurLexConnector,        # 欧盟一级立法（SPARQL）
    "us_federal": FederalRegisterConnector,
    "de_gesetze": GesetzeDeConnector,  # ⭐ 德国联邦法律（官方 XML，成员国层）
    "datafair": DataFairConnector,     # ⭐ Data Fair 开放数据平台（法国 ADEME 等）
    # ---- 企业侧 ----
    "cninfo": CninfoConnector,      # 上市公司公告 / 年报（13 家上市系企业）
    "eia": EiaConnector,            # 环评公示（非上市企业的唯一产能来源）
    # 待实现（见 04 篇 §7.1）：
    # "bidding": BiddingConnector,  # 招投标
    # "patent":  PatentConnector,   # 专利
}

__all__ = [
    "REGISTRY",
    "RATE_LIMITS",
    "USER_AGENT",
    "BaseConnector",
    "ConnectorBlocked",
    "ConnectorError",
    "ProbeResult",
    "RawEvidence",
    "CninfoConnector",
    "DataFairConnector",
    "EiaConnector",
    "EurLexConnector",
    "FederalRegisterConnector",
    "GesetzeDeConnector",
    "get_connector",
    "probe_all",
]


def get_connector(key: str) -> BaseConnector:
    cls = REGISTRY.get(key)
    if cls is None:
        raise ConnectorError(f"未注册的连接器: {key}")
    return cls()


async def probe_all(keys: list[str] | None = None) -> list[ProbeResult]:
    """并发探测所有连接器，直接回答"能不能搜到"。"""
    targets = keys or list(REGISTRY)
    connectors = [get_connector(k) for k in targets]
    try:
        return await asyncio.gather(*(c.probe() for c in connectors))
    finally:
        await asyncio.gather(*(c.aclose() for c in connectors), return_exceptions=True)
