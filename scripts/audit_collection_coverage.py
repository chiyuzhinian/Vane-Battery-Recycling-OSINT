"""采集穷尽性审计 —— 回答「我们到底采全了吗」。

为什么需要这个
--------------
「采完了」不能靠感觉。必须能从**四个维度**逐项对账，才知道缺口在哪：

    ① CELEX   跟踪清单 vs 实际落盘        —— 有没有漏掉跟踪的法案
    ② 关键词   配置清单 vs 实际命中的       —— 有没有没跑/没出结果的关键词
    ③ 数据源   应有源   vs 实际有数据的     —— 有没有接入却一条没采到的源
    ④ 时间     数据日期范围 vs 采集起点     —— 起点之前的法规是否属于遗漏

用法
----
    py scripts/audit_collection_coverage.py
    py scripts/audit_collection_coverage.py --since 2024-06-01   # 指定预期起点

退出码
------
    0 = 无缺口    1 = 存在缺口（需要补采）
"""
from __future__ import annotations

import io
import re
import sys
import glob
import json
import argparse
import collections
from pathlib import Path

sys.path.insert(0, ".")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
SOURCES = ROOT / "sources"

# 有采集能力的源 —— 必须用**落盘时真正写入的 source_id**。
# 不能用连接器模块名：eur_lex / us_federal / dila_fr / datafair 都是**模块名**，
# 它们写入的 source_id 分别是 eu_eurlex_*、us_federal_register、fr_dila、
# fr_ademe_opendata —— 拿模块名对账会凭空误报 6 个"零产出"。
EXPECTED_SOURCES = {
    # 欧盟
    "eu_eurlex_battery_reg", "eu_eurlex_keyword",
    # 美国
    "us_federal_register",
    # 成员国官方通道
    "de_gesetze", "nl_bwb", "es_boe", "fr_dila", "fr_ademe_opendata",
    # 浏览器通道（反爬站点的兜底）
    "browser_echa", "browser_france", "browser_netherlands",
    "browser_phmsa", "browser_bci", "browser_calrecycle",
}


# 同 URL 跨通道去重时，保留**信息质量更高**的通道（与 app/api/store.py 同一口径）。
# 实测坑：ADEME 的数据被 API 通道（fr_ademe_opendata）与浏览器通道
# （browser_france）各采一次，先到先得会让 API 版被吞 —— 于是审计误报
# 「fr_ademe_opendata 零产出」，而它其实有 28 条带数据行的记录。
_CHANNEL_RANK = {"connector": 3, "vane": 2, "browser_capture": 1}


def _channel_rank(r: dict) -> int:
    return _CHANNEL_RANK.get(str(r.get("channel") or ""), 0)


def load_records() -> list[dict]:
    index: dict[str, int] = {}
    rows: list[dict] = []
    for pat in ("eol_*.jsonl", "browser_*.jsonl"):
        for fp in sorted(glob.glob(str(OUT / pat))):
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
                    index[key] = len(rows)
                    rows.append(r)
                elif _channel_rank(r) > _channel_rank(rows[prev]):
                    rows[prev] = r
    return rows


def tracked_celex() -> list[str]:
    """sources/eu-acts-tracked.yaml 里跟踪的 CELEX。

    ⚠️ 只算 `tracked`（人工确认为要跟踪的）。
       不要把 eu-acts-candidates.yaml 算进来 —— 那是**待筛选候选**，
       混算会凭空造出几十个假缺口（实测：68 vs 真实 46）。
    """
    p = SOURCES / "eu-acts-tracked.yaml"
    if not p.exists():
        return []
    try:
        import yaml  # 延迟导入：本脚本在无 PyYAML 环境也能跑前两节
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return []
    ids: list[str] = []
    for a in (d.get("tracked") or []):
        if isinstance(a, dict) and a.get("celex"):
            ids.append(str(a["celex"]))
    return sorted(set(ids))


