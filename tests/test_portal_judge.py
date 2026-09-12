"""门户类判定（judge_portal_policy）的标准样本测试 —— py tests/test_portal_judge.py

为什么需要这个测试
------------------
判据来自**用户审核给出的判例**（2026-09-12），不是我的想象。
用户原话：
    「我需要的是**报废退役电池处置**相关的政策法规，黑粉也有」
    「这个是符合标准的 —— 按照这个纠正」 ※指 PHMSA 安全通告

必须把这些判例固化成断言，否则以后任何一次"顺手优化"都可能
悄悄违背用户的标准 —— 而这类回归**不会报错**，只会让面板重新变脏。

判例清单
--------
  ✅ PHMSA《锂电池商业运输中处置和回收的安全通告》 —— 用户指定的标准
  ✅ FR 2024-09094 清洁车辆抵免（含 Critical Minerals and Battery Components）
     —— 用户标注 relevant（按新判据落"待人工"，但**不排除**）
  ❌ FR 2024-08913 FEOC 定义解释 —— 用户标注 irrelevant
     （"recycling" 只出现在拨款项目名里）
  ❌ TSCA 新化学物质状态通告 / NESHAP 空气标准 —— 正文顺带提及
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge_portal_policy as J  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


# ============================================================
# 用例：(标签, 期望, 标题, 正文, 期望备注)
#   期望取值：
#     "relevant"   —— 必须判相关且**非**待人工
#     "review"     —— 必须待人工（不算噪声，也不能自动通过）
#     "irrelevant" —— 必须排除
# ============================================================
CASES = [
    (
        "PHMSA 安全通告（用户指定的标准）", "relevant",
        "Safety Advisory Notice for the Disposal and Recycling of "
        "Lithium Batteries in Commercial Transportation",
        "PHMSA wants to increase the public's awareness about the dangers "
        "related to shipping lithium batteries for recycling or disposal. "
        "Damaged, defective, or recalled lithium batteries have more "
        "restrictions. See 49 CFR 173.185.",
        "标题即「处置与回收锂电池」—— 标准的形状",
    ),
    (
        "EU 电池法（对照正样本）", "relevant",
        "Regulation (EU) 2023/1542 concerning batteries and waste batteries",
        "This Regulation lays down requirements for sustainability, safety, "
        "labelling and waste battery management, including recycling "
        "efficiency and recycled content obligations.",
        "标题含 waste batteries + 正文退役电池管理",
    ),
    (
        "FR 08913 FEOC 定义（用户标注 irrelevant）", "irrelevant",
        "Interpretation of Foreign Entity of Concern",
        "DOE responds to public comments clarifying the term foreign entity "
        "of concern. It applies to multiple programs related to the battery "
        "supply chain. Section 40207 provides funding to support domestic "
        "battery material processing, manufacturing, and recycling. DOE will "
        "prioritize recycling applicants who will not export recovered "
        "critical materials to a FEOC. In the case of the Battery Materials "
        "Processing and Battery Manufacturing and Recycling Grants programs, "
        "a bright-line rule will afford eligible entities greater clarity.",
        "recycling 只作为拨款项目名出现 —— 财政工具框架必须剔除",
    ),
    (
        "TSCA 新化学物质通告（实测噪声）", "irrelevant",
        "Certain New Chemicals; Receipt and Status Information for 2025",
        "Status information on certain new chemical substances. The list "
        "includes a battery component chemical substance submitted by a "
        "manufacturer.",
        "标题无领域锚点，正文仅一次 incidental 提及",
    ),
    (
        # ⚠️ 设计取舍（有意为之）：单次提及 → **待人工**而不是直接排除。
        #    理由：不能武断地说"只提了一次就一定无关"——回收厂的排放标准
        #    本身就是处置链的合规要求。把判断权交给人，比机器拍板安全。
        #    但它**不再自动判相关**（旧判定会给 0.7 直接放行），噪声已收口。
        "NESHAP 空气排放标准（实测噪声 → 待人工而非通过）", "review",
        "National Emission Standards for Hazardous Air Pollutants: "
        "Chemical Manufacturing Area Sources",
        "The EPA proposes emission standards for chemical manufacturing. A "
        "commenter operating a battery recycler noted thermal process "
        "controls.",
        "单次提及：降为待人工（保守），不自动通过",
    ),
    (
        "FR 09094 清洁车辆抵免（用户标注 relevant）", "review",
        "Clean Vehicle Credits Under Sections 25E and 30D; Transfer of "
        "Credits; Critical Minerals and Battery Components; Foreign "
        "Entities of Concern",
        "This document contains final regulations regarding Federal income "
        "tax credits under the Inflation Reduction Act for clean vehicles, "
        "including plug-in electric vehicles. The final regulations also "
        "provide guidance on transfer of credits and recapture.",
        "材料/供应链类 —— 不排除，但按判据落待人工（用户可一键裁）",
    ),
    (
        "程序性模板：信息收集通告", "irrelevant",
        "Agency Information Collection Activities; Proposed eCollection",
        "In accordance with the Paperwork Reduction Act, the Department "
        "invites comments on information collection activities concerning "
        "battery recycling reporting requirements.",
        "标题是程序性模板 —— 即便正文含处置词也不承载处置政策",
    ),
    (
        "程序性模板：特殊许可通告", "irrelevant",
        "Hazardous Materials: Notice of Actions on Special Permits",
        "PHMSA grants special permits to shippers of spent lithium "
        "batteries for recycling.",
        "许可通告是行政审批个案，不是政策法规",
    ),
    (
        # ⚠️ 实测误收回归（2026-09-12）：首版 transport 模式太宽，
        #    把航空器类别词 "transport category airplanes" 当成货运。
        "航空适航特条件：transport 是航空器类别词", "irrelevant",
        "Special Conditions: Delta Flight Products, Non-Rechargeable "
        "Lithium Batteries Installed in Certain Transport Category Airplanes",
        "These special conditions are issued for the installation of "
        "non-rechargeable lithium batteries and battery systems on certain "
        "transport category airplanes.",
        "transport ≠ 货运：必须要求「运输电池」的句法",
    ),
    (
        "FMVSS 305a 电动车安全标准（新车，不是处置）", "irrelevant",
        "Federal Motor Vehicle Safety Standards; FMVSS No. 305a "
        "Electric-Powered Vehicles",
        "This final rule amends FMVSS No. 305a relating to a National "
        "Transport program for electric-powered vehicles and their "
        "battery systems.",
        "新车安全标准与退役处置无关",
    ),
    (
        # ⚠️ 实测漏网回归（2026-09-12）：程序性表起初只写 "applications for
        #    new" 与 "actions on"，漏了 "Modification To" 变体 ——
        #    24 条审批通告混进了待人工。
        "程序性模板：特殊许可（Modification To 变体）", "irrelevant",
        "Hazardous Materials: Notice of Applications for Modification To "
        "Special Permits",
        "PHMSA received applications for modification to special permits "
        "for transportation of defective lithium ion batteries.",
        "special permits 的每个变体都要覆盖",
    ),
    # ============================================================
    # 以下用例来自**用户在面板上的第二轮审核**（2026-09-12）——
    # 用户的审核就是最权威的标准，必须固化成断言。
    # ============================================================
    (
        "EU 授权法规：supplementing 电池法（用户✅）", "relevant",
        "Commission Delegated Regulation (EU) 2025/606 of 21 March 2025 "
        "supplementing Regulation (EU) 2023/1542 by establishing the "
        "methodology for calculating and verifying the carbon footprint of "
        "batteries",
        "This Regulation establishes the methodology for calculating the "
        "carbon footprint of electric vehicle batteries and industrial "
        "batteries.",
        "授权法案是义务所在 —— 2025/606 碳足迹方法",
    ),
    (
        "EU 立法提案：电池法提案（用户✅）", "relevant",
        "Proposal for a REGULATION OF THE EUROPEAN PARLIAMENT AND OF THE "
        "COUNCIL concerning batteries and waste batteries, repealing "
        "Directive 2006/66/EC",
        "The Commission proposes a Regulation on batteries and waste "
        "batteries covering sustainability, performance and collection "
        "targets.",
        "提案也收（修正了早前「不含提案」的假设）",
    ),
    (
        "EU 修订指令：ELV/电池指令（用户✅）", "relevant",
        "Directive (EU) 2018/849 of the European Parliament and of the "
        "Council of 30 May 2018 amending Directives 2000/53/EC on "
        "end-of-life vehicles, 2006/66/EC on batteries and accumulators",
        "Amendments aligning waste management provisions of the ELV and "
        "batteries directives with the Waste Framework Directive.",
        "ELV 与退役车用电池强相关",
    ),
    (
        "EU 附件技术修订：amending Annex（用户🟡 uncertain）", "review",
        "Commission Delegated Directive (EU) 2020/362 of 17 December 2019 "
        "amending Annex II to Directive 2000/53/EC on end-of-life vehicles",
        "This Delegated Directive amends the technical annex listing "
        "materials and components.",
        "附件级技术修订 → 待人工（用户自己也标了 uncertain）",
    ),
    (
        "EU 泛产品母法：ESPR（用户🟡 uncertain）", "review",
        "Regulation (EU) 2024/1781 establishing a framework for the setting "
        "of ecodesign requirements for sustainable products",
        "This Regulation establishes a framework for ecodesign requirements "
        "for sustainable products, repealing Directive 2009/125/EC.",
        "泛产品母法（电池只是其一） → 待人工",
    ),
    (
        "消费类电池：应排除（用户首轮口径）", "irrelevant",
        "Used Household Batteries | US EPA",
        "Managing used household batteries: alkaline, button cells and "
        "other consumer batteries.",
        "消费类/家用电池不在边界内",
    ),
    (
        "铅酸电池：应排除（用户首轮口径）", "irrelevant",
        "Lead Battery Recycling | Battery Council International",
        "The lead battery industry achieves a 99% recycling rate.",
        "铅酸不在边界内（只要 EV 动力+储能退役+黑粉）",
    ),
    # ============================================================
    # 缺口补采发现的边界 case（2026-09-12 晚）—— 发现层补采 34 条缺口时
    # 实测出的两类系统性误判，必须固化成断言。
    # ============================================================
    (
        # 实测案例：52025XC00214（委员会指南——便携/LMT 电池可拆卸性）。
        # 对象是便携类（边界外），但它是 2023/1542 的官方适用指南。
        # ⭐ 用户裁决（2026-09-12）：「按照中国清单为准 我可能看摘要误判了」
        #    —— 中国清单含「依法适用政策文件」类（指南/公告/技术政策），
        #    本指南即其欧盟对应物 → **应收**（0.75，非自动 0.9）。
        "电池法适用指南：对象为便携类但引电池法（按中国清单应收）", "relevant",
        "Commission Notice – Commission guidelines to facilitate the "
        "harmonised application of provisions on the removability and "
        "replaceability of portable batteries and LMT batteries in "
        "Regulation (EU) 2023/1542",
        "These guidelines clarify the application of the removability and "
        "replaceability requirements.",
        "适用文件类 —— 中国清单「依法适用政策文件」的欧盟对应物",
    ),
    (
        # 实测案例：52025SC0501（中小企业简化包 SWD）。
        # 标题列 6 部被修订法规（含 2023/1542），但内容是中小企业举措。
        # 旧判定靠 2023/1542 硬信号给 0.9 相关 —— 误收。
        "综合立法包：中小企业简化包（电池只是名单之一）", "review",
        "COMMISSION STAFF WORKING DOCUMENT on small mid-cap companies "
        "Accompanying the documents Proposal for a REGULATION amending "
        "Regulations (EU) 2016/679, (EU) 2016/1036, (EU) 2016/1037, "
        "(EU) 2017/1129, (EU) 2023/1542 and (EU) 2024/573 as regards the "
        "extension of certain mitigating measures available for small and "
        "medium sized enterprises to small mid-cap enterprises",
        "This staff working document assesses the impact of the "
        "simplification measures on small mid-cap enterprises.",
        "omnibus 包：电池只以裸法规号出现 → 待人工，不自动通过",
    ),
    (
        # 反例守护：同样是简化包，但含"batteries and waste batteries"实体 →
        # 电池 EPR 条款是包内**实质性内容**，必须保持自动相关。
        # （实测案例：52025AE3982 委员会简化包意见 —— 含电池 EPR 授权代表规则）
        "简化包但含电池 EPR 实体内容（保持相关）", "relevant",
        "Opinion of the European Economic and Social Committee – "
        "Communication from the Commission – Simplifying for sustainable "
        "competitiveness – Proposal for a Regulation amending Regulation "
        "(EU) 2023/1542 and Regulation (EU) 2024/1244 as regards "
        "simplification – suspending the application of the rules on the "
        "appointment of an authorised representative for extended producer "
        "responsibility for batteries and waste batteries and packaging "
        "and packaging waste",
        "The opinion concerns the suspension of rules on authorised "
        "representatives for extended producer responsibility for "
        "batteries and waste batteries.",
        "omnibus 但电池是实体内容 → 不受 omnibus 规则影响",
    ),
]
def main() -> int:
    print("门户类判定 —— 标准样本测试")
    print("=" * 78)
    passed = 0
    for label, expect, title, text, note in CASES:
        v = J(text, title)
        if expect == "relevant":
            ok = v.relevant and not v.needs_human_review
        elif expect == "review":
            ok = v.relevant and v.needs_human_review
        else:
            ok = not v.relevant
        passed += bool(ok)
        mark = "✅" if ok else "❌"
        print(f"{mark} {label}")
        print(f"    期望 {expect:11s} 实得 {_short(v)}")
        if v.hits:
            print(f"    hits: {v.hits[:3]}")
        if v.rejected_by:
            print(f"    rejected_by: {v.rejected_by}")
        if not ok:
            print(f"    ⚠️ 备注：{note}")
    print("=" * 78)
    print(f"通过 {passed}/{len(CASES)}")
    return 0 if passed == len(CASES) else 1


def _short(v) -> str:
    if not v.relevant:
        return "irrelevant"
    if v.needs_human_review:
        return f"review({v.score})"
    return f"relevant({v.score})"


if __name__ == "__main__":
    raise SystemExit(main())
