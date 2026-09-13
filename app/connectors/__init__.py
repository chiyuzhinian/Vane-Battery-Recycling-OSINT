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
from .boe_es import BoeEsConnector
from .bwb_nl import BwbNlConnector
from .cninfo import CninfoConnector
from .datafair import DataFairConnector
from .dila_fr import DilaFrConnector
from .eia import EiaConnector
from .eur_lex import EurLexConnector
from .finlex_fi import FinlexFiConnector
from .gesetze_de import GesetzeDeConnector
from .isap_pl import IsapPlConnector
from .krs_ky import KrsKyConnector
from .leginfo_ca import LeginfoCaConnector
from .rcw_wa import RcwWaConnector
from .revisor_mn import RevisorMnConnector
from .sejm_eli_pl import SejmEliPlConnector
from .sfst_se import SfstSeConnector
from .us_federal import FederalRegisterConnector
from .vane import VaneConnector

REGISTRY: dict[str, Type[BaseConnector]] = {
    # ---- ⭐ 通道 A：通用搜索（未知源发现）----
    #   与下面所有「定向连接器」互补：定向回答「已知源里有什么」，
    #   Vane 回答「哪里还有我不知道的源」。未部署时可用 available() 跳过。
    "vane": VaneConnector,             # Vane /api/search（SearXNG + LLM 重排）
    # ---- 政策侧 ----
    "eur_lex": EurLexConnector,        # 欧盟一级立法（SPARQL + EUR-Lex 正文）
    "us_federal": FederalRegisterConnector,
    "de_gesetze": GesetzeDeConnector,  # ⭐ 德国联邦法律（官方 XML，成员国层）
    "nl_bwb": BwbNlConnector,          # ⭐ 荷兰国家法规（KOOP BWB 官方 XML）
    "es_boe": BoeEsConnector,          # ⭐ 西班牙立法整合库（BOE 官方 API）
    "dila_fr": DilaFrConnector,        # ⭐ 法国 DILA 开放数据（Légifrance 原始源）
    "datafair": DataFairConnector,     # ⭐ Data Fair 开放数据平台（法国 ADEME 等）
    # ---- Phase 4B-2A：成员国 pilot（官方立法库直链）----
    "se_sfst": SfstSeConnector,        # 瑞典 SFST（成员国层）
    "pl_isap": IsapPlConnector,        # 波兰 ISAP（成员国层）
    "fi_finlex": FinlexFiConnector,    # 芬兰 Finlex（成员国层）
    # ---- Phase 4B-2A：US 州 pilot ----
    "us_ca_leginfo": LeginfoCaConnector,   # 加州立法信息（法案/法典）
    "us_wa_rcw": RcwWaConnector,           # 华盛顿州 RCW 修订法典
    # ---- Phase 4B-2B0：受阻/未适配通道攻坚（Step 5）----
    "pl_sejm_eli": SejmEliPlConnector,     # 波兰 Sejm ELI 官方 API（替代被挡的 ISAP）
    "us_ky_krs": KrsKyConnector,           # 肯塔基 KRS 修订法典（statute.aspx）
    "us_mn_revisor": RevisorMnConnector,   # 明尼苏达法规（revisor cite 直链）
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
    "BoeEsConnector",
    "BwbNlConnector",
    "ConnectorBlocked",
    "ConnectorError",
    "ProbeResult",
    "RawEvidence",
    "CninfoConnector",
    "DataFairConnector",
    "DilaFrConnector",
    "EiaConnector",
    "EurLexConnector",
    "FederalRegisterConnector",
    "FinlexFiConnector",
    "GesetzeDeConnector",
    "IsapPlConnector",
    "LeginfoCaConnector",
    "RcwWaConnector",
    "SfstSeConnector",
    "VaneConnector",
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
