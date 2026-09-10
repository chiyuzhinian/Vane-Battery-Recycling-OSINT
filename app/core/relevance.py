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
    # 电池制造/材料制造类：不含"回收"字样，但**环评审批原则同样适用于回收项目**，
    # 直接丢弃会漏掉"某个行业能不能获批建厂"这类关键政策
    # （实测：生态环境部《锂离子电池及相关电池材料制造建设项目环评审批原则》）
    r"锂离子电池", r"电池材料", r"电池制造", r"电池生产",
    r"lithium[- ]ion batter", r"battery manufacturing", r"battery production",
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


# ============================================================
# 项目类规则（场景 2）—— 用于环评公示 / 招投标等"企业项目"场景
# ------------------------------------------------------------
# 为什么必须与政策类分开？
# 实测（2026-09-10）：广东省生态环境厅"审批文件公示"栏目里
#   **81% 是核技术利用 / 医院 / 辐照 / 工业CT 项目**，电池相关仅 1/21。
# 政策类的词表（"电池回收""battery recycling"）在这里两头不讨好：
#   · 拦不住核技术/医疗噪声（它们不含政策词，本就该丢）
#   · 又误杀了真相关项目（"动力电池结构件"、"锂电胶粘材料"不含"回收"）
# 因此项目类必须有自己的判定：
#   项目 = 电池产业链的【建设/扩产/审批】事件
# ============================================================

# A. 强相关：标题里出现这些，就是电池产业链项目
PROJECT_STRONG_PATTERNS: list[str] = [
    # 回收/再生类（最核心）
    r"电池[\s\S]{0,6}回收", r"回收[\s\S]{0,6}(电池|锂)", r"退役电池", r"废旧电池",
    r"梯次利用", r"黑粉", r"电池[\s\S]{0,4}再生", r"再生[\s\S]{0,4}电池",
    r"电池[\s\S]{0,4}拆解", r"电池[\s\S]{0,4}资源化", r"资源化[\s\S]{0,4}电池",
    # 电池材料/制造类
    r"锂(离子)?电池", r"锂电池", r"动力电池", r"储能电池", r"钠离子电池",
    r"正极材料", r"负极材料", r"前驱体", r"电解液", r"隔膜",
    r"电池[\s\S]{0,4}(材料|结构件|组件|制造|生产|基地)",
    r"(锂电|锂离子|三元|磷酸铁锂)[\s\S]{0,6}材料",
]

# B. 明确无关（命中即丢）—— 这些是"审批公示"栏目里的常客，但与我们业务无关
PROJECT_REJECT_PATTERNS: list[str] = [
    # 核与辐射类（省级厅公示的主力，实测占 81%）
    r"核技术利用", r"放射性同位素", r"放射源", r"辐照", r"工业CT", r"CT扩建",
    r"X射线", r"探伤", r"核医学", r"辐射工作场所", r"退役项目.{0,6}辐射",
    # 医疗/教育/市政
    r"医院", r"医学院", r"卫生院", r"疾控", r"妇幼", r"门诊", r"卫生服务",
    r"学校", r"中学", r"小学", r"幼儿园", r"大学",
    # 基础设施（这些出现在环评公示里但与本行业无关）
    r"输变电", r"变电站", r"输电线路", r"开闭所", r"配电站",
    r"海砂", r"航道", r"码头", r"水库", r"水利", r"堤防", r"水厂", r"污水(处理)?厂",
    r"公路", r"道路", r"铁路", r"桥梁", r"隧道", r"地铁", r"轨道交通",
    r"房地产", r"住宅", r"商业综合体", r"写字楼",
    r"垃圾(焚烧|填埋|中转)", r"污泥", r"餐厨",
    r"光伏电站", r"风电场", r"抽水蓄能", r"天然气管道", r"油气管",
]

# C. 模糊地带 → 人工复核（不丢弃，但也绝不当作已确认）
PROJECT_REVIEW_PATTERNS: list[str] = [
    r"新能源", r"新材料", r"固废", r"危险废物", r"资源综合利用",
    r"循环经济", r"再生资源",
]

_PROJ_STRONG_RE = [re.compile(p, re.I) for p in PROJECT_STRONG_PATTERNS]
_PROJ_REJECT_RE = [re.compile(p, re.I) for p in PROJECT_REJECT_PATTERNS]
_PROJ_REVIEW_RE = [re.compile(p, re.I) for p in PROJECT_REVIEW_PATTERNS]


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


