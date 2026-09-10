"""闭环迭代：结果 → 反推关键词/数据源 → 再采集 → 结果验证

与"单向采集"的区别
------------------
单向：配置 → 采集 → 出结果（结束）
闭环：结果 → 度量 → 反推 → 调整 → 再采集 → 用新结果验证调整是否正确

闭环怎么落地（关键设计）
------------------------
挖出来的新词**不直接进正式词表**（那会污染），也**不是只给人工看**（那还是单向）。
而是进入「**影子测试**」：

    Round 1  用正式词表采 → 度量 → 挖出候选词 C
    Round 2  拿 C 去采（结果标记 provisional，不并入正式库）→ 度量 C 的实测精确率
             用实测数据回答："这个自学习挖出来的词，到底有没有用？"
    产出     带实测证据的候选词清单 → 人工只需做最后确认

这样闭环是真的闭合了（系统自己验证自己的提议），
又不会自我污染（provisional 不并入正式库），
也不会死循环（轮次上限 + 收敛检测 + 冷却期，见 feedback.py 说明）。

用法
----
    py scripts/iterate_loop.py                    # 美国，最多 3 轮
    py scripts/iterate_loop.py --include-eu       # 含欧盟（慢，SPARQL ~10-60s/词）
    py scripts/iterate_loop.py --max-rounds 2
    py scripts/iterate_loop.py --reset            # 清空历史状态重跑
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.connectors import get_connector              # noqa: E402
from app.core.feedback import (                        # noqa: E402
    MAX_NEW_TERMS_PER_ROUND, MAX_ROUNDS, FeedbackEngine,
)
from app.core.relevance import judge                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
STATE_FILE = OUT / "feedback_state.json"
TAXONOMY = ROOT / "sources" / "keyword-taxonomy-eol-battery.yaml"
SOURCES = ROOT / "sources" / "policy-eu-us-eol-blackmass.yaml"

# 正式词表（外部锚点）—— 人工维护，系统不得自动改写
OFFICIAL_KEYWORDS = [
    "batteries", "waste batteries", "end-of-life vehicle", "vehicle recycling",
    "black mass", "waste shipment", "recycled content", "recycling efficiency",
    "producer responsibility", "lithium battery transport", "critical raw materials",
    "battery passport",
]

OFFICIAL_SOURCES = ["us_federal_register", "eu_eurlex"]

# US 机构池（按簇配对在配置里，这里取并集作为默认）
DEFAULT_AGENCIES = ["energy-department", "environmental-protection-agency",
                    "transportation-department"]


def load_plan() -> dict:
    taxonomy = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8")) or {}
    sources = yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}
    fr = sources.get("us", {}).get("federal_register", {})
    us_terms: dict[str, list[str]] = fr.get("terms_by_cluster", {})
    us_agencies: dict[str, list[str]] = fr.get("agencies_by_cluster", {})
    return {"us_terms": us_terms, "us_agencies": us_agencies,
            "taxonomy": taxonomy, "sources": sources}


# ============================================================
# 一轮采集（US）
# ============================================================
async def collect_us_round(keywords: list[str], cluster_of: dict[str, str],
                           agencies_of: dict[str, list[str]], since: str) -> list[dict]:
    records: list[dict] = []
    async with get_connector("us_federal") as conn:
        for kw in keywords:
            cluster = cluster_of.get(kw, "C?")
            agencies = agencies_of.get(cluster, DEFAULT_AGENCIES)
            try:
                items = await conn.fetch(terms=[kw], agencies=agencies,
                                         since=since, max_pages=2, per_page=50)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ 「{kw}」失败: {type(exc).__name__}")
                continue
            for it in items:
                v = judge(it.raw_text, it.source_title, scenario="policy")
                records.append({
                    "source_id": it.source_id,
                    "keyword": kw,
                    "cluster": cluster,
                    "evidence_id": it.evidence_id,
                    "title": it.source_title or "",
                    "url": it.source_url,
                    "text": it.raw_text[:1500],
                    "relevant": v.relevant,
                    "needs_human_review": v.needs_human_review,
                    "score": v.score,
                })
            print(f"    「{kw[:42]:<42}」→ {len(items):>4} 条")
    return records


# ============================================================
# 一轮采集（EU，可选）
# ============================================================
async def collect_eu_round(keywords: list[str], since: str) -> list[dict]:
    records: list[dict] = []
    async with get_connector("eur_lex") as conn:
        for kw in keywords:
            try:
                items = await conn.fetch(f"keyword:{kw}", since=since, limit=100)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ EU「{kw}」失败: {type(exc).__name__}")
                continue
            for it in items:
                v = judge(it.raw_text, it.source_title, scenario="policy")
                records.append({
                    "source_id": "eu_eurlex",
                    "keyword": kw,
                    "cluster": "C?",
                    "evidence_id": it.evidence_id,
                    "title": it.source_title or "",
                    "url": it.source_url,
                    "text": it.raw_text[:1500],
                    "relevant": v.relevant,
                    "needs_human_review": v.needs_human_review,
                    "score": v.score,
                })
            print(f"    EU「{kw[:38]:<38}」→ {len(items):>4} 条")
    return records


def write_candidates_file(candidates: dict[str, dict], round_tested: dict[str, dict]) -> None:
    """把候选词 + 影子测试实测结果写成配置，供人工确认。"""
    path = ROOT / "sources" / "keyword-candidates.yaml"
    lines = [
        "# ============================================================",
        "# 关键词候选池（系统自动生成 + 影子测试实测）",
        "# ------------------------------------------------------------",
        "# 工作方式：",
        "#   ① 系统从高相关文本里挖出候选术语（不直接进正式词表）",
        "#   ② 下一轮拿这些词去实际采集（结果标记 provisional，不并入正式库）",
        "#   ③ 用实测精确率证明这个词到底有没有用",
        "#   ④ **人工只需做最后确认** —— 把 status 改成 approved 即可进正式词表",
        "#",
        "# ⚠️ 未确认前不要加入 sources/keyword-taxonomy-eol-battery.yaml 的 discovery_terms",
        "# ============================================================",
        "",
        f"generated_at: {datetime.now().isoformat(timespec='seconds')}",
        f"total_candidates: {len(candidates)}",
        "",
        "candidates:",
    ]
    if not candidates:
        lines.append("  []")
    for term, c in sorted(candidates.items(),
                          key=lambda kv: kv[1]["doc_frequency"], reverse=True):
        measured = round_tested.get(term)
        lines.append(f"  - term: \"{term}\"")
        lines.append(f"    status: candidate          # candidate | shadow_tested | approved | rejected")
        lines.append(f"    doc_frequency: {c['doc_frequency']}")
        lines.append(f"    discovered_round: {c['round']}")
        lines.append(f"    example: \"{c['example'][:90]}\"")
        if measured:
            lines.append(f"    shadow_test:")
            lines.append(f"      raw: {measured['raw']}")
            lines.append(f"      relevant: {measured['relevant']}")
            lines.append(f"      precision: {measured['precision']:.3f}")
            lines.append(f"      novel: {measured['novel']}")
            lines.append(f"      verdict: {measured['verdict']}")
        else:
            lines.append(f"    shadow_test: null          # 尚未实测（下轮会测）")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  → 候选词清单已写入 {path.relative_to(ROOT)}")


def load_browser_records() -> list[dict]:
    """把浏览器抓取的证据接进闭环。

    为什么需要
    ----------
    被反爬拦截的站点（PHMSA/ECHA/CalRecycle/BCI）走的是 browser_capture 通道，
    产出在 outputs/browser_*.jsonl。它们是**站点级发现**而非关键词命中，
    所以：
      · 不带 `keyword` 字段（feedback.py 会归入 "(direct)"），避免污染关键词精确率
      · 必须补 `evidence_id`（url 的 sha1），否则每轮都被判为"新发现"，收敛判据失效
    """
    import hashlib

    files = sorted(OUT.glob("browser_*.jsonl"))
    if not files:
        return []

    records: list[dict] = []
    seen: set[str] = set()
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = r.get("url") or ""
            eid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
            if eid in seen:                     # 跨文件去重（同一 URL 可能被多次抓到）
                continue
            seen.add(eid)
            records.append({
                "source_id": r.get("source_id") or "browser_capture",
                "discovered_by": "browser_capture",   # 不设 keyword → 归入 (direct)
                "cluster": r.get("cluster") or "C?",
                "evidence_id": eid,
                "title": r.get("title") or "",
                "url": url,
                "text": (r.get("text") or "")[:1500],
                "relevant": bool(r.get("relevant")),
                "needs_human_review": bool(r.get("needs_human_review")),
                "score": r.get("score") or 0.0,
            })
    return records


async def main() -> int:
    ap = argparse.ArgumentParser(description="闭环迭代：结果反推关键词与数据源")
    ap.add_argument("--include-eu", action="store_true", help="含欧盟（慢）")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--since", default="2023-01-01")
    ap.add_argument("--reset", action="store_true", help="清空历史状态")
    ap.add_argument("--include-browser", action="store_true",
                    help="并入浏览器抓取的证据（outputs/browser_*.jsonl，被反爬站点）")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("已清空历史状态")

    plan = load_plan()
    cluster_of = {t: cid for cid, terms in plan["us_terms"].items() for t in terms}
    for d in (plan["taxonomy"].get("discovery_terms") or []):
        cluster_of.setdefault(d["term"], d["cluster"])

    engine = FeedbackEngine(STATE_FILE, known_keywords=OFFICIAL_KEYWORDS,
                            known_sources=OFFICIAL_SOURCES)

    log: list[str] = []
    round_tested: dict[str, dict] = {}
    baseline = OFFICIAL_KEYWORDS

    for round_no in range(1, args.max_rounds + 1):
        is_shadow = round_no > 1
        keywords = baseline if not is_shadow else list(engine.state["candidate_terms"].keys())[
            -(MAX_NEW_TERMS_PER_ROUND * 2):]
        if is_shadow and not keywords:
            print("\n无候选词可测试，提前结束")
            break

        label = "影子测试轮（候选词实测）" if is_shadow else "基线轮（正式词表）"
        print(f"\n{'=' * 96}\n 第 {round_no} 轮 · {label}\n{'=' * 96}")
        print(f"  关键词 {len(keywords)} 个：" + ", ".join(keywords[:8])
              + (" …" if len(keywords) > 8 else ""))

        records = await collect_us_round(keywords, cluster_of, plan["us_agencies"], args.since)
        if args.include_eu:
            records += await collect_eu_round(keywords, args.since)
        if args.include_browser:
            br = load_browser_records()
            print(f"\n  浏览器通道并入 {len(br)} 条（被反爬站点）")
            records += br

        obs = engine.observe(records, round_no)
        print(f"\n  观测：{obs['total_records']} 条记录，其中 {obs['new_novel']} 条为新条目")

        report = engine.analyze(round_no)

        # 影子轮：结算候选词的实测表现
        if is_shadow:
            per_kw: dict[str, dict] = defaultdict(lambda: {"raw": 0, "relevant": 0, "novel": 0})
            for r in records:
                k = r["keyword"]
                per_kw[k]["raw"] += 1
                per_kw[k]["relevant"] += 1 if r["relevant"] else 0
            for s in engine.pair_stats():
                if s.keyword in per_kw:
                    per_kw[s.keyword]["novel"] = s.novel
            for k, v in per_kw.items():
                p = v["relevant"] / v["raw"] if v["raw"] else 0.0
                # 判定阶梯（实测校正 2026-09-10）：
                # 初版只用一个门槛（raw>=30 且 precision>=0.10）→ 把实测精确率 40% 的
                # "rechargeable lithium" 判成了 insufficient，明显不合理：
                # **候选词本来就不可能一上来就有几百条**，用它跟正式词比样本量是错的。
                if v["raw"] == 0:
                    verdict = "no_results"
                elif p >= 0.15 and v["raw"] >= 15:
                    verdict = "recommend_approve"          # 精确率够，直接建议采纳
                elif p >= 0.10 and v["raw"] >= 10:
                    verdict = "promising_needs_more"       # 有潜力，样本偏少
                elif p < 0.05 and v["raw"] >= 30:
                    verdict = "recommend_reject"
                else:
                    verdict = "insufficient"
                round_tested[k] = {**v, "precision": p, "verdict": verdict}

        actions = getattr(engine, "_pending_actions", [])
        applied = engine.apply(actions, round_no)
        print()
        print(engine.render(report, actions, []))

        log.append(f"## 第 {round_no} 轮（{label}）\n\n"
                   f"- 记录 {obs['total_records']} 条，新条目 {obs['new_novel']}\n"
                   f"- 边际新发现率 {report.novel_rate:.2%}\n"
                   f"- 收敛：{'是' if report.converged else '否'}（{report.reason}）\n"
                   f"- 动作：调升 {applied['boosted']}｜调降 {applied['demoted']}｜"
                   f"停用词 {applied['retired']}｜饱和 {len(applied['saturated'])}\n")

        # 基线轮结束时挖候选词
        if not is_shadow:
            cands = engine.mine_candidate_terms(records, round_no,
                                                top_n=MAX_NEW_TERMS_PER_ROUND)
            if cands:
                print(f"\n  🔍 从高相关文本里挖出 {len(cands)} 个候选术语"
                      f"（进候选池，下一轮将拿去实测）")

        if report.converged:
            print(f"\n  ✅ 收敛：{report.reason}")
            break

    # 外部锚点健康检查（防回音室）
    anchor = engine.check_anchor_share(OFFICIAL_KEYWORDS)
    print("\n" + "=" * 96)
    print(" 外部锚点检查（防回音室）")
    print("=" * 96)
    for k, v in anchor.items():
        print(f"  {k:<20} {v}")
    if anchor["warning"]:
        print(f"\n  ⚠️ {anchor['warning']}")

    write_candidates_file(engine.state["candidate_terms"], round_tested)

    (OUT / "iteration_log.md").write_text(
        "# 闭环迭代日志\n\n" + f"生成：{datetime.now():%Y-%m-%d %H:%M}\n\n"
        + "\n".join(log)
        + "\n## 外部锚点检查\n\n```json\n"
        + json.dumps(anchor, ensure_ascii=False, indent=2) + "\n```\n",
        encoding="utf-8")
    print(f"  → 迭代日志 {ROOT / 'outputs' / 'iteration_log.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
