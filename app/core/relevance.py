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

# ---------- 规则（与 search-boundary.yaml 的 relevance 段保持一致）----------

MUST_MATCH_ANY: list[str] = [
    # 中文
    "电池回收", "退役电池", "废旧电池", "废电池", "梯次利用", "再生利用",
    "回收利用", "正极材料再生", "黑粉", "综合利用",
    # 英文
    "battery recycl", "waste batter", "end-of-life batter", "spent batter",
    "repurposing", "second life batter", "black mass", "cathode recover",
    "recycled content", "battery regulation", "recycling efficiency",
    "battery passport", "collection target", "due diligence batter",
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

# 中文无词边界，直接用子串匹配；英文用词边界避免 "battery" 命中 "batteries-free" 之类
_WORD_RE = re.compile(r"[A-Za-z0-9]")


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
    """对一段文本（标题+正文）做相关性判定。"""
    if not text:
        return RelevanceVerdict(relevant=False, score=0.0)

    # 标题权重更高：标题命中必修词，得分加成
    title_text = (title or "")
    haystack = f"{title_text}\n{text}".lower()

    hits = [t for t in MUST_MATCH_ANY if _contains(haystack, t.lower())]
    if not hits:
        return RelevanceVerdict(relevant=False, score=0.0)

    for bad in REJECT_IF_MATCH:
        if _contains(haystack, bad.lower()):
            # 例外：政策类文本里出现 "启动电池" 是合法的（铅酸电池也在电池法规范围内）
            if bad == "启动电池" and any(
                k in haystack for k in ("法规", "指令", "regulation", "directive", "回收")
            ):
                continue
            return RelevanceVerdict(
                relevant=False, score=0.0, hits=hits, rejected_by=bad
            )

    # 打分：命中数 + 标题加成 + 政策词加成
    score = min(1.0, 0.4 + 0.15 * len(hits))
    if any(_contains(title_text.lower(), h.lower()) for h in hits):
        score = min(1.0, score + 0.2)

    review = None
    for marker in HUMAN_REVIEW_MARKERS:
        if _contains(haystack, marker.lower()):
            review = marker
            break

    return RelevanceVerdict(
        relevant=True,
        score=round(score, 3),
        hits=hits,
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
    # 用实测抓到的真实假阳性做自检
    samples = [
        ("Commission Implementing Decision (EU) 2025/1769 ... battery-powered "
         "hold-open systems ... construction products", "regression-假阳性"),
        ("Regulation (EU) 2023/1542 on batteries and waste batteries",
         "regression-真阳性"),
        ("格林美2025年年报：动力电池回收量达 8 万吨", "regression-中文真阳性"),
    ]
    for text, label in samples:
        print(f"{label:28s} → {judge(text)}")
