"""源 × 关键词 双向反馈引擎 —— 把单向采集变成闭环，且不会死循环。

问题
----
原来的流程是单向的：
    配置关键词 → 配数据源 → 采集 → 出结果 → （结束）
结果只被人看，**不回流去修正关键词和数据源**。所以：
    · 某个源明明有料，但因为词没写对，一直采不到 → 永远发现不了
    · 某个词在某个源里根本不存在 → 每轮都在白跑，浪费配额
    · "黑粉"这个词在法规里叫 "intermediate wastes from battery recycling"
      → 靠人工想词，想不到就永远漏

闭环设计
--------
          ┌──────────────────────────────────────────┐
          │                                          │
          ▼                                          │
   ① 关键词×源 → ② 采集 → ③ 判定 → ④ 度量 → ⑤ 反推 ─┘
                                        │
                                        ├─ 词维度：哪个词有效/无效/已饱和
                                        ├─ 源维度：哪个源高产/低产/不覆盖
                                        └─ 关系维度：源×主题 覆盖矩阵（路由表）

反推产出三类动作（全部可逆、全部留痕）：
    boost / demote 源权重     ← 按边际产出（novel_rate）而非命中量
    keep / retire  关键词     ← 按精确率与边际产出
    mine           新候选词   ← 从高相关文本里挖术语，进候选池（**不直接进正式表**）

⚠️ 防死循环（这是本模块最重要的部分）
------------------------------------
闭环最大的风险是**自我强化**：只用自己挖出来的词去搜 → 结果越来越窄 → 回音室，
或者 A 源挖出新词 → 新词又命中 A 源 → 无限迭代。

六道闸门（缺一不可）：

  1. **硬轮次上限** MAX_ROUNDS=3
     不管收敛与否，到轮次就停。这是最后的保险丝。

  2. **收敛判据** novel_rate < 2% 连续 2 轮 → 判定收敛，提前停
     衡量的是"这轮还带回了多少新东西"，而不是"这轮跑了多少"。

  3. **外部锚点词表**（防回音室）
     候选词池只允许转入正式词表的**至多一半**；另一半必须来自
     外部权威词表（EuroVoc / 法规术语表 / 材料名），不参与自学习。
     → 保证系统的世界不会自我封闭。

  4. **每轮新增词上限** MAX_NEW_TERMS_PER_ROUND=8
     防止一轮涌入几百个词导致下一轮爆炸。

  5. **冷却期** COOLDOWN_ROUNDS=2
     同一个 (源, 词) 组合的权重在冷却期内只能调整一次，防止来回震荡。

  6. **人工闸门**
     自动只能把词放进「候选池」；进「正式词表」必须人工确认。
     删除数据源同理——自动只降权，不删除。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ============================================================
# 防死循环参数（集中管理，便于审计）
# ============================================================
MAX_ROUNDS = 3                    # 硬轮次上限
MAX_NEW_TERMS_PER_ROUND = 8       # 每轮最多新增候选词
COOLDOWN_ROUNDS = 2               # 权重调整冷却期（轮）
NOVEL_RATE_CONVERGENCE = 0.02     # 边际新发现率低于 2% 视为饱和
CONVERGENCE_STREAK = 2            # 连续两轮低于阈值 → 收敛
MIN_PRECISION_TO_KEEP = 0.05      # 精确率低于 5% 的词考虑停用
MIN_RAW_TO_JUDGE = 20             # 样本量不足不做判断（防小样本误判）
EXTERNAL_ANCHOR_SHARE = 0.5       # 正式词表中外部锚点词的最低占比

STOPWORDS = set("""
a an the and or of for to in on at by with from as is are was were be been being
this that these those it its such other any all more most less least than then
not no nor only own same so too very can will just should now under over between
act acts code part parts section sections rule rules title chapter subpart
united states federal register document notice proposed final rule
""".split())

# 核心锚点：候选词必须含其中至少一个，才算"粘在业务上"
# 与 DOMAIN_ANCHORS 的区别：DOMAIN_ANCHORS 允许 hazardous/waste/materials 这类泛词，
# 实测证明那会挖出公文套话；CORE_ANCHORS 只认业务核心词。
CORE_ANCHORS = {
    "battery", "batteries", "lithium", "li-ion", "cathode", "anode", "black",
    "shredd", "recycl", "cobalt", "nickel", "graphite", "electrolyte",
    "vehicle", "automotive", "elv", "depollution", "dismantl", "passport",
}

# 领域锚点：候选词里至少要有一个，否则不认为是本领域术语
DOMAIN_ANCHORS = {
    "battery", "batteries", "cell", "cells", "lithium", "li-ion", "cathode", "anode",
    "black", "mass", "recycl", "recovery", "material", "materials", "mineral", "minerals",
    "cobalt", "nickel", "manganese", "graphite", "electrolyte", "module", "pack",
    "vehicle", "vehicles", "automotive", "elv", "shredd", "hazardous", "waste",
    "efficiency", "content", "passport", "footprint", "diligence", "producer",
    "collect", "collection", "depollution", "dismantl", "transport", "shipment",
}

# ⚠️ 通用官文黑名单（实测踩坑 2026-09-10）
#    第一版挖掘把 Federal Register 的**公文套话**当成了领域术语：
#      hazardous materials / hazardous air pollutants / department transportation /
#      materials safety / permits hazardous …
#    它们含"领域锚点"（hazardous/materials/transport），但完全是通用监管词汇，
#    拿去搜索只会带回来一堆无关文件（影子测试实测精确率极低）。
#    教训：**"含领域词" ≠ "是领域术语"**。必须显式排除公文高频套话。
GENERIC_BLOCKLIST = {
    "hazardous materials", "hazardous material", "hazardous air", "hazardous air pollutants",
    "hazardous substances", "hazardous waste", "hazardous waste management",
    "department transportation", "department energy", "department commerce",
    "materials safety", "materials safety board", "safety administration",
    "transportation hazardous", "permits hazardous", "hazardous permits",
    "solid waste", "solid waste management", "waste management",
    "air pollutants", "air pollution", "water pollution", "environmental protection",
    "federal register", "united states", "public comment", "comment request",
    "information collection", "regulatory review", "notice proposed",
    "proposed rule", "final rule", "draft guidance", "public hearing",
    "national emission standards", "new source performance",
    "material recovery facility", "recovered materials", "recycling market",
}

# 真正有价值的术语长什么样（用于正例提示，不参与匹配，只用于人工复核时对照）
POSITIVE_TERM_HINTS = [
    "black mass", "shredder fines", "spent batteries", "battery passport",
    "recycled content", "recycling efficiency", "depollution", "second life",
    "battery dismantling", "intermediate waste", "battery stewardship",
    "state of charge", "damaged defective recalled",
]


# ============================================================
# 数据结构
# ============================================================
@dataclass
class PairStat:
    """单个 (数据源, 关键词) 组合的统计。"""
    source_id: str
    keyword: str
    raw: int = 0            # 返回条数（累积）
    relevant: int = 0       # 判定相关（累积）
    novel: int = 0          # 其中"没见过的新条目"（累积）
    rounds_seen: list[int] = field(default_factory=list)
    last_adjusted_round: int = -99
    # 本轮增量：{round_no: {"raw": n, "novel": n}}
    # why 必须按轮存：累积比率是**滞后指标**，会长期停留在高位
    # （旧条目没变但分母持续增长），导致收敛判据永远不触发。
    rounds: dict = field(default_factory=dict)

    @property
    def precision(self) -> float:
        return self.relevant / self.raw if self.raw else 0.0

    @property
    def novel_rate(self) -> float:
        """累积边际新发现率（滞后指标，仅作参考）。"""
        return self.novel / self.raw if self.raw else 0.0

    def round_novel_rate(self, round_no: int) -> float:
        """**本轮**边际新发现率 —— 收敛判据与源/词调权都应当用这个。"""
        r = self.rounds.get(str(round_no)) or self.rounds.get(round_no) or {}
        raw = r.get("raw", 0)
        return (r.get("novel", 0) / raw) if raw else 0.0

    @property
    def key(self) -> str:
        return f"{self.source_id}||{self.keyword}"


@dataclass
class Action:
    kind: str               # boost_source | demote_source | keep_keyword |
                            # retire_keyword | mine_terms | saturate_pair | route_note
    target: str
    reason: str
    magnitude: float = 0.0
    reversible: bool = True
    requires_human: bool = False


@dataclass
class ConvergeReport:
    converged: bool
    reason: str
    round_no: int
    novel_rate: float
    streak: int


# ============================================================
# 引擎
# ============================================================
class FeedbackEngine:
    """源×关键词 的闭环反馈引擎。

    用法（每轮结束时调用一次 observe + analyze）：
        eng = FeedbackEngine(state_path)
        eng.observe(records, round_no=1)
        report = eng.analyze(round_no=1)
        if report.converged: stop()
        eng.apply(report.actions)      # 写回候选词池 / 权重建议
    """

    def __init__(self, state_path: Path | str, known_keywords: Iterable[str] = (),
                 known_sources: Iterable[str] = ()) -> None:
        self.state_path = Path(state_path)
        self.state: dict[str, Any] = self._load()
        self.state.setdefault("pairs", {})
        self.state.setdefault("seen_evidence", [])
        self.state.setdefault("history", [])
        self.state.setdefault("source_weight", {})
        self.state.setdefault("keyword_status", {})     # active | retired | candidate
        self.state.setdefault("candidate_terms", {})
        self._seen: set[str] = set(self.state["seen_evidence"])

        for k in known_keywords:
            self.state["keyword_status"].setdefault(k, "active")
        for s in known_sources:
            self.state["source_weight"].setdefault(s, 1.0)

    # ---------- 持久化 ----------
    def _load(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def save(self) -> None:
        self.state["seen_evidence"] = sorted(self._seen)[-50000:]   # 防止无限膨胀
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- ① 观测 ----------
    def observe(self, records: list[dict], round_no: int) -> dict[str, int]:
        """把一轮采集结果喂进来，更新统计。

        records 需含：source_id / keyword / evidence_id / relevant
        novel 的判定依据是证据 id 是否在**历史所有轮次**里出现过 ——
        这是"边际产出"的度量，也是收敛判据的基础。
        """
        new_novel = 0
        for r in records:
            src = r.get("source_id") or "unknown"
            # keyword 可能没有（如 CELEX 精确跟踪），用 source 兜底命名
            kw = r.get("keyword") or r.get("discovered_by") or "(direct)"
            key = f"{src}||{kw}"
            stat = self.state["pairs"].get(key)
            if stat is None:
                stat = asdict(PairStat(source_id=src, keyword=kw))
                self.state["pairs"][key] = stat

            stat["raw"] = stat.get("raw", 0) + 1
            if r.get("relevant"):
                stat["relevant"] = stat.get("relevant", 0) + 1

            # 本轮增量（收敛判据的基础）
            rstat = stat.setdefault("rounds", {}).setdefault(
                str(round_no), {"raw": 0, "novel": 0})
            rstat["raw"] += 1

            eid = str(r.get("evidence_id") or "")
            if eid and eid not in self._seen:
                self._seen.add(eid)
                stat["novel"] = stat.get("novel", 0) + 1
                rstat["novel"] += 1
                new_novel += 1

            rs = stat.setdefault("rounds_seen", [])
            if round_no not in rs:
                rs.append(round_no)

        return {"new_novel": new_novel, "total_records": len(records)}

    # ---------- ② 度量 ----------
    def pair_stats(self) -> list[PairStat]:
        out = []
        for k, v in self.state["pairs"].items():
            out.append(PairStat(
                source_id=v["source_id"], keyword=v["keyword"],
                raw=v.get("raw", 0), relevant=v.get("relevant", 0),
                novel=v.get("novel", 0),
                rounds_seen=v.get("rounds_seen", []),
                last_adjusted_round=v.get("last_adjusted_round", -99),
                rounds=v.get("rounds", {}),
            ))
        return out

    def source_view(self, round_no: int | None = None) -> dict[str, dict[str, float]]:
        """按源聚合（跨关键词）。

        round_no 给定时，novel_rate 是**本轮**边际新发现率（调权用这个）；
        否则是累积值（仅作参考，是滞后指标）。
        """
        agg: dict[str, dict[str, float]] = defaultdict(
            lambda: {"raw": 0, "relevant": 0, "novel": 0, "round_raw": 0, "round_novel": 0})
        for s in self.pair_stats():
            a = agg[s.source_id]
            a["raw"] += s.raw
            a["relevant"] += s.relevant
            a["novel"] += s.novel
            if round_no is not None:
                r = s.rounds.get(str(round_no)) or {}
                a["round_raw"] += r.get("raw", 0)
                a["round_novel"] += r.get("novel", 0)
        for a in agg.values():
            a["precision"] = a["relevant"] / a["raw"] if a["raw"] else 0.0
            a["novel_rate"] = a["novel"] / a["raw"] if a["raw"] else 0.0
            a["round_novel_rate"] = (a["round_novel"] / a["round_raw"]
                                      if a["round_raw"] else 0.0)
        return dict(agg)

    def keyword_view(self, round_no: int | None = None) -> dict[str, dict[str, float]]:
        """按关键词聚合（跨源）—— 回答"这个词到底有效吗"。"""
        agg: dict[str, dict[str, float]] = defaultdict(
            lambda: {"raw": 0, "relevant": 0, "novel": 0, "round_raw": 0, "round_novel": 0})
        for s in self.pair_stats():
            a = agg[s.keyword]
            a["raw"] += s.raw
            a["relevant"] += s.relevant
            a["novel"] += s.novel
            if round_no is not None:
                r = s.rounds.get(str(round_no)) or {}
                a["round_raw"] += r.get("raw", 0)
                a["round_novel"] += r.get("novel", 0)
        for a in agg.values():
            a["precision"] = a["relevant"] / a["raw"] if a["raw"] else 0.0
            a["novel_rate"] = a["novel"] / a["raw"] if a["raw"] else 0.0
            a["round_novel_rate"] = (a["round_novel"] / a["round_raw"]
                                      if a["round_raw"] else 0.0)
        return dict(agg)

    def coverage_matrix(self) -> dict[str, dict[str, int]]:
        """源 × 关键词 覆盖矩阵 —— 这是"要采某主题该去哪个源"的路由表。

        反推数据源的核心依据：某主题在 A 源有命中、在 B 源为 0
        → 说明 B 源不覆盖该主题，别再浪费配额。
        """
        m: dict[str, dict[str, int]] = defaultdict(dict)
        for s in self.pair_stats():
            m[s.source_id][s.keyword] = s.relevant
        return {k: dict(v) for k, v in m.items()}

    # ---------- ③ 反推：动作决策 ----------
    def analyze(self, round_no: int) -> ConvergeReport:
        """基于统计产出动作清单 + 收敛判断。"""
        actions: list[Action] = []
        stats = self.pair_stats()
        srcs = self.source_view(round_no)         # 本轮边际
        kws = self.keyword_view(round_no)

        # ---- 源维度 ----
        for src, a in srcs.items():
            if a["raw"] < MIN_RAW_TO_JUDGE:
                continue
            # 用本轮边际：某源累积边际可能很高，但本轮已无新增 → 应该降权
            if a["round_novel_rate"] < 0.01 and a["precision"] < 0.05:
                actions.append(Action(
                    "demote_source", src,
                    f"本轮边际 {a['round_novel_rate']:.1%}、精确率 {a['precision']:.1%}，"
                    f"该源对本主题已无增量", magnitude=-0.2))
            elif a["round_novel_rate"] >= 0.10:
                actions.append(Action(
                    "boost_source", src,
                    f"本轮边际 {a['round_novel_rate']:.1%}，持续带回新信息",
                    magnitude=0.2))

        # ---- 关键词维度 ----
        for kw, a in self.keyword_view().items():
            if a["raw"] < MIN_RAW_TO_JUDGE:
                continue
            if a["precision"] < MIN_PRECISION_TO_KEEP and a["round_novel"] == 0:
                actions.append(Action(
                    "retire_keyword", kw,
                    f"精确率 {a['precision']:.1%} 且本轮零边际产出，建议停用"))
            elif a["precision"] >= 0.30 and a["round_novel_rate"] >= 0.05:
                actions.append(Action(
                    "keep_keyword", kw,
                    f"精确率 {a['precision']:.1%} + 本轮边际 "
                    f"{a['round_novel_rate']:.1%}，保持"))

        # ---- 组合维度：饱和 ----
        # ⚠️ 用**本轮**边际判饱和，不用累积（同收敛判据的理由）
        for s in stats:
            if s.raw >= MIN_RAW_TO_JUDGE and s.rounds_seen and \
                    s.rounds_seen.count(max(s.rounds_seen)) and \
                    s.round_novel_rate(round_no) < NOVEL_RATE_CONVERGENCE:
                if round_no - s.last_adjusted_round >= COOLDOWN_ROUNDS:
                    actions.append(Action(
                        "saturate_pair", s.key,
                        f"连续 {len(s.rounds_seen)} 轮、本轮边际 "
                        f"{s.round_novel_rate(round_no):.1%} 已饱和",
                        reversible=True))

        # ---- 收敛判断 ----
        # ⚠️ 必须用**本轮**边际新发现率，不能用累积比率。
        #    累积比率是滞后指标：旧条目没变但分母持续增长，
        #    它会长期停留在高位 → 阈值 2% 永远触发不了 → 收敛判据形同虚设。
        #    （实测 2026-09-10：第 3 轮真实边际 0/98 = 0%，累积却显示 59.7%，
        #      报告说"仍有增量"，而实际上已经完全不饱和了。）
        round_raw = sum(
            (s.rounds.get(str(round_no)) or {}).get("raw", 0) for s in stats)
        round_novel = sum(
            (s.rounds.get(str(round_no)) or {}).get("novel", 0) for s in stats)
        rate = (round_novel / round_raw) if round_raw else 0.0
        hist = self.state["history"]
        streak = 1 if (hist and hist[-1].get("novel_rate", 1.0) < NOVEL_RATE_CONVERGENCE
                       and rate < NOVEL_RATE_CONVERGENCE) else 0

        if round_no >= MAX_ROUNDS:
            report = ConvergeReport(True, f"达到硬轮次上限 {MAX_ROUNDS}", round_no, rate, streak)
        elif streak >= CONVERGENCE_STREAK:
            report = ConvergeReport(True, f"连续 {streak} 轮边际新发现 <{NOVEL_RATE_CONVERGENCE:.0%}",
                                    round_no, rate, streak)
        else:
            report = ConvergeReport(False, f"边际新发现 {rate:.1%}，仍有增量", round_no, rate, streak)

        self.state["history"].append({
            "round": round_no, "novel_rate": rate, "converged": report.converged,
            "reason": report.reason,
        })
        self._pending_actions = actions
        return report

    # ---------- ④ 执行（全部可逆 + 留痕）----------
    def apply(self, actions: list[Action], round_no: int) -> dict[str, Any]:
        applied: dict[str, Any] = {"boosted": [], "demoted": [], "retired": [],
                                   "saturated": [], "needs_human": []}
        for a in actions:
            if a.kind == "boost_source":
                w = self.state["source_weight"].get(a.target, 1.0)
                self.state["source_weight"][a.target] = min(2.0, w + a.magnitude)
                applied["boosted"].append(a.target)
            elif a.kind == "demote_source":
                w = self.state["source_weight"].get(a.target, 1.0)
                self.state["source_weight"][a.target] = max(0.2, w + a.magnitude)
                applied["demoted"].append(a.target)
            elif a.kind == "retire_keyword":
                # ⚠️ 只标记 retired，不删除；人工可一键恢复
                self.state["keyword_status"][a.target] = "retired_auto"
                applied["retired"].append(a.target)
            elif a.kind == "saturate_pair":
                pair = self.state["pairs"].get(a.target)
                if pair is not None:
                    pair["last_adjusted_round"] = round_no
                applied["saturated"].append(a.target)
            if a.requires_human:
                applied["needs_human"].append(f"{a.kind}:{a.target}")
        self.save()
        return applied

    # ---------- ⑤ 术语挖掘（反推关键词）----------
    def mine_candidate_terms(self, records: list[dict], round_no: int,
                            top_n: int = MAX_NEW_TERMS_PER_ROUND) -> list[dict]:
        """从高相关文本里挖新术语，进「候选池」。

        ⚠️ 三重限制，防止自我强化：
          1. 只从 relevant=True 的文本挖（不学噪声）
          2. 每轮最多 top_n 个
          3. 只写候选池；进正式词表需人工确认（requires_human=True）

        做法：1-3 元词组 + 文档频次 + 领域锚点过滤（无自研 NLP 依赖）
        """
        known = set(self.state["keyword_status"]) | set(self.state["candidate_terms"])
        df = Counter()
        examples: dict[str, str] = {}
        # ⚠️ 只从"标题本身就含电池线索"的记录里挖词。
        #    理由：正文（1500 字符）里全是公文套话，噪声极大；
        #    而标题含电池线索的记录，其正文里的术语才更可能是领域术语。
        TITLE_ANCHOR = re.compile(
            r"batter|lithium|black mass|recycl|vehicle|electric|spent|waste batter",
            re.I)

        for r in records:
            if not r.get("relevant"):
                continue
            title = (r.get("title") or "")
            if not TITLE_ANCHOR.search(title):
                continue
            tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", title.lower())
            seen_ngrams = set()
            for n in (2, 3):
                for i in range(len(tokens) - n + 1):
                    gram_tokens = tokens[i:i + n]
                    if any(t in STOPWORDS for t in gram_tokens):
                        continue
                    gram = " ".join(gram_tokens)
                    # ① 必须含领域锚点
                    if not any(any(g.startswith(a) for a in DOMAIN_ANCHORS)
                               for g in gram_tokens):
                        continue
                    # ② 不能是通用公文套话（实测踩坑后的修正）
                    if gram in GENERIC_BLOCKLIST:
                        continue
                    # ③ 必须至少含一个"电池/车辆/回收"级别的核心锚点，
                    #    而不是"hazardous/waste/materials"这类泛词
                    if not any(any(g.startswith(a) for a in CORE_ANCHORS)
                               for g in gram_tokens):
                        continue
                    if gram in seen_ngrams:
                        continue
                    seen_ngrams.add(gram)
                    df[gram] += 1
                    examples.setdefault(gram, title[:120])

        # 已有词或已有候选词的变体不入池
        candidates = []
        for gram, freq in df.most_common(200):
            if freq < 3 or gram in known:
                continue
            if any(gram in k or k in gram for k in known if len(k) > 6):
                continue
            candidates.append({
                "term": gram,
                "doc_frequency": freq,
                "round": round_no,
                "example": examples.get(gram, ""),
                "status": "candidate",
                "requires_human": True,
                "source": "auto_mined_from_relevant_records",
            })
            if len(candidates) >= top_n:
                break

        for c in candidates:
            self.state["candidate_terms"][c["term"]] = c
        self.save()
        return candidates

    # ---------- 外部锚点校验（防回音室）----------
    def check_anchor_share(self, official_keywords: Iterable[str]) -> dict[str, Any]:
        """检查正式词表里有多少来自"外部权威词表"，防止系统自我封闭。

        规则：外部锚点词占比不得低于 EXTERNAL_ANCHOR_SHARE（默认 50%）。
        低于阈值 → 报警，提示必须从法规术语表/EuroVoc 补充外部词，而不是继续自学习。
        """
        official = list(official_keywords)
        auto = [k for k, v in self.state["keyword_status"].items()
                if v.startswith("auto") or k in self.state["candidate_terms"]]
        anchor = [k for k in official if k not in auto]
        share = len(anchor) / len(official) if official else 1.0
        return {
            "official_keywords": len(official),
            "external_anchor": len(anchor),
            "auto_derived": len(auto),
            "anchor_share": round(share, 3),
            "healthy": share >= EXTERNAL_ANCHOR_SHARE,
            "warning": (None if share >= EXTERNAL_ANCHOR_SHARE else
                        f"外部锚点占比 {share:.0%} 低于 {EXTERNAL_ANCHOR_SHARE:.0%}，"
                        f"存在回音室风险：请从法规术语表/EuroVoc 补充外部词，"
                        f"而不是继续依赖自学习挖词"),
        }

    # ---------- 报告 ----------
    def render(self, report: ConvergeReport, actions: list[Action],
               candidates: list[dict]) -> str:
        lines = [
            "=" * 96,
            f" 闭环反馈报告 · 第 {report.round_no} 轮",
            "=" * 96,
            f" 收敛状态：{'✅ 已收敛' if report.converged else '🔄 继续迭代'}"
            f"  —— {report.reason}",
            f" 本轮边际新发现率：{report.novel_rate:.1%}"
            f"   ← 收敛判据用这个（不是累积比率）",
            "",
            " 【源维度】",
            f"  {'source':<28}{'raw':>6}{'rel':>6}{'novel':>7}{'精确率':>9}"
            f"{'本轮边际':>10}{'累积':>8}",
            "  " + "-" * 76,
        ]
        for src, a in sorted(self.source_view(report.round_no).items(),
                             key=lambda kv: kv[1]["round_novel_rate"], reverse=True)[:12]:
            lines.append(f"  {src:<28}{int(a['raw']):>6}{int(a['relevant']):>6}"
                         f"{int(a['novel']):>7}{a['precision']:>8.1%}"
                         f"{a['round_novel_rate']:>10.1%}{a['novel_rate']:>8.1%}")

        lines += ["", " 【关键词维度】（只列样本量足够的）"]
        lines.append(f"  {'keyword':<34}{'raw':>6}{'rel':>6}{'novel':>7}{'精确率':>9}"
                     f"{'本轮边际':>10}{'累积':>8}")
        lines.append("  " + "-" * 82)
        for kw, a in sorted(self.keyword_view(report.round_no).items(),
                            key=lambda kv: kv[1]["raw"], reverse=True):
            if a["raw"] < MIN_RAW_TO_JUDGE:
                continue
            lines.append(f"  {kw[:33]:<34}{int(a['raw']):>6}{int(a['relevant']):>6}"
                         f"{int(a['novel']):>7}{a['precision']:>8.1%}"
                         f"{a['round_novel_rate']:>10.1%}{a['novel_rate']:>8.1%}")

        lines += ["", " 【反推动作】"]
        if not actions:
            lines.append("  （无）")
        for a in actions:
            flag = "🔒需人工" if a.requires_human else ("↩可逆" if a.reversible else "")
            lines.append(f"  · {a.kind:<16} {a.target[:44]:<46} {a.reason} {flag}")

        if candidates:
            lines += ["", f" 【新候选词 {len(candidates)} 个】（进候选池，需人工确认后才进正式词表）"]
            for c in candidates:
                lines.append(f"  · {c['term']:<34} 频次={c['doc_frequency']:<3} "
                             f"例：{c['example'][:44]}")

        lines += ["", " 【防死循环状态】",
                  f"  · 轮次 {report.round_no}/{MAX_ROUNDS}",
                  f"  · 每轮新增词上限 {MAX_NEW_TERMS_PER_ROUND}",
                  f"  · 权重调整冷却期 {COOLDOWN_ROUNDS} 轮",
                  f"  · 收敛阈值 边际新发现 <{NOVEL_RATE_CONVERGENCE:.0%} 连续 {CONVERGENCE_STREAK} 轮"]
        return "\n".join(lines)
