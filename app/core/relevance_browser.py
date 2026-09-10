"""浏览器通道相关性判定 —— 与被反爬站点的噪声结构匹配。

为什么不能复用政策规则
----------------------
政策规则（judge_policy）在**关键词检索结果**上工作良好，因为那种文本是
"一篇文档"。但浏览器抓来的是**整个页面的渲染文本**，其中必然混入
站点全局导航。

实测（2026-09-10，CalRecycle）：
    `/epr/` 页面的导航里列着该站**全部**产品线——
    纺织 / 包装 / 油漆 / 地毯 / 床垫 / 药品锐器 / 饮料容器 …
    导航文本里 "recycl" 与 "batter" 天然共现，
    于是 Textiles、SB 54 包装 EPR 都被政策规则判成了"相关"。

结论：**浏览器通道的判定必须以「页面身份」为准（标题 + URL 路径），
正文只能作辅助。** 导航文本不是页面在讲的内容。

判定阶梯（拒绝优先）
--------------------
    1. 页面类型噪声（隐私政策/招聘/站点地图…）      → 丢弃
    2. 同母类的其他产品线（纺织/包装/油漆/地毯…）    → 丢弃
    3. 页面身份含电池锚点                            → 相关
    4. 身份不含电池但正文强相关                      → 人工复核（不直接丢）
    5. 其余                                          → 丢弃

第 4 档为什么保留：有些关键页面标题确实不写 "battery"
（例如欧盟"废物越境转移"页）。宁可标人工，不可漏。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

try:                                    # 作为包导入（正常路径）
    from .relevance import RelevanceVerdict, judge_policy
except ImportError:                     # 直接 `py app/core/relevance_browser.py` 跑自检
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from relevance import RelevanceVerdict, judge_policy  # type: ignore[no-redef]

# ============================================================
# 1) 硬噪声 —— 这类页面在任何站点都**永远不是证据**
# ============================================================
BROWSER_NOISE_PATTERNS: list[str] = [
    r"privacy\s+polic", r"terms\s+(of\s+)?(use|service)", r"cookie",
    r"legal\s+notice", r"disclaimer", r"accessibilit", r"sitemap",
    r"contact\s+us", r"careers?", r"newsletter",
    r"subscribe", r"sign\s+in", r"log\s+in", r"site\s+map",
    r"^untitled", r"page\s+not\s+found", r"\b404\b",
    # ⚠️ 只匹配真正的招聘页，不能用 \bjobs?\b 泛匹配：
    #    实测误杀 PHMSA 的「Green Job Hazards - Recycling: Batteries | OSHA」
    #    ——那是真相关的（电池回收职业危害）。
    #    两层保护：
    #      ① 用**复数** \bjobs\b（「Green Job Hazards」是单数，不命中）
    #      ② 排除 "green jobs"（OSHA 的 URL 是 /green-jobs/recycling/batteries，
    #         路径里连字符转空格后变成 "green jobs"，会误命中）
    r"(?<!green[-\s])\bjobs\b", r"^job\s+opportunit",
    r"\bjob\s+(openings?|opportunities|listings?|search)\b",
    # ⭐⭐ WAF/人机验证页 —— **拦截页伪装成内容，是最危险的一类假阳性**。
    #    实测 ECHA 的 Azure WAF 403 页标题就是 "Azure WAF"，
    #    不拦就会被当成一条"证据"写进证据库。
    r"azure\s+waf", r"web\s+application\s+firewall",
    r"access\s+denied", r"\bcaptcha\b", r"are\s+you\s+a\s+human",
    r"enable\s+javascript", r"\bcloudflare\b", r"attention\s+required",
    r"\bddos\s+protection\b", r"request\s+blocked", r"403\s+forbidden",
]

# ============================================================
# 1b) 导航型噪声 —— **只在页面身份里没有电池线索时**才算噪声。
#     为什么不能并入硬噪声：
#       「About the Battery Regulation」是可用证据，
#       而「About Us」不是。区别在于有没有电池锚点。
# ============================================================
BROWSER_NAV_PATTERNS: list[str] = [
    r"^about\b", r"^home\b", r"^index\b",
    r"^overview\b", r"^directory\b", r"^site\b", r"^search\b",
    r"^departments?\b", r"^services?\b",
    # ⚠️ 不能用 `\bhome\s*page\b`：CalRecycle 每个页面标题都带
    #    "- CalRecycle Home Page" 后缀，会把全部页面误杀。
    #    只认「主标题整体就是 Home/HOMEPAGE」的情况。
    r"^(the\s+)?home\s*page\s*$", r"^(the\s+)?homepage\s*$",
]


def _strip_site_suffix(title: str) -> str:
    """去掉站点名后缀，避免标题里的 "- XX Home Page" 干扰判定。

    实测：CalRecycle 的标题形如「Battery Stewardship - CalRecycle Home Page」，
    后半截是站点名，不是页面内容。
    """
    t = (title or "").strip()
    # 只删最后一个 " - 站点名" / " | 站点名" 后缀，且后缀里不含电池/回收线索
    m = re.match(r"^(.+?)\s+[-|–—]\s+([^-|–—]{3,60})$", t)
    if m and not re.search(r"batter|lithium|recycl|waste|black\s+mass", m.group(2), re.I):
        return m.group(1).strip()
    return t

# ============================================================
# 2) 同母类的其他产品线 —— 电池 EPR 站点的头号噪声源
#    这些产品线与电池同属"生产者责任延伸/回收"母类，
#    共享绝大部分词汇，只有产品名不同。
# ============================================================
SIBLING_STREAM_PATTERNS: list[str] = [
    r"textile", r"packaging", r"plastic", r"paint\b", r"carpet",
    r"mattress", r"pharmaceutical", r"sharps", r"beverage\s+container",
    r"\btires?\b", r"used\s+oil", r"mercury\s+lamp", r"fluorescent\s+lamp",
    r"\bsb\s*54\b", r"\bab\s*793\b",                      # 加州包装/纺织法案
    r"container\s+deposit", r"bottle\s+bill",
    r"solar\s+panel", r"photovoltaic\s+panel", r"wind\s+turbine\s+blade",
    r"e-?waste", r"electronic\s+waste", r"appliance\s+recycl",
]

# ============================================================
# 3) 页面身份锚点 —— 标题或 URL 路径里出现，才认定"这是电池页"
# ============================================================
BROWSER_FOCUS_ANCHORS: list[str] = [
    r"batter", r"lithium", r"li-?ion", r"lead-?acid",
    r"black\s+mass", r"cathode", r"anode",
    r"end-?of-?life\s+vehicle", r"\belv\b",
    r"electric\s+vehicle", r"\bev\b",
    r"damaged[\s,]+defective", r"\bddr\b", r"recalled\s+batter",
    r"\bun\s*3480\b", r"\bun\s*3481\b", r"hazmat.*batter",
]

# 身份里出现这些词 → 明确是"回收/监管"主题（提高分数用）
BROWSER_POLICY_ANCHORS: list[str] = [
    r"recycl", r"stewardship", r"producer\s+responsib", r"\bepr\b",
    r"policy", r"legislat", r"regulat", r"guidance", r"compliance",
    r"transport", r"shipment", r"hazard", r"collection",
    r"material\s+recovery", r"circular",
]

_NOISE_RE = [re.compile(p, re.I) for p in BROWSER_NOISE_PATTERNS]
_NAV_RE = [re.compile(p, re.I) for p in BROWSER_NAV_PATTERNS]
_SIBLING_RE = [re.compile(p, re.I) for p in SIBLING_STREAM_PATTERNS]
_FOCUS_RE = [re.compile(p, re.I) for p in BROWSER_FOCUS_ANCHORS]
_POLICY_RE = [re.compile(p, re.I) for p in BROWSER_POLICY_ANCHORS]


def _page_identity(title: str, url: str) -> str:
    """页面身份 = 标题（去站点后缀）+ URL 路径（去掉域名与查询串）。

    为什么去掉域名：`calrecycle.ca.gov` 里的 "recycl" 会让每个页面都像回收主题。
    为什么保留路径：`/epr/batteries/` 的 `batteries` 是页面真正在讲什么。
    """
    path = ""
    if url:
        try:
            path = urlparse(url).path.replace("-", " ").replace("/", " ")
        except ValueError:
            path = url
    return f"{_strip_site_suffix(title)} {path}".strip()


def judge_browser(title: str, url: str = "", text: str = "") -> RelevanceVerdict:
    """浏览器抓取页面的相关性判定（以页面身份为准）。"""
    identity = _page_identity(title, url)

    # ---- 1) 页面类型噪声 ----
    for rx in _NOISE_RE:
        m = rx.search(identity)
        if m:
            return RelevanceVerdict(relevant=False, score=0.0,
                                    rejected_by=f"browser_noise:{m.group(0)[:24]}")

    # ---- 2) 同母类其他产品线（必须排在电池锚点之前做联合判断）----
    sibling = next((m.group(0) for rx in _SIBLING_RE if (m := rx.search(identity))), None)

    # ---- 3) 页面身份含电池锚点 ----
    focus_hits = [m.group(0) for rx in _FOCUS_RE if (m := rx.search(identity))]
    if focus_hits and not sibling:
        policy_hits = [m.group(0) for rx in _POLICY_RE if (m := rx.search(identity))]
        score = min(1.0, 0.65 + 0.1 * len(policy_hits))
        if text and len(text) > 800:            # 有实质正文，再加一点
            score = min(1.0, score + 0.05)
        return RelevanceVerdict(relevant=True, score=round(score, 3),
                                hits=focus_hits[:4] + policy_hits[:2])
    if focus_hits and sibling:
        # 身份里同时出现电池和别的产品线 → 多半是"站点总览页"（列出所有产品线）
        # 这一档不能直接丢（可能是电池专题的聚合页），交人工
        return RelevanceVerdict(
            relevant=True, score=0.4, hits=focus_hits[:3] + [f"sibling:{sibling}"],
            needs_human_review=True,
            review_reason=f"页面身份同时含电池与同母类产品线「{sibling}」，疑似站点总览页")

    # ---- 2b) 只有别的产品线，没有电池 → 丢弃 ----
    if sibling:
        return RelevanceVerdict(relevant=False, score=0.0,
                                rejected_by=f"browser_sibling:{sibling}")

    # ---- 3b) 导航型页面（首页/关于我们…）—— 到这里说明身份里没有电池线索 ----
    for rx in _NAV_RE:
        m = rx.search(identity)
        if m:
            return RelevanceVerdict(relevant=False, score=0.0,
                                    rejected_by=f"browser_nav:{m.group(0)[:24]}")

    # ---- 4) 身份不含电池，但正文强相关 → 人工复核（不直接丢）----
    v = judge_policy(text, title)
    if v.relevant:
        return RelevanceVerdict(
            relevant=True, score=min(v.score, 0.6), hits=v.hits,
            needs_human_review=True,
            review_reason="页面身份（标题/URL）不含电池线索，但正文相关，需人工确认",
        )

    # ---- 5) 丢弃 ----
    return RelevanceVerdict(relevant=False, score=0.0,
                            rejected_by=v.rejected_by or "browser_no_identity_anchor")


# ============================================================
# 回归自检
# ============================================================
_SAMPLES: list[tuple[str, str, str, bool, str]] = [
    # (title, url, text, 期望相关, 说明)
    ("Battery Stewardship - CalRecycle Home Page",
     "https://calrecycle.ca.gov/EPR/batteries/",
     "Responsible Battery Recycling Program AB 2440 ...", True, "真阳性-加州电池EPR"),
    ("Safety Advisory Notice for the Transportation of Lithium Batteries "
     "for Disposal or Recycling",
     "https://www.phmsa.dot.gov/training/hazmat/safety-advisory-notice-"
     "transportation-lithium-batteries-disposal-or-recycling",
     "Issued Date: Tuesday, May 17, 2022 ... damaged defective recalled ...", True,
     "真阳性-PHMSA运输通告"),
    ("Lithium Battery Guide for Shippers | PHMSA",
     "https://www.phmsa.dot.gov/lithiumbatteries/lithium-battery-guide-shippers",
     "UN3480 UN3481 packing instruction ...", True, "真阳性-托运指南"),
    ("Lead Battery Recycling | Battery Council International",
     "https://batterycouncil.org/battery-facts-and-applications/battery-recycling/",
     "98 percent recycling rate ...", True, "真阳性-铅电池回收"),
    ("Understanding the Risks of Damaged, Defective, or Recalled (DDR) "
     "Lithium Batteries",
     "https://www.phmsa.dot.gov/lithiumbatteries/ddr", "DDR battery risks ...", True,
     "真阳性-DDR"),
    # ---- 以下为实测泄漏，必须被拒 ----
    ("Textiles - CalRecycle Home Page", "https://calrecycle.ca.gov/epr/textiles/",
     "recycl ... battery ... extended producer responsibility ...", False,
     "真阴性-纺织（导航里含battery）"),
    ("SB 54: Plastic Pollution Prevention and Packaging Producer Responsibility Act",
     "https://calrecycle.ca.gov/packaging/packaging-epr/",
     "recycl ... battery ... producer responsibility ...", False, "真阴性-包装"),
    ("Beverage Container Recycling", "https://calrecycle.ca.gov/bev/",
     "recycl ... battery ...", False, "真阴性-饮料容器"),
    ("Mattress Stewardship Program", "https://calrecycle.ca.gov/epr/mattresses/",
     "recycl ... battery ...", False, "真阴性-床垫"),
    ("About Us - ECHA", "https://echa.europa.eu/about-us",
     "recycl battery waste ...", False, "真阴性-关于我们"),
    ("About the Battery Regulation", "https://echa.europa.eu/about-batteries-regulation",
     "scope of the regulation ...", True, "真阳性-关于页但有电池线索"),
    ("CalRecycle Jobs - CalRecycle Home Page", "https://calrecycle.ca.gov/Jobs/",
     "battery recycl ...", False, "真阴性-招聘"),
    ("Privacy Policy | Battery Council International",
     "https://batterycouncil.org/privacy-policy/",
     "battery recycl ...", False, "真阴性-隐私政策"),
    # ---- 以下两条是实测误杀，必须修正：规则不能比数据还粗 ----
    ("Green Job Hazards - Recycling: Batteries | Occupational Safety and Health "
     "Administration", "https://www.osha.gov/green-jobs/recycling/batteries",
     "battery recycling hazards ...", True, "真阳性-OSHA（含Job字样）"),
    ("Product Stewardship and Extended Producer Responsibility (EPR) - CalRecycle "
     "Home Page", "https://calrecycle.ca.gov/epr/",
     "battery stewardship program ... recycl battery ...", True,
     "人工复核-EPR总览页（标题带Home Page后缀）"),
    # ---- 拦截页伪装成内容：最危险的假阳性 ----
    ("Azure WAF", "https://echa.europa.eu/legislation",
     "Request blocked ... your request has been blocked ...", False,
     "真阴性-WAF拦截页"),
]

if __name__ == "__main__":
    print("浏览器通道相关性规则回归自检")
    print("=" * 92)
    ok = 0
    for title, url, text, want, label in _SAMPLES:
        v = judge_browser(title, url, text)
        good = v.relevant == want
        ok += good
        mark = "✅" if good else "❌"
        print(f"  {mark} {label:28s} 期望={'相关' if want else '丢弃':2s} → {v}")
    print("-" * 92)
    print(f"  通过 {ok}/{len(_SAMPLES)}")