def judge_project(text: str, title: str | None = None) -> RelevanceVerdict:
    """项目类判定（环评公示 / 招投标 / 项目批复）。

    判定顺序（**拒绝优先**，宁可漏也不塞垃圾）：
      1. 命中明确无关（核技术/医院/输变电/水库…）→ 丢弃
      2. 命中电池产业链强模式 → 相关
      3. 命中模糊地带（新能源/固废/资源综合利用）→ 相关但标记人工复核
      4. 其余 → 丢弃
    """
    if not text:
        return RelevanceVerdict(relevant=False, score=0.0)

    haystack = f"{title or ''}\n{text}"

    # 1) 明确无关 —— 必须最先判，否则"XX医院核技术利用项目"里的
    #    "利用"等字眼可能被后面的规则误捞
    for rx in _PROJ_REJECT_RE:
        m = rx.search(haystack)
        if m:
            return RelevanceVerdict(relevant=False, score=0.0,
                                    rejected_by=f"project_reject:{m.group(0)[:20]}")

    # 2) 电池产业链强模式
    hits = [m.group(0)[:30] for rx in _PROJ_STRONG_RE
            if (m := rx.search(haystack))]

    if hits:
        score = min(1.0, 0.6 + 0.15 * len(hits))
        return RelevanceVerdict(relevant=True, score=round(score, 3), hits=hits[:5])

    # 3) 模糊地带 → 人工复核
    for rx in _PROJ_REVIEW_RE:
        m = rx.search(haystack)
        if m:
            return RelevanceVerdict(
                relevant=True, score=0.5,
                hits=[f"review:{m.group(0)[:20]}"],
                needs_human_review=True,
                review_reason="泛行业词（新能源/固废/资源综合利用），需人工确认是否涉及电池",
            )

    # 4) 无关
    return RelevanceVerdict(relevant=False, score=0.0)


def judge(text: str, title: str | None = None, scenario: str = "policy") -> RelevanceVerdict:
    """统一入口。scenario:
        "policy"  → 政策法规场景（默认）
        "project" → 企业项目场景（环评 / 招投标）
    """
    if scenario == "project":
        return judge_project(text, title)
    return judge_policy(text, title)


def judge_policy(text: str, title: str | None = None) -> RelevanceVerdict:
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
    print("相关性规则回归自检")
    print("=" * 88)
    print("【场景 1：政策法规】")
    print("-" * 88)
    # 全部来自 2026-09-10 的真实采集结果
    policy_samples = [
        ("Advanced Manufacturing Production Credit ... credit for the production and sale of "
         "battery components and critical minerals processing", "真阳性-45X最终规则"),
        ("Clean Vehicle Credits Under Sections 25E and 30D; Transfer of Credits; "
         "Critical Minerals and Battery Components", "真阳性-清洁车辆抵免"),
        ("Notice of Final Determination on 2023 DOE Critical Materials List", "真阳性-关键材料清单"),
        ("Request for Public Comment on Settlement Agreement for Battery and Electronics "
         "Recycling Inc. Superfund Site", "真阳性-夹词回收"),
        ("Regulation (EU) 2023/1542 on batteries and waste batteries", "真阳性-欧盟电池法"),
        ("格林美2025年年报：动力电池回收量达 8 万吨", "真阳性-中文"),
        ("Energy Conservation Program: Test Procedure for Battery Chargers", "真阴性-充电器"),
        ("Significant New Use Rules on Certain Chemical Substances (26-2)", "真阴性-化学品"),
        ("Air Plan Approval; Georgia; Second Period Regional Haze Plan", "真阴性-空气计划"),
        ("Section 45Y Clean Electricity Production Credit and Section 48E Clean Energy "
         "Investment Credit", "人工复核-能源条款"),
    ]
    for text, label in policy_samples:
        print(f"  {label:26s} → {judge(text, scenario='policy')}")

    print()
    print("【场景 2：企业项目（环评/招投标）】")
    print("-" * 88)
    project_samples = [
        # ⚠️ 真实采集到的条目：上一版规则把它们判为"不相关"，是误杀
        ("2026年9月8日建设项目环境影响报告书（表）审批受理情况公示"
         "（锂电胶粘材料数字化转型升级暨智能制造基地建设项目）", "真阳性-锂电材料项目"),
        ("宁德市生态环境局关于宁德长盈新能源汽车动力电池结构件（三期）"
         "环境影响报告表的批复", "真阳性-动力电池结构件"),
        ("格林美（荆门）动力电池回收与资源化利用项目环境影响报告书受理公示", "真阳性-回收项目"),
        ("XX公司废旧锂电池梯次利用及黑粉提取项目环评受理公示", "真阳性-梯次利用"),
        # 真阴性：省厅公示栏目的噪声主力（实测占 81%）
        ("东莞市道滘医院核技术利用扩建项目生态环境影响报告表受理公告", "真阴性-核技术利用"),
        ("广东省生态环境厅关于广东省汕尾市陆丰西南海域SW24-12矿区海砂开采"
         "环境影响报告书的批复及公告", "真阴性-海砂开采"),
        ("广州中医药大学顺德医院医技楼一层核医学科辐射工作场所退役项目", "真阴性-医院核医学"),
        ("南方医科大学南方医院核技术利用改扩建项目（重新报批）受理公告", "真阴性-医院扩建"),
        ("广东省生态环境厅关于中国科学院高能物理研究所东莞研究部核技术利用"
         "改扩建项目环境影响报告书的批复及公告", "真阴性-科研核利用"),
        # 模糊地带
        ("广东省生态环境厅拟对广东誉兴环境科技有限公司资源综合利用项目"
         "生态环境影响评价文件作出批准决定的公示", "人工复核-资源综合利用"),
    ]
    for text, label in project_samples:
        print(f"  {label:26s} → {judge(text, scenario='project')}")

