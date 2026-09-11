"""面板数据访问层 —— 读文件、聚合、叠加人工审核。

设计原则
--------
· **只读原始数据**：`outputs/*.jsonl` 是「采集快照」，永不被面板改写。
  人工审核另存 `review_decisions.jsonl`，读取时**叠加**：
      有效判定 = 审核决定 ?? 原始判定
  这样既保留采集时的机器判定，又能看到人工纠偏结果（可回溯、可再判定）。

· **去重口径与报告一致**：按 URL 去重、`eol_*.jsonl` 优先。
  否则面板数字会与 `docs/policy-report-*.md` 对不上 —— 那是最容易被质疑的地方。

· **缓存 + mtime 失效**：jsonl 会随采集增长，但不能每次请求都全量重读。
"""
from __future__ import annotations

import io
import json
import glob
import collections
from pathlib import Path
from typing import Any, Iterable

from app.core.geo import SOURCE_COUNTRY, unit_of, rollup_parent

# 与 make_report.load_records() 保持一致的加载顺序
_PATTERNS = ("eol_*.jsonl", "browser_*.jsonl", "policy_EU_*.jsonl", "policy_US_*.jsonl")

# 同一份数据可能被多个通道各采一次（实测：ADEME 的 Data Fair API 通道
# `fr_ademe_opendata` 与浏览器通道 `browser_france` 命中了**同一批数据集 URL**）。
# 按"先到先得"去重会让**结构化 API 版输给页面抓取版**：
# 现象是源统计里 API 通道「零产出」，而它其实采到了带字段的真数据行。
# 去重时必须保留**信息质量更高**的那一条：
#   connector（结构化接口，带字段与数据行）
#     > vane（通用搜索返回的网页）
#       > browser_capture（整页渲染文本，导航噪声多）
_CHANNEL_RANK = {"connector": 3, "vane": 2, "browser_capture": 1}


def _channel_rank(r: dict) -> int:
    return _CHANNEL_RANK.get(str(r.get("channel") or ""), 0)


def country_label(code: str) -> str:
    """展示名。

    geo.py 把中英文名封装在 `GeoUnit` 里（一个代码可能对应多语言名），
    面板默认展示中文名；需要英文时用 `unit_of(code).name_en`。
    """
    return unit_of(code).name_zh


