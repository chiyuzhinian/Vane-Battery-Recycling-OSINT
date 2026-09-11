"""西班牙 BOE 立法整合库连接器 —— 官方 REST API。

为什么值得单独做
----------------
西班牙是欧洲第二大汽车生产国，"车辆报废 + 电池回收"体量大；
BOE（Boletín Oficial del Estado）提供**完整 REST API + 每日公报**，
是成员国层里接口最规范的一个。

⚠️ 唯一的坑：**必须显式带 Accept 头**
--------------------------------
    GET /datosabiertos/api/boe/sumario/20260910
      → 400 {"text": "No soportado ningún mime type de la cabecera Accept."}

它不是反爬、也不是限流，而是**严格内容协商**——不接受 httpx/curl 默认的 `*/*`。
加上 `Accept: application/xml` 立刻 200。（与 EUR-Lex 的 Accept 行为同一类问题，
属于"看起来像被拦、其实是没按规矩请求"。）

实测端点（从 api.php 帮助页导出，共 19 个）
------------------------------------------
    /boe/sumario/{fecha}                                每日公报（含全部栏目）
    /borme/sumario/{fecha}                              商事公报
    /legislacion-consolidada                            立法整合库索引（分页）
    /legislacion-consolidada/id/{id}                    单部法
    /legislacion-consolidada/id/{id}/texto              正文 ★
    /legislacion-consolidada/id/{id}/texto/indice       条文目录
    /legislacion-consolidada/id/{id}/texto/bloque/{n}   分块取正文
    /legislacion-consolidada/id/{id}/metadatos          元数据
    /legislacion-consolidada/id/{id}/analisis           引用关系
    /datos-auxiliares/{ambitos,departamentos,materias,rangos,...}

编号发现：**分页枚举 + 标题筛选**
--------------------------------
索引只回"最近更新"的 50 条，但 `?offset=N` 是**真翻页**（实测三页零重叠）。
所以走"先建目录，再按标题筛"——与德国 `gii-toc.xml` 同一模式。
（⚠️ 不要猜 BOE 编号：`BOE-A-2022-22065` 是凭空猜的，404。）
索引项**不含主题词编码**，`?materia=` 等参数一律 "Parámetros no soportados"。

用法
----
    async with get_connector("es_boe") as c:
        laws = await c.catalog(max_pages=20)         # 建目录
        hits = c.match(laws)                          # 按西语词筛标题
        items = await c.fetch(ids=[laws[0]["id"]])    # 取正文
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)

# 目录缓存：全量枚举 ~1.2 万部法规需 ~250 次请求，不能每次采集重跑
ROOT_DIR = Path(__file__).resolve().parents[2]
CATALOG_CACHE = ROOT_DIR / "outputs" / "cache" / "boe_catalog.json"

# 正文里我们关心的西语术语
KEY_TERMS: tuple[str, ...] = (
    "batería", "baterias", "pila", "acumulador", "residuo", "peligroso",
    "reciclaje", "reciclado", "valorización", "eliminación",
    "vehículo fuera de uso", "descontaminación", "fragmentación", "chatarra",
    "masa negra", "cobalto", "litio", "níquel", "responsabilidad ampliada",
)


class BoeEsConnector(BaseConnector):
    """西班牙官方公报与立法整合库（BOE 开放数据 API）。"""

    source_id = "es_boe"
    base_url = "https://www.boe.es/datosabiertos/api"
    timeout = 60.0

    # ⚠️ 不带这个头一律 400（不是反爬，是内容协商）
    ACCEPT = {"Accept": "application/xml"}
    PAGE = 50

    # ⭐ 已验证的相关法规编号（由全量目录 12,395 部中筛出）
    # ⚠️ 全部经实测可取到正文；**不要改成猜测的编号**——
    #    曾猜 BOE-A-2008-2981（真值是 2387）→ 404「La información solicitada no existe」。
    DEFAULT_LAWS: dict[str, str] = {
        "BOE-A-2008-2387": "Real Decreto 106/2008 —— 电池与蓄电池及其废物的环境管理"
                            "（西班牙实施欧盟电池指令的国内法）",
        "BOE-A-2011-11827": "Real Decreto 846/2011 —— 报废车辆（VFU）处理设施的条件",
        "BOE-A-2022-19914": "Real Decreto 993/2022 —— 电池相关的控制措施",
        "BOE-A-2022-5809": "Ley 7/2022 —— 废物与污染土壤（循环经济）国家基础法",
        "BOE-A-2024-21709": "Real Decreto 1093/2024 —— 废物管理",
    }

    # 标题筛选词（西语）—— ⚠️ 分级，不能一视同仁
    # 实测教训：只用 `residuos?` 会把加利西亚/瓦伦西亚/巴利阿里等
    # **自治区通用废物法**（25~48 万字符/部）全部捞进来，
    # 它们与电池/黑粉无关，会把目录冲垮。
    STRONG_TERMS: tuple[str, ...] = (
        r"bater[ií]as?\b", r"\bpilas?\b", r"acumulador", r"fuera de uso",
        r"masa\s+negra", rf"\bvfu\b",
    )
    MEDIUM_TERMS: tuple[str, ...] = (
        r"descontaminaci[óo]n", r"fragmentaci[óo]n", r"chatarra",
        r"reciclaje", r"reciclado", r"residuos?\s+peligrosos",
    )
    WEAK_TERMS: tuple[str, ...] = (
        r"residuos?\b", r"contaminaci[óo]n del suelo", r"econom[íi]a circular",
    )

    # 综合筛选词（供外部直接引用）
    TITLE_TERMS: tuple[str, ...] = STRONG_TERMS + MEDIUM_TERMS + WEAK_TERMS

    def __init__(self, client: Any = None) -> None:
        super().__init__(client=client)
        self._catalog: list[dict] | None = None

    # ---------- HTTP ----------
    async def _get(self, path: str, **params: Any):
        return await self._polite_get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self.ACCEPT,
            params=params or None,
        )

    # ---------- 目录 ----------
    async def catalog(self, max_pages: int = 400, refresh: bool = False,
                      max_age_days: int = 14) -> list[dict]:
        """分页枚举立法整合库，返回 {id, titulo, rango, fecha, vigente...} 列表。

        ⚠️ offset 是**真翻页**（实测三页零重叠）；语料总量 10k~15k 部，
           全量扫描 ~250 次请求，所以结果**落盘缓存**（默认 14 天内不重扫）。
        """
        if self._catalog is not None:
            return self._catalog
        if not refresh:
            cached = _load_cache(max_age_days)
            if cached:
                self._catalog = cached
                return cached

        out: list[dict] = []
        seen: set[str] = set()
        for page in range(max_pages):
            offset = page * self.PAGE
            try:
                resp = await self._get("legislacion-consolidada",
                                       offset=offset, limit=self.PAGE)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ es_boe 目录 offset={offset} 失败：{type(exc).__name__}")
                break
            items = [_parse_item(b) for b in _ITEM_RE.findall(resp.text)]
            items = [i for i in items if i.get("id")]
            if not items:
                break                    # 到底了
            for it in items:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    out.append(it)
            if (page + 1) % 25 == 0:
                print(f"      目录 {len(out)} 部…")
            if len(items) < self.PAGE:
                break                    # 最后一页
        self._catalog = out
        if out:
            _save_cache(out)
        return out

    def match(self, laws: list[dict] | None = None,
              min_score: int = 1,
              only_estatal: bool = False,
              drop_expired: bool = False) -> list[dict]:
        """按西语关键词给标题**分级打分**，返回按相关度倒序的候选。

        分数：专有词（电池/报废车）=3，中等（破碎/回收）=2，通用废物=1。
        只命中通用废物词的自治区法规会排在最后，可用 min_score 卡掉。
        """
        tiered = [(self.STRONG_TERMS, 3), (self.MEDIUM_TERMS, 2), (self.WEAK_TERMS, 1)]
        compiled = [(re.compile(t, re.I), w) for terms, w in tiered for t in terms]

        hits: list[dict] = []
        for law in (laws if laws is not None else (self._catalog or [])):
            if only_estatal and (law.get("ambito") or "") != "Estatal":
                continue
            if drop_expired and (law.get("vigencia_agotada") or "").upper() == "Y":
                continue
            title = law.get("titulo") or ""
            matched = [p.pattern for p, _ in compiled if p.search(title)]
            if not matched:
                continue
            score = max(w for p, w in compiled if p.search(title))
            if score < min_score:
                continue
            law = dict(law)
            law["matched"] = matched
            law["score"] = score
            hits.append(law)
        return sorted(hits, key=lambda x: -x["score"])

    # ---------- 抓取 ----------
    async def fetch(self, ids: list[str] | None = None,
                    max_pages: int = 400,
                    min_score: int = 2,
                    only_estatal: bool = False,
                    drop_expired: bool = True,
                    limit: int | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        """取正文。ids 优先；否则先建目录，再按标题分级筛。

        ⚠️ max_pages 默认 400（全量）。**不要图快改成 40**：
           40 页 = 2,000 部，而语料共 10k~15k 部且**顺序任意**，
           实测那 2,000 部里电池专法命中 0 部 —— 局部扫描会得出错误结论。
           目录有磁盘缓存（14 天），全量扫描只付一次代价。

        默认 min_score=2：只取含“电池/报废车/破碎/回收”类词的法规，
        排除仅含“residuo”的通用废物法（否则被自治区废物法淹没）。
        """
        targets: list[dict] = []
        if ids:
            targets = [{"id": i} for i in ids]
        else:
            # ① 先放**已验证的精选法规**（不依赖目录，保证核心法一定入库）
            targets = [{"id": i, "titulo": t, "curated": True}
                       for i, t in self.DEFAULT_LAWS.items()]
            # ② 再用目录扫描补发现（可能失效/不存在，失败不告急）
            try:
                laws = await self.catalog(max_pages=max_pages)
                hits = self.match(laws, min_score=min_score,
                                  only_estatal=only_estatal, drop_expired=drop_expired)
                known = {t["id"] for t in targets}
                fresh = [h for h in hits if h["id"] not in known]
                print(f"    目录 {len(laws)} 部 → 标题命中 {len(hits)} 部"
                      f"（分≥{min_score}{'，仅国家级' if only_estatal else ''}），"
                      f"其中新增 {len(fresh)} 部")
                targets += fresh[: limit or 20]
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ es_boe 目录扫描失败（仍用精选清单）：{type(exc).__name__}")

        out: list[RawEvidence] = []
        for t in targets:
            try:
                out.append(await self._fetch_one(t))
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ es_boe {t.get('id')} 失败：{type(exc).__name__}: {exc}")
        return out

    async def _fetch_one(self, law: dict) -> RawEvidence:
        bid = law["id"]
        resp = await self._get(f"legislacion-consolidada/id/{bid}/texto")
        text, meta = self._parse_texto(resp.text)
        title = law.get("titulo") or meta.get("titulo") or bid
        return RawEvidence(
            evidence_id="",
            channel="connector",
            source_id=self.source_id,
            source_url=f"https://www.boe.es/buscar/act.php?id={bid}",
            source_title=f"{title} [{bid}]",
            publish_date=_parse_ymd(law.get("fecha_publicacion") or law.get("fecha")),
            raw_text=text,
            meta={
                "boe_id": bid,
                "country": "ES",
                "region_hint": "EU-MemberState",
                "law_title": title,
                "rango": law.get("rango"),
                "departamento": law.get("departamento"),
                "ambito": law.get("ambito"),
                "vigencia_agotada": law.get("vigencia_agotada"),
                "estado_consolidacion": law.get("estado"),
                "fecha_vigencia": law.get("fecha_vigencia"),
                "url_eli": law.get("url_eli"),
                "matched": law.get("matched"),
                "title_score": law.get("score"),
                "curated": law.get("curated", False),
                "derogada": meta.get("derogada"),
                "derogada_nota": meta.get("derogada_nota"),
                "term_hits": meta.get("term_hits"),
                "api_url": f"{self.base_url}/legislacion-consolidada/id/{bid}/texto",
                "channel_note": "西班牙 BOE 立法整合库官方 API（Accept: application/xml）",
            },
        )

    # ---------- 每日公报 ----------
    async def daily(self, date: str, terms: list[str] | None = None) -> list[RawEvidence]:
        """某日 BOE 公报（YYYYMMDD）→ 命中领域关键词的条目。"""
        resp = await self._get(f"boe/sumario/{date}")
        xml = resp.text
        pats = [re.compile(t, re.I) for t in (terms or self.TITLE_TERMS)]
        out: list[RawEvidence] = []
        for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
            title = _tag(block, "titulo")
            if not title or not any(p.search(title) for p in pats):
                continue
            ident = _tag(block, "identificador") or ""
            url = _tag(block, "url_html") or _tag(block, "url_pdf") or ""
            out.append(RawEvidence(
                evidence_id="",
                channel="connector",
                source_id=self.source_id,
                source_url=url or f"https://www.boe.es/diario_boe/",
                source_title=f"[BOE {date}] {title}",
                publish_date=_parse_ymd(date),
                raw_text=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).strip()[:4000],
                meta={
                    "country": "ES", "region_hint": "EU-MemberState",
                    "boe_id": ident, "sumario_date": date,
                    "channel_note": "BOE 每日公报（boe/sumario）",
                },
            ))
        return out

    # ---------- 解析 ----------
    def _parse_texto(self, xml: str) -> tuple[str, dict]:
        titulo = _tag(xml, "titulo")
        if "<texto" not in xml and not titulo:
            raise ConnectorError(f"{self.source_id}: 正文响应异常")
        txt = re.sub(r"</(p|div|br|h[1-6]|li|bloque)>", "\n", xml, flags=re.I)
        txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
        txt = _TAG_RE.sub(" ", txt)
        txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
                  .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
        txt = _WS_RE.sub(" ", txt)
        txt = _BLANK_RE.sub("\n\n", txt).strip()
        hits = {t: len(re.findall(re.escape(t), txt, re.I)) for t in KEY_TERMS}
        hits = {k: v for k, v in sorted(hits.items(), key=lambda kv: -kv[1]) if v}

        # ⚠️ 索引里的 vigencia_agotada 并不可靠：实测 RD 846/2011 与 RD 1619/2005
        #    在索引里 vigencia_agotada=N，但正文第一行写着 "Norma derogada"。
        #    **知道一部法已废止本身就是情报**——它说明监管已转移到别处，
        #    所以不丢弃，而是标记出来。
        head = txt[:400]
        m = re.search(r"Norma\s+derogada[^.]{0,160}", head, re.I)
        return txt, {"titulo": titulo, "term_hits": hits,
                     "derogada": bool(m),
                     "derogada_nota": m.group(0).strip()[:160] if m else None}

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        t0 = time.monotonic()
        try:
            resp = await self._get("boe/sumario/20260910")
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"{type(exc).__name__}: {exc}")
        n = len(re.findall(r"<item>", resp.text))
        return ProbeResult(
            source_id=self.source_id, reachable=True, status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000),
            records_found=n,
            sample=[f"当日公报条目 {n}", f"响应 {len(resp.content)} 字节"])


# ---------- 工具 ----------
def _tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", m.group(1))).strip()


def _parse_item(block: str) -> dict:
    return {
        "id": _tag(block, "identificador"),
        "titulo": _tag(block, "titulo"),
        "rango": _tag(block, "rango"),
        "departamento": _tag(block, "departamento"),
        "ambito": _tag(block, "ambito"),
        "fecha": _tag(block, "fecha_actualizacion"),
        "fecha_publicacion": _tag(block, "fecha_publicacion"),
        "fecha_vigencia": _tag(block, "fecha_vigencia"),
        "vigencia_agotada": _tag(block, "vigencia_agotada"),
        "estado": _tag(block, "estado_consolidacion"),
        "url_eli": _tag(block, "url_eli"),
    }


def _parse_ymd(value: str | None) -> datetime | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)[:8]
    try:
        return datetime.strptime(digits, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_cache(max_age_days: int) -> list[dict] | None:
    """读目录缓存（过期或损坏则返回 None）。"""
    if not CATALOG_CACHE.exists():
        return None
    try:
        blob = json.loads(CATALOG_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    saved = blob.get("saved_at")
    if not saved:
        return None
    try:
        when = datetime.fromisoformat(saved)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - when > timedelta(days=max_age_days):
        return None
    laws = blob.get("laws")
    return laws if isinstance(laws, list) and laws else None


def _save_cache(laws: list[dict]) -> None:
    CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_CACHE.write_text(
        json.dumps({"saved_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(laws), "laws": laws},
                   ensure_ascii=False),
        encoding="utf-8",
    )
