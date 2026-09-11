"""Data Fair 开放数据平台连接器 —— 官方 REST API。

为什么要有这个连接器
--------------------
实测（2026-09-11）：同一个站（data.ademe.fr），两种入口，价值天差地别——

    网页抓取 → 0 条相关
        标题是"Economie circulaire et déchets"这种**分类名**，
        既没电池词也没车辆词，看起来毫无价值。
    识别出平台是 Data Fair → 调 API
        → 立刻拿到 9 个 REP-VHU 数据集，含：
            REP - VHU - Tonnages collectés Broyeurs depuis 2018
            （122 条记录：按省分的破碎厂数量 + 接收的报废车壳体数）
            REP - VHU - TRR et TRV des Broyeurs depuis 2018（回收率指标）
            REP - VHU - Liste des producteurs enregistrés à SYDEREP（生产者名录）

⭐⭐ **核心方法：先识别门户跑在哪个平台软件上，再用平台 API，不要爬页面。**
   这一条比任何单站优化都值钱 —— Data Fair 被法国/比利时等多个
   公共机构使用，换站点只需换 base_url。

Data Fair API 三件套
--------------------
    GET /datasets?q=..&size=N              目录检索
    GET /datasets/<id>                     数据集元信息（schema / count / 主题）
    GET /datasets/<id>/lines?size=N&select= 实际数据行

用法
----
    async with get_connector("datafair") as c:
        items = await c.fetch(terms=["vhu", "broyeur", "batterie"])
        # 或直接指定数据集：
        items = await c.fetch(ids=["rep-vhu-tonnages-collectes-broyeurs-en-2018"])
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from .base import BaseConnector, ProbeResult, RawEvidence


class DataFairConnector(BaseConnector):
    """Data Fair 开放数据平台（默认指向法国 ADEME）。

    ⚠️ 该平台也被其他机构使用；换站点只需覆盖 base_url / portal_name。
    """

    source_id = "fr_ademe_opendata"
    base_url = "https://data.ademe.fr"
    portal_name = "法国 ADEME 开放数据"
    country = "FR"
    timeout = 45.0

    # 与报废车 / 电池回收直接相关的数据集（slug 经实测验证）
    # ⚠️ slug 必须从 API 取真值，猜过 5 个全 404
    #    （`?q=vhu` 一查即得）
    DEFAULT_DATASETS: dict[str, str] = {
        "rep-vhu-tonnages-collectes-broyeurs-en-2018":
            "破碎厂收集吨位（黑粉上游的直接量化指标）",
        "rep-vhu-trr-et-trv-des-broyeurs-en-2018":
            "破碎厂回收率/再利用率（TRR/TRV，对应 EU 回收效率要求）",
        "rep-vhu-tonnages-collectes-cvhu-en-2018":
            "报废车处理中心（CVHU）收集吨位",
        "rep-vhu-trr-et-trv-des-cvhu-en-2018":
            "报废车处理中心回收率/再利用率",
        "rep-vhu-performances-cumulees-en-2018":
            "REP-VHU 累计绩效（生产者责任履行情况）",
        "rep-vhu-liste-des-societes-inscrites-a-syderep":
            "SYDEREP 注册生产者名录（竞争情报：谁在生产、谁在担责）",
        "materiaux-te-t1":
            "报废车材料按处理方式分布",
    }

    def __init__(self, client: Any = None) -> None:
        super().__init__(client=client)
        self._api = f"{self.base_url}/data-fair/api/v1/datasets"

    # ---------- 三件套 ----------
    async def search(self, q: str, size: int = 20) -> list[dict]:
        """目录检索。⚠️ 平台 q= 是模糊 OR 匹配，必须后置过滤。"""
        resp = await self._polite_get(f"{self._api}?size={size}&q={quote(q)}")
        data = resp.json()
        return [{
            "id": r.get("id"), "title": r.get("title") or "",
            "slug": r.get("slug"), "updated": r.get("updatedAt"),
        } for r in (data.get("results") or [])]

    async def dataset(self, did: str) -> dict:
        """数据集元信息（schema / 记录数 / 主题 / 许可）。"""
        resp = await self._polite_get(f"{self._api}/{quote(did)}")
        return resp.json()

    async def lines(self, did: str, size: int = 20,
                    q: str | None = None) -> dict:
        """实际数据行。"""
        url = f"{self._api}/{quote(did)}/lines?size={size}"
        if q:
            url += f"&q={quote(q)}"
        resp = await self._polite_get(url)
        return resp.json()

    # ---------- 归一化 ----------
    async def fetch(self, ids: list[str] | None = None,
                    terms: list[str] | None = None,
                    sample_lines: int = 20,
                    **kwargs: Any) -> list[RawEvidence]:
        """抓取数据集（元信息 + 数据行样本）并归一化为证据。

        为什么要带数据行样本：只有元信息的话，内容里可能一个业务词都没有
        （标题是法语"REP - VHU - ..."），相关性判定会误杀。
        带上真实的列名与行数据，"这是什么数据"才一目了然。
        """
        targets: list[str] = []
        if ids:
            targets = list(ids)
        elif terms:
            seen: set[str] = set()
            for t in terms:
                try:
                    for rec in await self.search(t, size=10):
                        if rec["id"] and rec["id"] not in seen:
                            seen.add(rec["id"])
                            targets.append(rec["id"])
                except Exception as exc:  # noqa: BLE001
                    print(f"    ⚠️ 检索「{t}」失败：{type(exc).__name__}")
        else:
            targets = list(self.DEFAULT_DATASETS)

        out: list[RawEvidence] = []
        for did in targets[:20]:
            try:
                out.append(await self._fetch_one(did, sample_lines))
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ {did} 失败：{type(exc).__name__}")
        return out

    async def _fetch_one(self, did: str, sample_lines: int) -> RawEvidence:
        meta = await self.dataset(did)
        title = meta.get("title") or did

        # 数据行样本（拿不到也不致命，元信息本身有价值）
        rows: list[dict] = []
        total = meta.get("count")
        try:
            lines_data = await self.lines(did, size=sample_lines)
            rows = lines_data.get("results") or []
            total = lines_data.get("total", total)
        except Exception:  # noqa: BLE001
            pass

        schema = [f.get("key") for f in (meta.get("schema") or []) if f.get("key")]
        text = self._render(title, meta, schema, rows, total)

        return RawEvidence(
            evidence_id="",
            channel="connector",
            source_id=self.source_id,
            source_url=f"{self.base_url}/datasets/{did}",
            source_title=title,
            publish_date=None,
            raw_text=text,
            meta={
                "dataset_id": did,
                "country": self.country,
                "region_hint": "EU-MemberState",
                "cluster_hint": "C2_elv",
                "portal": self.portal_name,
                "rows_total": total,
                "rows_sampled": len(rows),
                "schema": schema,
                "topics": meta.get("topics"),
                "license": meta.get("license"),
                "channel_note": "Data Fair 官方 API（非网页抓取）",
            },
        )

    @staticmethod
    def _render(title: str, meta: dict, schema: list[str],
                rows: list[dict], total: Any) -> str:
        """把数据集渲染成可判定的文本。

        必须包含**列名与真实行数据**：法语数据集的标题往往看不出业务含义，
        但列名（如 Nombre_de_carcasses_prises_en_charge = 接收的报废车壳体数）
        信息量很大。
        """
        parts = [f"# {title}", ""]
        desc = (meta.get("description") or "").strip()
        if desc:
            parts += [desc[:2000], ""]
        parts.append(f"记录数: {total}")
        if meta.get("updatedAt"):
            parts.append(f"更新时间: {meta['updatedAt']}")
        parts.append(f"主题: {meta.get('topics')}    许可: {meta.get('license')}")
        parts += ["", "## 字段", ", ".join(schema), "", "## 数据样例"]
        for r in rows[:20]:
            clean = {k: v for k, v in r.items() if not str(k).startswith("_")}
            parts.append(json.dumps(clean, ensure_ascii=False))
        return "\n".join(parts)

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            cat = await self.search("vhu", size=5)
            ok_lines = 0
            if cat:
                l = await self.lines(cat[0]["id"], size=1)
                ok_lines = l.get("total") or 0
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"{type(exc).__name__}")
        return ProbeResult(
            source_id=self.source_id, reachable=True, status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000),
            records_found=len(cat),
            sample=[f"{c['id']} ({c['title'][:40]})" for c in cat[:3]]
                   + ([f"首集数据行 {ok_lines} 条"] if ok_lines else []),
        )