class DataStore:
    """面板的唯一数据入口。线程/请求间复用同一实例即可。"""

    def __init__(self, outputs_dir: Path, review_path: Path | None = None) -> None:
        self.outputs = Path(outputs_dir)
        self.review_path = Path(review_path) if review_path else self.outputs / "review_decisions.jsonl"
        self._records: list[dict] | None = None
        self._stamp: tuple = ()
        self._decisions: dict[str, dict] = {}

    # ------------------------------------------------------------ 加载
    def _current_stamp(self) -> tuple:
        """所有数据文件 + 审核文件的 (路径, mtime, 大小) 指纹。"""
        files = []
        for pat in _PATTERNS:
            files += glob.glob(str(self.outputs / pat))
        if self.review_path.exists():
            files.append(str(self.review_path))
        out = []
        for fp in sorted(files):
            try:
                st = Path(fp).stat()
                out.append((fp, int(st.st_mtime), st.st_size))
            except OSError:
                continue
        return tuple(out)

    def _load_decisions(self) -> dict[str, dict]:
        """人工审核决定：target_id → decision（后写的覆盖先写的）。"""
        dec: dict[str, dict] = {}
        if not self.review_path.exists():
            return dec
        try:
            text = io.open(self.review_path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            return dec
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = d.get("target_id")
            if tid:
                dec[tid] = d
        return dec

    def load(self, refresh: bool = False) -> list[dict]:
        """全部记录（去重 + 叠加审核 + 补地理字段）。"""
        stamp = self._current_stamp()
        if self._records is not None and not refresh and stamp == self._stamp:
            return self._records

        self._decisions = self._load_decisions()
        index: dict[str, int] = {}       # url/evidence_id → records 下标
        records: list[dict] = []
        for pat in _PATTERNS:
            for fp in sorted(glob.glob(str(self.outputs / pat))):
                try:
                    text = io.open(fp, encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):
                    continue
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = (r.get("url") or r.get("evidence_id") or "").strip()
                    if not key:
                        continue
                    prev = index.get(key)
                    if prev is None:
                        index[key] = len(records)
                        records.append(self._enrich(r))
                    elif _channel_rank(r) > _channel_rank(records[prev]):
                        # 同一条数据换了更优的通道 → 换掉旧的
                        records[prev] = self._enrich(r)

        self._records = records
        self._stamp = stamp
        return records

    # ------------------------------------------------------------ 单条加工
    def _enrich(self, r: dict) -> dict:
        """补上地理归属 + 叠加人工审核结果（不修改原始字段，另开 effective_*）。"""
        sid = r.get("source_id") or "?"
        code = SOURCE_COUNTRY.get(sid, "ZZ")
        r["geo_code"] = code
        # ⚠️ 必须用 `unit_of(...).name_zh`，不要写 `country_label(code)` ——
        #    后者在 geo.py 里**根本不存在**，而且 store.py 也没导入它。
        #    一旦执行到这一行就是 NameError → 整个面板 API 直接 500。
        #    （geo.unit_of 对未知 code 返回 "ZZ" 单元，不会抛异常。）
        r["geo_name"] = unit_of(code).name_zh
        r["geo_parent"] = rollup_parent(code)       # US-CA → US（地图聚合用）

        # 审核叠加：原始判定保持不动，另记有效判定
        dec = self._decisions.get(r.get("evidence_id") or "")
        r["reviewed"] = bool(dec)
        r["review_verdict"] = (dec or {}).get("verdict")
        raw_rel = bool(r.get("relevant"))
        if dec and dec.get("verdict") in ("relevant", "irrelevant"):
            r["effective_relevant"] = dec["verdict"] == "relevant"
        else:
            r["effective_relevant"] = raw_rel
        r["machine_relevant"] = raw_rel
        return r

    # ------------------------------------------------------------ 聚合
    def map_stats(self) -> list[dict]:
        """按**父国家**聚合 —— 地图每个国家一个色块。"""
        buckets: dict[str, dict[str, Any]] = collections.defaultdict(
            lambda: {"total": 0, "relevant": 0, "review": 0, "sources": set(),
                     "channels": collections.Counter()})
        for r in self.load():
            c = r["geo_parent"]
            b = buckets[c]
            b["total"] += 1
            if r["effective_relevant"]:
                b["relevant"] += 1
            if r.get("needs_human_review"):
                b["review"] += 1
            b["sources"].add(r.get("source_id"))
            b["channels"][r.get("channel") or "?"] += 1

        out = []
        for code, b in buckets.items():
            out.append({
                "code": code,
                "name": country_label(code),
                "total": b["total"],
                "relevant": b["relevant"],
                "needs_review": b["review"],
                "rejected": b["total"] - b["relevant"],
                "source_count": len(b["sources"]),
                "relevance_rate": round(b["relevant"] / b["total"], 3) if b["total"] else 0.0,
                "channels": dict(b["channels"]),
            })
        out.sort(key=lambda x: -x["total"])
        return out

    def country_detail(self, code: str) -> dict:
        """一个国家/地区的完整画像 —— 对应地图点击后的抽屉。"""
        code = code.upper()
        rows = [r for r in self.load() if r["geo_parent"] == code]
        if not rows:
            return {"code": code, "name": country_label(code), "found": False}

        by_source: dict[str, dict[str, Any]] = collections.defaultdict(
            lambda: {"total": 0, "relevant": 0, "review": 0, "clusters": collections.Counter()})
        by_cluster: collections.Counter = collections.Counter()
        for r in rows:
            s = by_source[r.get("source_id") or "?"]
            s["total"] += 1
            if r["effective_relevant"]:
                s["relevant"] += 1
            if r.get("needs_human_review"):
                s["review"] += 1
            if r.get("cluster_hint"):
                s["clusters"][r["cluster_hint"]] += 1
                by_cluster[r["cluster_hint"]] += 1

        sources = [{
            "source_id": sid,
            "total": v["total"],
            "relevant": v["relevant"],
            "needs_review": v["review"],
            "relevance_rate": round(v["relevant"] / v["total"], 3) if v["total"] else 0.0,
            "clusters": dict(v["clusters"]),
        } for sid, v in sorted(by_source.items(), key=lambda kv: -kv[1]["total"])]

        # 子区域拆分（如 US 下的 US-CA）
        children = sorted({r["geo_code"] for r in rows if r["geo_code"] != code})

        dates = [r.get("publish_date") for r in rows if r.get("publish_date")]
        return {
            "code": code,
            "name": country_label(code),
            "found": True,
            "total": len(rows),
            "relevant": sum(1 for r in rows if r["effective_relevant"]),
            "needs_review": sum(1 for r in rows if r.get("needs_human_review")),
            "reviewed": sum(1 for r in rows if r.get("reviewed")),
            "sources": sources,
            "clusters": dict(by_cluster),
            "children": [{"code": c, "name": country_label(c)} for c in children],
            "date_range": [min(dates), max(dates)] if dates else None,
        }

    def records(self, *, country: str | None = None, source_id: str | None = None,
                relevant: bool | None = None, review_only: bool = False,
                unreviewed_only: bool = False, cluster: str | None = None,
                q: str | None = None, page: int = 1, page_size: int = 50,
                sort: str = "score") -> dict:
        """筛选 + 分页。`relevant` 用**有效判定**（含人工审核覆盖）。"""
        rows = self.load()
        if country:
            rows = [r for r in rows if r["geo_parent"] == country.upper()]
        if source_id:
            rows = [r for r in rows if r.get("source_id") == source_id]
        if cluster:
            rows = [r for r in rows if r.get("cluster_hint") == cluster]
        if relevant is not None:
            rows = [r for r in rows if r["effective_relevant"] is relevant]
        if review_only:
            rows = [r for r in rows if r.get("needs_human_review")]
        if unreviewed_only:
            rows = [r for r in rows if not r.get("reviewed")]
        if q:
            needle = q.lower()
            rows = [r for r in rows
                    if needle in (r.get("title") or "").lower()
                    or needle in (r.get("text") or "").lower()]

        if sort == "date":
            rows.sort(key=lambda r: r.get("publish_date") or "", reverse=True)
        else:
            rows.sort(key=lambda r: (r.get("relevance_score") or 0), reverse=True)

        total = len(rows)
        page = max(1, page)
        page_size = min(max(1, page_size), 200)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if total else 0,
            "items": [self._brief(r) for r in rows[start:start + page_size]],
        }

    @staticmethod
    def _brief(r: dict) -> dict:
        """列表用精简结构（不带全文，省带宽）。"""
        return {
            "evidence_id": r.get("evidence_id"),
            "geo_code": r.get("geo_code"),
            "geo_name": r.get("geo_name"),
            "source_id": r.get("source_id"),
            "channel": r.get("channel"),
            "cluster_hint": r.get("cluster_hint"),
            "title": (r.get("title") or "")[:160],
            "url": r.get("url"),
            "publish_date": r.get("publish_date"),
            "machine_relevant": r.get("machine_relevant"),
            "effective_relevant": r.get("effective_relevant"),
            "relevance_score": r.get("relevance_score"),
            "needs_human_review": r.get("needs_human_review"),
            "reviewed": r.get("reviewed"),
            "review_verdict": r.get("review_verdict"),
            "hits": (r.get("hits") or [])[:5],
            "rejected_by": r.get("rejected_by"),
            # ⭐ 展开阅读用：用户要求「逐个查看之后判定是不是」，
            #    列表就带上正文摘要，避免展开时再发一次请求（交互有延迟）
            "text": (r.get("text") or "")[:900],
        }

    def record_detail(self, evidence_id: str) -> dict | None:
        for r in self.load():
            if r.get("evidence_id") == evidence_id:
                return r
        return None

    def facets(self) -> dict:
        """筛选器选项：国家 / 源 / 簇 / 状态计数。"""
        rows = self.load()
        return {
            "countries": [{"code": k, "name": country_label(k), "count": v}
                          for k, v in collections.Counter(
                              r["geo_parent"] for r in rows).most_common()],
            "sources": [{"source_id": k, "count": v}
                        for k, v in collections.Counter(
                            r.get("source_id") for r in rows).most_common()],
            "clusters": [{"cluster": k, "count": v}
                         for k, v in collections.Counter(
                             r.get("cluster_hint") for r in rows if r.get("cluster_hint")
                         ).most_common()],
            "counts": {
                "total": len(rows),
                "relevant": sum(1 for r in rows if r["effective_relevant"]),
                "needs_review": sum(1 for r in rows if r.get("needs_human_review")),
                "reviewed": sum(1 for r in rows if r.get("reviewed")),
            },
        }
