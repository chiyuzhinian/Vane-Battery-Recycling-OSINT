"""面板 HTTP API（FastAPI）—— 世界地图 + 记录浏览 + 审核 + 反哺。

端口约定
--------
    后端 8000  |  前端 3100
    ⚠️ 前端**不能用 3000** —— 那是 Vane 的端口（本项目的通道 A）。

分层
----
    main.py（本文件）  只做 HTTP 适配：参数校验、错误映射、序列化
    store.py           数据访问：读 jsonl、去重、聚合、叠加人工审核
    core/geo.py        地理归属：source_id → 国家码
    core/feedback.py   （阶段四接入）反哺闭环引擎

⚠️ 本层**只读** `outputs/*.jsonl`。审核写入是独立文件 `review_decisions.jsonl`，
   反哺动作（阶段四）也不直接改数据文件，而是产出「待确认动作清单」。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.api.review import ReviewStore, VALID_TARGETS, VALID_VERDICTS
from app.api.store import DataStore
from app.core.geo import GEO_UNITS, ISO_TO_MAP_NAME, known_units

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS = ROOT / "outputs"

store = DataStore(OUTPUTS)
review_store = ReviewStore(OUTPUTS / "review_decisions.jsonl")

app = FastAPI(
    title="退役电池回收 OSINT 面板 API",
    version="0.1.0",
    description="世界地图 + 记录浏览 + 人工审核 + 反哺闭环",
)

# 前端 3100（Vane 占用了 3000，不要混用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================ 基础
@app.get("/api/health", summary="健康检查 + 数据条数")
def health() -> dict[str, Any]:
    rows = store.load()
    return {"ok": True, "records": len(rows), "outputs_dir": str(OUTPUTS)}


@app.get("/api/units", summary="地理单元与地图名称映射（前端渲染图例用）")
def units() -> dict[str, Any]:
    return {
        "units": [
            {"code": u.code, "name_zh": u.name_zh, "name_en": u.name_en,
             "level": u.level, "parent": u.parent,
             "renderable": u.is_renderable}
            for u in known_units()
        ],
        # 前端世界地图 GeoJSON 多用英文名作为 id
        "map_names": ISO_TO_MAP_NAME,
    }


# ============================================================ 地图
@app.get("/api/map", summary="地图数据：每个国家/地区一个色块")
def map_stats() -> dict[str, Any]:
    return {"regions": store.map_stats()}


# ============================================================ 国家详情
@app.get("/api/country/{code}", summary="一个国家/地区的完整画像")
def country(code: str) -> dict[str, Any]:
    detail = store.country_detail(code)
    if not detail.get("found"):
        raise HTTPException(404, f"没有 {code} 的数据")
    return detail


# ============================================================ 记录
@app.get("/api/facets", summary="筛选器选项与状态计数")
def facets() -> dict[str, Any]:
    return store.facets()


@app.get("/api/records", summary="记录列表（筛选 + 分页）")
def records(
    country: str | None = Query(None, description="国家码，如 US / EU / NL / US-CA"),
    source_id: str | None = Query(None, description="数据源，如 nl_bwb"),
    cluster: str | None = Query(None, description="关键词簇，如 C3_black_mass"),
    relevant: bool | None = Query(None, description="按**有效判定**过滤（含人工审核）"),
    review_only: bool = Query(False, description="只看待人工复核"),
    unreviewed_only: bool = Query(False, description="只看未审核的"),
    q: str | None = Query(None, description="标题/正文关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("score", pattern="^(score|date)$"),
) -> dict[str, Any]:
    return store.records(
        country=country, source_id=source_id, cluster=cluster,
        relevant=relevant, review_only=review_only,
        unreviewed_only=unreviewed_only, q=q,
        page=page, page_size=page_size, sort=sort,
    )


@app.get("/api/record/{evidence_id}", summary="单条记录详情（含判定依据）")
def record_detail(evidence_id: str) -> dict[str, Any]:
    r = store.record_detail(evidence_id)
    if not r:
        raise HTTPException(404, "未找到该记录")
    return r


# ============================================================ 人工审核
#
# ⭐ 只写 `review_decisions.jsonl`，**不碰** `outputs/*.jsonl`。
#    每次写入后调 `store.load(refresh=True)` 使后续查询立即看到新决定。


class DecisionIn(BaseModel):
    target_type: str = Field(..., description="record | source")
    target_id: str = Field(..., description="record 用 evidence_id；source 用 source_id")
    verdict: str = Field(..., description="relevant | irrelevant | uncertain")
    reason: str = ""
    country: str | None = None


class ReviewIn(BaseModel):
    decisions: list[DecisionIn]


class RevokeIn(BaseModel):
    decision_ids: list[str]


class UndoLastIn(BaseModel):
    n: int = Field(1, ge=1, le=500)


@app.get("/api/review/schema", summary="审核取值域（前端渲染按钮用）")
def review_schema() -> dict[str, Any]:
    return {"verdicts": list(VALID_VERDICTS), "targets": list(VALID_TARGETS)}


@app.post("/api/review", summary="提交人工审核（单条或批量）")
def submit_review(body: ReviewIn) -> dict[str, Any]:
    try:
        rows = review_store.submit([d.model_dump() for d in body.decisions])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.load(refresh=True)
    return {"saved": len(rows), "decisions": rows}


@app.post("/api/review/revoke", summary="按 decision_id 撤销")
def revoke_review(body: RevokeIn) -> dict[str, Any]:
    n = review_store.revoke(body.decision_ids)
    store.load(refresh=True)
    return {"removed": n}


@app.post("/api/review/undo-last", summary="撤销最近 N 条（UI 的「撤销上一批」）")
def undo_last(body: UndoLastIn) -> dict[str, Any]:
    ids = review_store.revoke_last(body.n)
    store.load(refresh=True)
    return {"removed": len(ids), "decision_ids": ids}


@app.get("/api/review/stats", summary="审核进度")
def review_stats() -> dict[str, Any]:
    s = review_store.stats()
    rows = store.load()
    s["records_total"] = len(rows)
    s["records_reviewed"] = sum(1 for r in rows if r.get("reviewed"))
    return s


# ============================================================ 未归类告警
@app.get("/api/unmapped", summary="未映射的 source_id（UI 上必须显式展示）")
def unmapped() -> dict[str, Any]:
    """漏映射 = 数据从地图上静默消失。

    所以单独开一个端点，让前端在角落常驻一个告警角标——**问题要看得见**。
    """
    rows = store.load()
    bad: dict[str, int] = {}
    for r in rows:
        if r["geo_code"] == "ZZ":
            sid = r.get("source_id") or "?"
            bad[sid] = bad.get(sid, 0) + 1
    return {
        "has_unmapped": bool(bad),
        "sources": [{"source_id": k, "count": v} for k, v in sorted(
            bad.items(), key=lambda kv: -kv[1])],
        "hint": "补进 app/core/geo.py 的 SOURCE_COUNTRY 后即可在地图上归位",
    }


def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """启动入口（供 scripts/serve_panel.py 调用）。"""
    import uvicorn
    uvicorn.run("app.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run(reload=True)
