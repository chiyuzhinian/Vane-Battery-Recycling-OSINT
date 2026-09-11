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
    # ---- ELV（报废车）侧 —— 英语/欧盟术语 ----
    # ⚠️ 这是一个真实缺口：英语模式里**只有 battery 侧的词，没有 vehicle 侧**。
    #    实测后果：报废车指令 2000/53/EC（ELV 主干法，3.2 万字符全文）
    #    只能靠 `depollution` 勉强命中 —— 而那是法语模式顺带覆盖的，
    #    `end-of-life vehicle` / `2000/53/EC` / `shredder light fraction`
    #    这些 ELV 核心术语一个都没有。
    r"end-of-life\s+vehicles?", r"\belv\b",
    r"2000/53/EC", r"2005/64/EC",                    # ELV 指令 / 3R 型式认证
    r"certificate\s+of\s+destruction",               # 报废证明（COD）
    r"dismantl\w*\s+of\s+vehicles?", r"dismantlers?",
    r"shredder\s+light\s+fraction", r"\bslf\b",     # 破碎轻馏分
    r"vehicle\s+recycl",
    r"take-back\s+of\s+(old\s+)?vehicles",
]

# ============================================================
# 第一段 B：欧盟成员国语言（德 / 法 / 荷）—— ⚠️ 不加这一组会丢失整个成员国层
# ------------------------------------------------------------
# 实测（2026-09-11）：
#     altautov（德国 AltfahrzeugV 报废车法，5.4 万字符） → ❌ 未命中必修词
#     avv     （德国 AVV 欧洲废物目录，危废分类依据）    → ❌ 未命中必修词
#     ADEME REP-VHU-broyeurs（法国 122 条破碎厂数据）    → ❌ 未命中必修词
#   BWB 荷兰法规正文                                    → 若不补则同样丢失
#   即：**数据采到了，但系统不认** —— 这是最危险的一类 bug，
#   因为采集日志一切正常，只是入不了库。
#
# 选词标准：必须是本国**本领域专有名词**，不是通用词。
# 反而要避免的：bare `batterie`（`batter` 已覆盖）、通用 `Abfall`（=waste，太泛）、
#                荷兰语通用 `afvalstof`（=waste）——只取精确的 `afvalstoffenlijst`。
# ============================================================
MEMBER_STATE_PATTERNS: list[str] = [
    # ---- 德语（德国转化 ELV 指令、实施 EU 电池法）----
    r"altfahrzeug",              # 报废车（德语 ELV 的标准说法）
    r"altbatterie",              # 废电池
    r"batteriegesetz", r"\bbattdg\b",      # 德国电池法
    r"abfallverzeichnis",        # 废物目录（AVV，危废分类）
    r"fahrzeugverwertung",       # 车辆回收利用
    r"schwarzmasse",             # 黑粉（德语）
    r"schredder",                # 破碎机
    r"r[uü]cknahmepflicht",      # 回收义务
    # ---- 法语（法国 REP / VHU 体系）----
    r"\bvhu\b",                  # 报废车（véhicule hors d'usage）
    r"v[eé]hicule\s+hors\s+d'?usage",
    r"masse\s+noire",            # 黑粉（法语）
    r"broyeur",                  # 破碎机 —— 实测这个查出英文找不到的数据集
    r"d[eé]pollution",           # 去除污染（报废车预处理）
    r"responsabilit[eé]\s+[eé]largie\s+du\s+producteur",   # 生产者延伸责任
    r"fili[eè]re\s+[àa]\s+responsabilit",                  # REP 体系的法式说法
    r"centre\s+de\s+traitement\s+de\s+v[eé]hicules",       # 报废车处理中心
    # ⚠️ 2026-09-11 补：法语此前**只有 ELV / 黑粉侧词汇，没有电池侧词汇**。
    #    后果：《环境法典》里「Chapitre III —— Dispositions propres à certaines
    #    catégories de produits et de déchets」（电池与蓄电池专章）这类条文
    #    虽然命中了 accumulateur / pile，却因模式库无对应词被判为不相关。
    #    与德语（batteriegesetz）、荷兰语（batterij）、西语（batería）不对称，
    #    属于**语言覆盖不完整**而非源不可用。
    r"batterie",                 # 电池（含 batteries；法语政策文本里基本无歧义）
    r"accumulateur",             # 蓄电池（含 accumulateurs）
    r"broyage",                  # 破碎（黑粉产出的上游工序，↔ 英语 shredding）
    # `pile` 单用有「堆/桩」义，故只收**限定搭配**，不做裸词匹配
    r"\bpiles?\s+(?:usag[eé]es?|alcalines?|bouton|au\s+lithium)",
    r"\bpiles?\s+et\s+accumulateurs?",
    r"d[eé]chets?\s+d'?[eé]quipements\s+[eé]lectriques",    # DEEE（电子废弃物）
    # ---- 荷兰语（荷兰《环境管理法》/《报废车辆管理令》体系，KOOP BWB）----
    r"autowrak",                # 报废车（荷兰语 ELV 标准说法，含 autowrakken）
    r"batterij",                # 电池（含 batterijen）
    r"\baccu'?s?\b",            # 蓄电池（法规中的常用简称）
    r"accumulatoren?",          # 蓄电池（正式写法）
    r"zwarte\s+massa",          # 黑粉（荷兰语）
    r"afvalstoffenlijst",       # 废物清单（危废定性依据，对应德国 abfallverzeichnis）
    r"producentenverantwoordelijkheid",   # 生产者延伸责任（对应法国 REP）
    r"batterijverordening",     # 电池条例（欧盟 2023/1542 的荷兰语称法）
    # ---- 西班牙语（西班牙 BOE 立法整合库）----
    r"bater[ií]a",              # 电池
    r"\bpilas?\b",             # 电池（西语常用，注意 pila 也有“堆”义）
    r"acumulador",             # 蓄电池
    r"veh[ií]culos?\s+fuera\s+de\s+uso",   # 报废车（西语 VFU）
    r"\bvfu\b",
    r"masa\s+negra",           # 黑粉（西语）
    r"descontaminaci[óo]n",    # 去除污染（报废车预处理）
    r"fragmentaci[óo]n",       # 破碎（↔ 英语 shredding）
    r"residuos?\s+peligrosos", # 危险废物
    r"chatarra",               # 废金属
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

# ============================================================
# 黑粉监管四条线 —— 专题识别模式
# ------------------------------------------------------------
# ⭐ 为什么单列一组：**黑粉的监管不在电池法里**，而是分散在四条独立线上。
#    通用强模式（要求"电池+回收"共现）会把这些法规**全部漏掉** ——
#    实测 (EU) 2024/1157「废物跨境转移条例」因标题里没有 battery 被判"不相关"，
#    导致黑粉第①条线整个缺失。
#
# ⚠️ 这些模式命中后**一律转人工复核**，不自动判为相关：
#    因为它们描述的是"监管领域"，不必然与电池相关
#    （如"危险废物"可以指任何废物）。宁可多一条待审，不可漏一条法规。
#
# ⚠️⚠️ 线名是**跨模块契约**：报告生成器按线名聚合，必须与此处完全一致。
#      曾经踩过：报告里写 "① 废物跨境转移"（带空格），此处是 "①废物跨境转移"（无空格）
#      → 四条线全部显示"未收集到条目"，而实际有命中。
#      所以线名统一由本模块导出，消费端 **import，不要自己抄一份**。
# ============================================================
LINE_EOL_SHIPMENT = "①废物跨境转移"
LINE_DANGEROUS_GOODS = "②危险货物运输"
LINE_HAZWASTE = "③危废定性"
LINE_STRATEGIC = "④战略价值认定"

BLACK_MASS_LINE_PATTERNS: list[tuple[str, str]] = [
    # ---- ① 废物跨境转移 ----
    (r"shipments?\s+of\s+waste", LINE_EOL_SHIPMENT),
    (r"waste\s+shipments?", LINE_EOL_SHIPMENT),
    (r"\b2024/1157\b", LINE_EOL_SHIPMENT),          # 新废物运输条例
    (r"\b1257/2013\b", LINE_EOL_SHIPMENT),          # 旧废物运输条例
    (r"\bbasel\s+convention\b", LINE_EOL_SHIPMENT),
    (r"transboundary\s+movements?", LINE_EOL_SHIPMENT),
    (r"abfallverbringung", LINE_EOL_SHIPMENT),
    (r"transfert\s+de\s+d[eé]chets", LINE_EOL_SHIPMENT),
    # ⚠️ 成员国语言版本：不加则荷兰/西班牙法规在四线分析里"看不见"
    (r"overbrenging\s+van\s+afvalstoffen", LINE_EOL_SHIPMENT),   # 荷兰语
    (r"grensoverschrijdende\s+overbrenging", LINE_EOL_SHIPMENT),
    (r"traslado\s+de\s+residuos", LINE_EOL_SHIPMENT),            # 西班牙语
    (r"movimientos?\s+transfronterizos?\s+de\s+residuos", LINE_EOL_SHIPMENT),
    # ---- ② 危险货物运输 ----
    # ⚠️ 不要加 `shippers?`：每份危险货物文件都会出现 "shipper"，
    #    实测导致 64 条命中里绝大多数是 "Notice of Actions on Special Permits"
    #    这类许可通告，与电池/黑粉无关。**宁可漏，不要泛。**
    (r"\bun\s*348[01]\b", LINE_DANGEROUS_GOODS),          # 锂电池 UN 编号
    (r"damaged[,\s]+defective", LINE_DANGEROUS_GOODS),     # DDR 电池
    (r"\b49\s*cfr\s*(17[0-9]|100)", LINE_DANGEROUS_GOODS),
    (r"hazardous\s+materials?\s+regulations?\b", LINE_DANGEROUS_GOODS),
    (r"lithium\s+batter\w*\s+(transport|shipment)", LINE_DANGEROUS_GOODS),
    (r"\bADR\b.*\bbatter", LINE_DANGEROUS_GOODS),
    # ---- ③ 危废定性 ----
    (r"\brcra\b", LINE_HAZWASTE),
    (r"abfallverzeichnis", LINE_HAZWASTE),
    (r"avfallsf[oö]rordning", LINE_HAZWASTE),
    # ⚠️ 都是"废物清单"的精确对应词，不是泛指的"废物"：
    (r"afvalstoffenlijst", LINE_HAZWASTE),                    # 荷兰语
    (r"lista\s+europea\s+de\s+residuos", LINE_HAZWASTE),      # 西班牙语（LER）
    (r"\bler\b\s*\(?\s*lista", LINE_HAZWASTE),
    # ---- ④ 战略价值认定 ----
    (r"\b2024/1252\b", LINE_STRATEGIC),             # 关键原材料法
    (r"critical\s+raw\s+materials?\s+act", LINE_STRATEGIC),
    (r"\b45x\b", LINE_STRATEGIC),
]
_LINE_RE = [(re.compile(p, re.I), name) for p, name in BLACK_MASS_LINE_PATTERNS]


def black_mass_lines(text: str, title: str = "") -> list[str]:
    """返回文本命中的黑粉监管线名称（可能多条）。

    抽成公开函数供报告复用：报告与采集判定用**同一套模式**，
    避免"报告里显示的线和采集时判的线不一致"。
    """
    hay = f"{title}\n{text}"
    return sorted({name for rx, name in _LINE_RE if rx.search(hay)})


REJECT_IF_MATCH: list[str] = [    # ⚠️ 实测假阳性来源
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

_STRONG_RE = [re.compile(p, re.I)
              for p in STRONG_PATTERNS + MEMBER_STATE_PATTERNS]
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

    # ---- 4b) 黑粉监管四条线 → 人工复核（不自动相关）----
    #   为什么放在最后一道：这四类法规**标题里常常没有 battery**，
    #   但它们是黑粉监管的实际依据。不接收 → 整条线缺失（实测过）。
    #   为什么只标人工：模式描述的是"监管领域"，不必然与电池相关。
    if not hits:
        lines = black_mass_lines(haystack)
        if lines:
            return RelevanceVerdict(
                relevant=True, score=0.5,
                hits=[f"line:{n}" for n in lines],
                needs_human_review=True,
                review_reason=f"命中黑粉监管线「{'、'.join(lines)}」，"
                              f"需人工确认与电池/黑粉的关联",
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


# ============================================================
# 门户类批量源判定（scenario="portal"）—— Federal Register / BOE 等批量文书库
# ------------------------------------------------------------
# ⭐ 判据不是拍脑袋写的，来自**用户审核给出的标准样本**（2026-09-12）。
#    用户原话：「我需要的是**报废退役电池处置**相关的政策法规，黑粉也有」
#    「这个是符合标准的 —— 按照这个纠正」 ※指 PHMSA 安全通告
#
#   ✅ 正样本（标准的形状）
#      PHMSA《Safety Advisory Notice for the Disposal and Recycling of
#      Lithium Batteries in Commercial Transportation》
#      —— 「退役/损坏状态的电池」×「处置/回收动作」×「操作性规则」，
#         三者都在**主旨**上（标题即 "Disposal and Recycling of ... Batteries"）
#   ✅ 正样本（用户标注 relevant）
#      FR 2024-09094 清洁车辆抵免（标题含 Critical Minerals and Battery
#      Components）—— 涉电池材料合规，按本判据落「待人工」档
#   ❌ 负样本（用户标注 irrelevant）
#      FR 2024-08913《Interpretation of Foreign Entity of Concern》
#      —— "recycling" 只作为**拨款项目名**出现（"Battery Manufacturing and
#         Recycling Grants programs"），规则本身讲的是外国实体认定
#   ❌ 实测噪声
#      TSCA「新化学物质状态通告」（正文列了个 battery component 化学品）
#      NESHAP「空气排放标准」（正文顺带提了一次电池回收商）
#
# 由此得到三条可执行规则：
#   ① **身份优先**：主依据是「标题 + 摘要」，不是全文任意位置的命中。
#      FR 的 excerpts 是检索词扫到的零散片段 —— "某处提到" ≠ "在讲这个"。
#      （与浏览器通道同一原则：那里已证明整页噪声会让判定失真）
#   ② **"回收/处置"的两种出现方式必须分开**：
#        被规制对象（"shipping batteries for recycling"、"recycled in
#                    North America"）        → ✅ 证据
#        财政工具宾语（"Recycling Grants programs"、"prioritize recycling
#                    applicants"）            → ❌ 不是证据（项目名/资格条件）
#   ③ **材料/供应链类**（battery component、critical minerals、clean vehicle
#      credit）不再单独判相关 —— 没有处置语义，一律转人工。
# ============================================================

# 处置链证据：要求「电池/车辆」与「处置/退役」**在同一短语内**共现
PORTAL_DISPOSAL_PATTERNS = [
    # 退役状态 + 电池
    r"(spent|used|waste|end[- ]of[- ]life|retired|scrapped|discarded|dead)\s+"
    r"(lithium[- ]ion\s+|li[- ]ion\s+)?batter",
    r"batter\w*[\s,]{1,6}(spent|end[- ]of[- ]life|waste|scrap|retired)",
    # 处置/回收动作 + 电池（双向；含 reuse，梯次利用同属处置链）
    r"batter\w*[\s\S]{0,40}?\b(recycl|dispos|shredd|dismantl|repurpos|"
    r"second[- ]life|salvag|reus)",
    r"\b(recycl|dispos|shredd|dismantl|repurpos|salvag|reus)\w*[\s\S]{0,30}?"
    r"(lithium[- ]ion\s+|spent\s+|waste\s+|used\s+|end[- ]of[- ]life\s+)?batter",
    # 回收体系术语（收集/回收点）
    r"batter\w*\s+collection", r"collection\s+of\s+batter",
    # 黑粉（多语）
    r"black\s+mass", r"masse\s+noire", r"schwarzmasse", r"zwarte\s+massa",
    r"masa\s+negra", r"黑粉",
    # 运输 / 包装 / 贮存（处置链环节 —— PHMSA 标准的核心）
    # ⚠️ 这里**必须收窄**（实测误收，2026-09-12）：
    #    首版用 `batter\w* ...(transport|shipment|shipping|packag)` 的宽间隔匹配，
    #    结果把两条**完全无关**的航空文书也捞成"相关"：
    #      · "Special Conditions: ... Non-Rechargeable Lithium Batteries ...
    #        on certain **transport category airplanes**"  ← transport 是航空器类别词
    #      · "FMVSS No. 305a Electric-Powered Vehicles ... National **Transport**..."
    #    教训：`transport` 在英文法规里**不只表示货运**。必须要求它与电池
    #    构成"运输某物"的句法，而不是碰巧同段。
    r"batter\w*[\s-]{0,2}(transport|shipment|shipping)",           # battery transport / shipment
    r"(transport|shipment|shipping|packaging)\s+of\s+.{0,20}?batter",  # transport of ... batteries
    r"batter\w*[\s\S]{0,20}?\bfor\s+(disposal|recycling|transport)",
    r"(damaged|defective|recalled)[\s,]+.{0,25}batter",
    r"\bun\s*348[01]\b", r"\b49\s+cfr\s+17",
    # 报废车侧
    r"end[- ]of[- ]life\s+vehicle", r"\belvs?\b", r"\baltfahrzeug",
    r"v[eé]hicule\s+hors", r"\bvhu\b", r"autowrak",
]

# 财政工具框架 —— "回收/处置"出现在这里时**不算处置证据**（08913 的判例）
PORTAL_FINANCIAL_FRAME = [
    r"(recycl\w*|dispos\w*)\s+(grants?|programs?|funding|applicants?|awards?|projects?)",
    r"(grants?|funding|programs?|credits?)[\s\S]{0,24}\bfor\b[\s\S]{0,24}(recycl|dispos)",
    r"priorit\w+[\s\S]{0,40}(recycl|dispos)\w*\s+applicants?",
]

# 材料 / 供应链锚点 —— 单独出现（无处置证据）时转人工，不直接判相关
PORTAL_MATERIAL_ANCHORS = [
    r"batter\w*\s+(components?|materials?|supply\s+chains?)",
    r"critical\s+(minerals?|materials?)",
    r"clean\s+vehicle\s+credits?",
    r"recycled\s+content",
    r"\b45x\b", r"\b30d\b", r"\b25e\b",
]

# 标题级程序性模板 —— 这类文书**从不承载处置政策**，直接排除
#   ⚠️ `foreign-trade zone` **不列入**：FTZ 生产活动通知是真实产能信号，
#      属于企业情报（但在政策视图里无处置语义，最终仍落"不相关"）。
#   ⚠️ special permits 的变体要写全（实测漏网）：
#      "Applications for New" / "Actions on" / "Applications for **Modification To**"
#      —— 漏了最后一个变体，24 条审批通告混进了"待人工"。
PORTAL_PROCEDURAL_TITLES = [
    r"agency information collection activities",
    r"(notice of )?(actions on|applications? for (new|modification to)|modification to)"
    r"\s+special permits?",
    r"notice of public meeting", r"public meeting",
    r"receipt and status information",       # TSCA 新化学物质状态通告
    r"proposed collection", r"information collection",
]

# 标题里的领域锚点（判断"标题是否在讲电池/车辆"）
PORTAL_DOMAIN_ANCHORS = [
    r"batter", r"lithium", r"accumulator", r"\bvehicle", r"\belvs?\b",
    r"电池", r"车辆",
]

# 身份区长度：标题之后的摘要通常落在前 900 字符内
_PORTAL_IDENTITY_CHARS = 900

_PORTAL_DISP_RE = [re.compile(p, re.I) for p in PORTAL_DISPOSAL_PATTERNS]
_PORTAL_FIN_RE = [re.compile(p, re.I) for p in PORTAL_FINANCIAL_FRAME]
_PORTAL_MAT_RE = [re.compile(p, re.I) for p in PORTAL_MATERIAL_ANCHORS]
_PORTAL_PROC_RE = [re.compile(p, re.I) for p in PORTAL_PROCEDURAL_TITLES]
_PORTAL_DOMAIN_RE = [re.compile(p, re.I) for p in PORTAL_DOMAIN_ANCHORS]


def _portal_disposal_hits(hay: str) -> list[str]:
    """列出"处置链"命中，并剔除落在**财政工具框架**内的（08913 的判例）。

    只做"位置剔除"不做"语义理解"：命中点前后 40 字符里若出现
    grants/programs/applicants 等资助语境，就认为这是在讲**项目**而非**处置**。
    """
    out: list[str] = []
    for rx in _PORTAL_DISP_RE:
        for m in rx.finditer(hay):
            snippet = hay[max(0, m.start() - 40): m.end() + 40]
            if any(f.search(snippet) for f in _PORTAL_FIN_RE):
                continue                      # 财政工具语境 —— 不是处置证据
            out.append(m.group(0)[:44])
    return out


def judge_portal_policy(text: str, title: str | None = None) -> RelevanceVerdict:
    """门户类批量源判定（scenario="portal"）。

    与 `judge_policy` 的差别：**不信任"全文某处提到"**。证据分三层：

      0. 标题是程序性模板（信息收集/会议通知/许可通告）→ 直接排除
      1. **标题**命中处置链 → 相关（强）            —— PHMSA 判例
      2. **身份区**（标题 + 摘要前 900 字符）命中处置链：
           标题含电池/车辆锚点 → 相关
           标题不含锚点        → 转人工（保守：不直接采信摘要）
      3. **正文**命中处置链 ≥2 处 → 转人工
         标题含材料/供应链锚点  → 转人工            —— 09094 判例
         黑粉监管四线           → 转人工
      4. 其余 → 不相关
    """
    if not text:
        return RelevanceVerdict(relevant=False, score=0.0)

    title_text = title or ""
    lowered = f"{title_text}\n{text}".lower()

    # ---- 0a) 拒绝词（沿用政策类）----
    for bad in REJECT_IF_MATCH:
        if bad.lower() in lowered:
            if bad == "启动电池" and any(
                k in lowered for k in ("法规", "指令", "regulation", "directive", "回收")
            ):
                continue
            return RelevanceVerdict(relevant=False, score=0.0, rejected_by=bad)

    # ---- 0b) 标题程序性模板 → 排除 ----
    for rx in _PORTAL_PROC_RE:
        m = rx.search(title_text)
        if m:
            return RelevanceVerdict(relevant=False, score=0.0,
                                    rejected_by=f"procedural:{m.group(0)[:30]}")

    # ---- 1) 标题命中处置链 → 强相关 ----
    title_hits = _portal_disposal_hits(title_text)
    if title_hits:
        return RelevanceVerdict(
            relevant=True, score=0.9,
            hits=[f"title:{h}" for h in title_hits[:4]],
        )

    title_has_anchor = any(rx.search(title_text) for rx in _PORTAL_DOMAIN_RE)

    # ---- 2) 身份区（标题 + 摘要）命中处置链 ----
    identity = title_text + "\n" + text[:_PORTAL_IDENTITY_CHARS]
    ident_hits = _portal_disposal_hits(identity)
    if ident_hits:
        if title_has_anchor:
            return RelevanceVerdict(
                relevant=True, score=0.75,
                hits=[f"summary:{h}" for h in ident_hits[:4]],
            )
        return RelevanceVerdict(
            relevant=True, score=0.5,
            hits=[f"summary:{h}" for h in ident_hits[:4]],
            needs_human_review=True,
            review_reason="摘要提及电池处置/回收，但标题无电池锚点，需人工确认主旨",
        )

    # ---- 3a) 正文多处提及处置链 → 转人工 ----
    body_hits = _portal_disposal_hits(text)
    if len(body_hits) >= 2:
        return RelevanceVerdict(
            relevant=True, score=0.5,
            hits=[f"body:{h}" for h in body_hits[:4]],
            needs_human_review=True,
            review_reason="正文多处提及电池处置/回收，但标题与摘要未体现，需人工确认",
        )

    # ---- 3b) 标题含材料/供应链锚点 → 转人工（09094 判例）----
    mat = next((m for rx in _PORTAL_MAT_RE if (m := rx.search(title_text))), None)
    if mat:
        return RelevanceVerdict(
            relevant=True, score=0.5,
            hits=[f"material:{mat.group(0)[:30]}"],
            needs_human_review=True,
            review_reason="电池材料/供应链类（无处置语义），需人工裁决",
        )

    # ---- 3c) 黑粉监管四线 → 转人工 ----
    lines = black_mass_lines(text, title_text)
    if lines:
        return RelevanceVerdict(
            relevant=True, score=0.5,
            hits=[f"line:{n}" for n in lines],
            needs_human_review=True,
            review_reason=f"命中黑粉监管线「{'、'.join(lines)}」，"
                          f"需人工确认与电池/黑粉的关联",
        )

    # ---- 4) 其余 → 不相关 ----
    return RelevanceVerdict(relevant=False, score=0.0)


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
        # ---- 跨语言回归用例（2026-09-11，全部为实测误杀）----
        ("Verordnung über die Überlassung, Rücknahme und umweltverträgliche Entsorgung "
         "von Altfahrzeugen (AltfahrzeugV)", "真阳性-德国报废车法(德语)"),
        ("Gesetz zur Durchführung der Verordnung (EU) 2023/1542 betreffend Batterien "
         "und Altbatterien (BattDG)", "真阳性-德国电池法(德语)"),
        ("Verordnung über das Europäische Abfallverzeichnis (AVV) —— gefährliche "
         "Abfälle, Schredder-Rückstände", "真阳性-德国废物目录(德语)"),
        ("REP - VHU - Tonnages collectés Broyeurs depuis 2018 —— "
         "Nombre_de_carcasses_prises_en_charge", "真阳性-法国破碎厂数据(法语)"),
        ("Masse noire issue du broyage des véhicules hors d'usage", "真阳性-法语黑粉"),
        # ---- 黑粉监管四条线（应转人工复核，不自动相关）----
        ("Regulation (EU) 2024/1157 of 11 April 2024 on shipments of waste, "
         "amending Regulations (EU) No 1257/2013 and (EU) 2020/1056",
         "人工复核-①废物跨境转移"),
        ("Critical Raw Materials Act (EU) 2024/1252 — strategic projects list",
         "人工复核-④战略价值认定"),
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

