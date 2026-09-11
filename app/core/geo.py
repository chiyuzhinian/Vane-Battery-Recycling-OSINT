"""地理归属 —— 把 `source_id` 映射到国家/地区，供 UI 世界地图使用。

为什么需要这一层
----------------
采集数据里只有两个大区值：

    region: "EU" | "US"

**国家信息藏在 `source_id` 里**（`nl_bwb`→荷兰、`es_boe`→西班牙、`de_gesetze`→德国……
以及 `browser_calrecycle`→美国加州）。地图要靠这层映射才能点亮具体国家。

⚠️ 为什么用**代码表**而不是从 URL 里猜域名
------------------------------------------
    · 同一个源走不同通道时 URL 形态不同（`browser_france` 是整页渲染文本）
    · 网站域名与国家不总对应（`echanges.dila.gouv.fr` 是法国官方源，
      但 `eur-lex.europa.eu` 是超国家的）
    · **漏映射的后果是静默丢失**：某个源没登记 → 它的数据从地图上消失，且不报错

    所以：新增源后必须跑 `scripts/audit_source_mapping.py` 验证覆盖完整。

未映射的兜底
------------
    未登记的 `source_id` 归入 `ZZ`（未知），**不抛异常、不静默丢弃**——
    UI 上单列一个「未归类」分组，让问题可见。
"""
from __future__ import annotations

from dataclasses import dataclass

# ============================================================
# 源 → 地理代码
# ------------------------------------------------------------
# 代码约定：
#   "EU"      超国家（欧盟一级立法 / 欧盟机构）
#   "DE" 等   ISO 3166-1 alpha-2 国家码
#   "US-CA"   国家-州（当前只有加州，预留其他州）
# 未登记 → "ZZ"
# ============================================================
SOURCE_COUNTRY: dict[str, str] = {
    # ---- 超国家：欧盟 ----
    "eu_eurlex_battery_reg": "EU",      # EUR-Lex 电池法规正文（CELEX 精确跟踪）
    "eu_eurlex_keyword": "EU",          # EUR-Lex 关键词发现
    "eur_lex": "EU",                    # 连接器历史名（早期数据用这个）
    "browser_echa": "EU",               # ECHA 欧盟化学品署（浏览器通道）

    # ---- 成员国 ----
    "de_gesetze": "DE",                 # 德国联邦法律（gesetze-im-internet 官方 XML）
    "nl_bwb": "NL",                     # 荷兰国家法规（KOOP BWB 官方 XML）
    "browser_netherlands": "NL",        # 荷兰浏览器通道（Stichting OPEN 等）
    "es_boe": "ES",                     # 西班牙立法整合库（BOE 官方 API）
    "fr_dila": "FR",                    # 法国 DILA 开放数据（Légifrance 原始源）
    "fr_ademe_opendata": "FR",          # 法国 ADEME Data Fair
    "browser_france": "FR",             # 法国浏览器通道

    # ---- 美国联邦 ----
    "us_federal_register": "US",        # Federal Register（主力源，占比最大）
    "browser_phmsa": "US",              # 管道与危险品安全署（锂电池运输）
    "browser_bci": "US",                # Battery Council International（行业组织）

    # ---- 美国州级 ----
    "browser_calrecycle": "US-CA",      # 加州 CalRecycle（负责任电池回收计划）
}


# ============================================================
# 地理单元元数据（地图渲染与 UI 展示用）
# ============================================================
@dataclass(frozen=True)
class GeoUnit:
    code: str                 # "EU" / "US" / "US-CA" / "ZZ"
    name_zh: str
    name_en: str
    level: str                # supranational | country | state | unknown
    parent: str | None = None # 州级指向所属国家

    @property
    def is_renderable(self) -> bool:
        """能否在地图上作为独立色块渲染。

        超国家和国家可以；州级**不单独渲染**（在地图上层级太细），
        而是并入父国家的明细里展示。
        """
        return self.level in ("supranational", "country")


GEO_UNITS: dict[str, GeoUnit] = {
    "EU":    GeoUnit("EU", "欧盟", "European Union", "supranational"),
    "DE":    GeoUnit("DE", "德国", "Germany", "country"),
    "NL":    GeoUnit("NL", "荷兰", "Netherlands", "country"),
    "ES":    GeoUnit("ES", "西班牙", "Spain", "country"),
    "FR":    GeoUnit("FR", "法国", "France", "country"),
    "US":    GeoUnit("US", "美国", "United States", "country"),
    "US-CA": GeoUnit("US-CA", "美国·加利福尼亚州", "United States · California",
                     "state", parent="US"),
    # 兜底：未登记的 source_id 会落到这里，**在 UI 上显式展示**而非隐藏
    "ZZ":    GeoUnit("ZZ", "未归类", "Unclassified", "unknown"),
}

# ISO alpha-2 → 地图 GeoJSON 里的名称（世界地图数据多用英文名做 id）
# 仅供前端匹配用；渲染时以 code 为准
ISO_TO_MAP_NAME: dict[str, str] = {
    "DE": "Germany",
    "NL": "Netherlands",
    "ES": "Spain",
    "FR": "France",
    "US": "United States of America",
}


# ============================================================
# 查询接口
# ============================================================
def country_of(source_id: str | None) -> str:
    """`source_id` → 地理代码。

    未登记返回 `"ZZ"` 而不是抛异常 —— 地图数据是**尽力而为**的展示层，
    一个未登记的源不应该让整个 API 500。
    """
    return SOURCE_COUNTRY.get((source_id or "").strip(), "ZZ")


def unit_of(code: str) -> GeoUnit:
    """地理代码 → 元数据。未知代码返回 `ZZ` 单元（不抛异常）。"""
    return GEO_UNITS.get(code) or GEO_UNITS["ZZ"]


def rollup_parent(code: str) -> str:
    """把州级代码归并到国家（`US-CA` → `US`），其余原样返回。

    地图按**国家**着色时用它；钻取到州级明细时不用。
    """
    u = unit_of(code)
    return u.parent or u.code


def unmapped_sources(source_ids) -> list[str]:
    """列出未登记的 source_id（供 `scripts/audit_source_mapping.py` 校验）。

    用法：
        from app.core.geo import unmapped_sources
        bad = unmapped_sources({"nl_bwb", "某个新源"})   # → ["某个新源"]
    """
    return sorted({s for s in source_ids if s and s not in SOURCE_COUNTRY})


def known_units(level: str | None = None) -> list[GeoUnit]:
    """列出已知地理单元（可按住层级过滤）。

    用于前端初始化地图图例，或在新增源时确认归属。
    """
    units = [u for u in GEO_UNITS.values() if u.code != "ZZ"]
    if level:
        units = [u for u in units if u.level == level]
    return sorted(units, key=lambda u: (u.level, u.code))
