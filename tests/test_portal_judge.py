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