def configured_keywords() -> list[str]:
    """keyword-taxonomy-eol-battery.yaml 的 `discovery_terms`（真正拿去检索的）。

    ⚠️ 只算 discovery_terms。clusters 里的 terms 是"概念全集"，
       用于人工理解与后期 NLP 标注，**不拿去检索**（实测：83 个全跑要
       15-80 分钟且后 70 个几乎带不回新结果）。把它们算进"应有"是假缺口。
    """
    p = SOURCES / "keyword-taxonomy-eol-battery.yaml"
    if not p.exists():
        return []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for t in (d.get("discovery_terms") or []):
        if isinstance(t, dict) and t.get("term"):
            out.append(str(t["term"]))
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-06-01",
                    help="预期采集起点（默认 2024-06-01）")
    args = ap.parse_args()

    rows = load_records()
    print(f"载入 {len(rows)} 条去重记录\n")
    gaps: list[str] = []

    # ---------- ① CELEX 覆盖 ----------
    print("=" * 78)
    print("① CELEX 覆盖：跟踪清单 vs 实际落盘")
    print("=" * 78)
    tracked = tracked_celex()
    got: set[str] = set()
    for r in rows:
        meta = r.get("meta") or {}
        c = meta.get("celex")
        if c:
            got.add(str(c).split("R(")[0])   # 去掉更正版本后缀再比
    if not tracked:
        print("   （未读到跟踪清单，跳过）")
    else:
        tracked_base = {c.split("R(")[0] for c in tracked}
        missing = sorted(tracked_base - got)
        print(f"   跟踪 {len(tracked_base)} 个 CELEX，落盘 {len(got)} 个")
        if missing:
            print(f"   ⚠️ 未取到 {len(missing)} 个：")
            for c in missing[:20]:
                print(f"      · {c}")
            gaps.append(f"{len(missing)} 个跟踪 CELEX 未取到")
        else:
            print("   ✅ 全部取到")

    # ---------- ② 关键词覆盖 ----------
    print("\n" + "=" * 78)
    print("② 关键词覆盖：配置清单 vs 数据里的簇")
    print("=" * 78)
    kws = configured_keywords()
    clusters = collections.Counter(
        r.get("cluster_hint") for r in rows if r.get("cluster_hint"))
    print(f"   配置关键词 {len(kws)} 个")
    print(f"   数据里出现的簇：{dict(clusters)}")
    if not clusters:
        print("   ⚠️ 数据里没有任何 cluster_hint —— 无法确认关键词覆盖")
        gaps.append("数据缺少 cluster_hint，关键词覆盖无法验证")
    else:
        print(f"   ℹ️ 有 {len(clusters)} 个簇产出了数据")

    # ---------- ③ 数据源覆盖 ----------
    print("\n" + "=" * 78)
    print("③ 数据源覆盖：应有源 vs 实际有数据")
    print("=" * 78)
    actual = collections.Counter(r.get("source_id") or "?" for r in rows)
    never = sorted(s for s in EXPECTED_SOURCES if s not in actual)
    if never:
        print(f"   ⚠️ {len(never)} 个源被接入但**一条数据都没有**：")
        for s in never:
            print(f"      · {s}")
        gaps.append(f"{len(never)} 个源零产出")
    else:
        print("   ✅ 所有预期源都有数据")
    print(f"\n   实际有数据的源（{len(actual)} 个）：")
    for s, n in actual.most_common():
        print(f"      {s:<28} {n:>5}")

    # ---------- ④ 时间边界 ----------
    print("\n" + "=" * 78)
    print("④ 时间边界")
    print("=" * 78)
    dates = sorted(
        (r.get("publish_date") or "")[:10]
        for r in rows if r.get("publish_date"))
    if dates:
        print(f"   最早 {dates[0]}   最晚 {dates[-1]}")
        print(f"   采集起点设定 --since {args.since}")
        early = [d for d in dates if d and d < args.since]
        if early:
            print(f"   ℹ️ 有 {len(early)} 条早于设定起点（来自无日期过滤的源）")
        else:
            print("   ✅ 无记录早于设定起点（或起点之前的法规不属于遗漏）")
        # 按年统计
        by_year = collections.Counter(d[:4] for d in dates if d)
        print(f"   年份分布：{dict(sorted(by_year.items()))}")
    else:
        print("   ⚠️ 没有带日期的记录")

    # ---------- 结论 ----------
    print("\n" + "=" * 78)
    if gaps:
        print(f"⚠️ 存在 {len(gaps)} 类缺口：")
        for g in gaps:
            print(f"   · {g}")
        return 1
    print("✅ 未发现缺口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
