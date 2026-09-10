"""相关性判定 —— 解决"搜到的不是我要的"。

为什么必须有这一层？
------------------
实测（2026-09-10）：用 `batter` 检索欧盟立法，返回的第一批结果是
    "battery-powered hold-open systems"（电池供电的门吸，建筑产品指令）
——相关性为零。

任何纯关键词检索都必然产生假阳性。本模块实现 sources/search-boundary.yaml
里定义的三段式判定：

    第一段 必修词  → 一条都不命中 → 直接丢弃（Recall 交给上游查询词保证）
    第二段 拒绝词  → 命中 → 直接丢弃（Precision 的主要来源）
    第三段 模糊词  → 命中 → 不丢弃，但标记 needs_human_review
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------- 规则（与 sources/search-boundary.yaml 的 relevance 段保持一致）----------
#
# 演进记录（2026-09-10，由真实采集数据驱动）：
#   第一版用纯子串匹配 "battery recycl"，结果把
#     · "Advanced Manufacturing Production Credit"（45X 最终规则）
#     · "Clean Vehicle Credits ... Critical Minerals and Battery..."
#     · "Notice of Final Determination on 2023 DOE Critical Materials List"
#   这三条**核心政策误杀了**；同时 "Battery and Electronics Recycling"
#   因为中间夹了 "and electronics" 也没匹配上。
#   → 改为「正则 + 有界间隔 + 上下文词」三段式，并把税收抵免类政策
#     降级为"人工复核"而非直接丢弃（宁可多一条待审，不可漏一条政策）。

# 第一段 A：强模式（正则，允许中间夹少量词）
STRONG_PATTERNS: list[str] = [
    r"batter\w*[\s\W]+(?:\w+[\s\W]+){0,5}?recycl",   # battery (and electronics) recycling
    r"recycl\w*[\s\W]+(?:\w+[\s\W]+){0,5}?batter",   # recycling of lithium-ion batteries
    r"电池[\s\S]{0,10}?回收",
    r"回收[\s\S]{0,10}?电池",
    r"退役电池", r"废旧电池", r"废电池", r"动力电池回收", r"梯次利用",
    r"再生利用", r"黑粉", r"black mass",
    r"end-of-life batter", r"spent batter", r"second[- ]life batter",
    r"repurpos", r"cathode recover",
    r"waste batter", r"batteries directive", r"batter\w*[\s\S]{0,25}regulation",
    r"regulation[\s\S]{0,25}batter", r"2023/1542",           # 欧盟电池法
    r"recycled content", r"battery passport",
    r"recycling efficiency", r"collection target",
    r"battery material", r"battery component", r"battery supply chain",
]

# 第二段 B：上下文词 —— 单独出现不算，必须与"锚点"共现
CONTEXT_TERMS: list[str] = [
    r"critical mineral", r"critical material", r"due diligence",
    r"extended producer responsibility", r"producer responsibility",
    r"resource recovery", r"material recovery", r"circular economy",
    r"生产者责任", r"综合利用", r"再生资源",
]
CONTEXT_ANCHORS: list[str] = [
    r"batter", r"lithium", r"cathode", r"anode", r"recycl",
    r"electric vehicle", r"energy storage", r"新能源汽车", r"储能",
]

# 第三段 C：形似相关但需人工裁决（税收抵免 / 能源条款类）
#   这类文档标题里往往不出现 "battery"，但正文/影响范围常涉及电池供应链，
#   直接丢弃会漏政策，因此标为 needs_human_review。
POLICY_MAYBE_TERMS: list[str] = [
    r"advanced manufacturing production credit", r"\b45x\b", r"\b45y\b", r"\b48e\b", r"\b48c\b",
    r"clean vehicle credit", r"clean hydrogen", r"energy property",
    r"advanced manufacturing investment credit", r"\b30d\b", r"\b25e\b",
    # 关键材料/矿产清单类：标题常不含 "battery"，但直接决定电池材料能否拿到激励
    r"critical minerals? list", r"critical materials? list",
    r"critical minerals?", r"critical materials?",
]

REJECT_IF_MATCH: list[str] = [
    # ⚠️ 实测假阳性来源
    "battery-powered", "battery operated", "batteridrevne", "battery charger",
    "纽扣电池", "电池供电", "电池充电器",
    # 非目标行业
    "启动电池", "consumer electronic batter", "hearing aid batter",
    # 非情报意图
    "电池概念股", "电池招聘", "电池价格行情",
]

HUMAN_REVIEW_MARKERS: list[str] = [
    "solid state batter", "sodium ion batter", "固态电池", "钠离子电池",
    "海外建厂", "回收价格",
]

_STRONG_RE = [re.compile(p, re.I) for p in STRONG_PATTERNS]
_CONTEXT_RE = [re.compile(p, re.I) for p in CONTEXT_TERMS]
_ANCHOR_RE = [re.compile(p, re.I) for p in CONTEXT_ANCHORS]
_MAYBE_RE = [re.compile(p, re.I) for p in POLICY_MAYBE_TERMS]


@dataclass
class RelevanceVerdict:
    relevant: bool
    score: float                                   # 0.0 ~ 1.0
    hits: list[str] = field(default_factory=list)  # 命中的必修词
    rejected_by: str | None = None                 # 命中的拒绝词
    needs_human_review: bool = False
    review_reason: str | None = None

    def __str__(self) -> str:
        if self.rejected_by:
            return f"❌ 拒绝（命中拒绝词: {self.rejected_by}）"
        if not self.relevant:
            return "❌ 拒绝（未命中任何必修词）"
        flag = "🟡 需人工复核" if self.needs_human_review else "✅ 相关"
        return f"{flag} score={self.score:.2f} hits={self.hits[:3]}"


def _contains(text: str, term: str) -> bool:
    """子串匹配；对纯英文词加宽松边界判断，避免误伤。"""
    if term.isascii():
        return term.lower() in text
    return term in text


def judge(text: str, title: str | None = None) -> RelevanceVerdict:
    """对一段文本（标题+正文）做相关性判定。

    判定顺序：
      1. 拒绝词命中 → 直接丢弃（最高优先级，防止 battery-powered 这类噪声）
      2. 强模式命中 → 相关
      3. 上下文词 + 锚点共现 → 相关
      4. 税优/能源条款类 → 相关但标记人工复核（宁可多审，不可漏政策）
      5. 都不命中 → 丢弃
    """
    if not text:
        return RelevanceVerdict(relevant=False, score=0.0)

    title_text = title or ""
    haystack = f"{title_text}\n{text}"

    # ---- 1) 拒绝词 ----
    lowered = haystack.lower()
    for bad in REJECT_IF_MATCH:
        if bad.lower() in lowered:
            # 例外：政策文本里出现"启动电池"是合法的（铅酸电池同属电池法规范围）
            if bad == "启动电池" and any(
                k in lowered for k in ("法规", "指令", "regulation", "directive", "回收")
            ):
                continue
            return RelevanceVerdict(relevant=False, score=0.0, rejected_by=bad)

    hits: list[str] = []

    # ---- 2) 强模式 ----
    for rx in _STRONG_RE:
        m = rx.search(haystack)
        if m:
            hits.append(m.group(0)[:40])

    # ---- 3) 上下文词 + 锚点 ----
    if not hits:
        if any(rx.search(haystack) for rx in _ANCHOR_RE):
            for rx in _CONTEXT_RE:
                m = rx.search(haystack)
                if m:
                    hits.append(f"ctx:{m.group(0)[:30]}")

    # ---- 4) 税优/能源条款类 → 人工复核 ----
    if not hits:
        maybe = next((rx.search(haystack) for rx in _MAYBE_RE if rx.search(haystack)), None)
        if maybe:
            return RelevanceVerdict(
                relevant=True,
                score=0.5,
                hits=[f"maybe:{maybe.group(0)[:30]}"],
                needs_human_review=True,
                review_reason="税优/能源条款类，可能涉及电池供应链，需人工裁决",
            )
        return RelevanceVerdict(relevant=False, score=0.0)

    # ---- 打分 ----
    score = min(1.0, 0.5 + 0.2 * len(hits))
    if any(rx.search(title_text) for rx in _STRONG_RE):
        score = min(1.0, score + 0.2)

    review = next((mk for mk in HUMAN_REVIEW_MARKERS if mk.lower() in lowered), None)

    return RelevanceVerdict(
        relevant=True,
        score=round(score, 3),
        hits=hits[:5],
        needs_human_review=review is not None,
        review_reason=(f"命中模糊标记「{review}」，需人工裁决" if review else None),
    )


def batch_judge(items: list[dict]) -> list[dict]:
    """批量判定。items: [{"id":..., "title":..., "text":...}]"""
    out = []
    for it in items:
        v = judge(it.get("text", ""), it.get("title"))
        out.append({**it, "relevant": v.relevant, "score": v.score,
                    "rejected_by": v.rejected_by,
                    "needs_human_review": v.needs_human_review,
                    "review_reason": v.review_reason})
    return out


if __name__ == "__main__":
    # 回归样本：全部来自 2026-09-10 的真实采集结果
    samples = [
        # 真阳性（第一版规则误杀，必须通过）
        ("Advanced Manufacturing Production Credit ... credit for the production and sale of "
         "battery components and critical minerals processing", "真阳性-45X最终规则"),
        ("Clean Vehicle Credits Under Sections 25E and 30D; Transfer of Credits; "
         "Critical Minerals and Battery Components", "真阳性-清洁车辆抵免"),
        ("Notice of Final Determination on 2023 DOE Critical Materials List", "真阳性-关键材料清单"),
        ("Request for Public Comment on Settlement Agreement for Battery and Electronics "
         "Recycling Inc. Superfund Site", "真阳性-夹词回收"),
        ("Regulation (EU) 2023/1542 on batteries and waste batteries", "真阳性-欧盟电池法"),
        ("格林美2025年年报：动力电池回收量达 8 万吨", "真阳性-中文"),
        # 真阴性（必须拒绝）
        ("Energy Conservation Program: Test Procedure for Battery Chargers", "真阴性-充电器"),
        ("Significant New Use Rules on Certain Chemical Substances (26-2)", "真阴性-化学品"),
        ("Air Plan Approval; Georgia; Second Period Regional Haze Plan", "真阴性-空气计划"),
        # 人工复核
        ("Section 45Y Clean Electricity Production Credit and Section 48E Clean Energy "
         "Investment Credit", "人工复核-能源条款"),
    ]
    print("相关性规则回归自检")
    print("-" * 78)
    for text, label in samples:
        print(f"{label:24s} → {judge(text)}")
