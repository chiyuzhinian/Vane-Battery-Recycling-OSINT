"""空壳内容防护测试 —— py tests/test_empty_content_guard.py

本轮最贵的一类缺陷：**记录存在，但内容为空。**

三处同型故障（2026-09-11）
------------------------
① 荷兰 BWB：`/bwb/{ID}` 返回 `<work>` WTI 元数据（6,090 字符，`autowrak` 出现 0 次）
   → 采集"成功"，但一个字法条都没有。
② EUR-Lex `Q_CELEX`：早期漏 select `expression_title`
   → raw_text 只有占位符 `EU legislation CELEX 32024R1157`
   → 黑粉①线《废物运输条例》被丢弃（不是规则错，是没内容可判）。
③ EUR-Lex 元数据记录：正文早已落盘，但记录里只有 CELEX 号
   → **报废车指令 2000/53/EC（ELV 主干法）被判为不相关**。

共性：采集层、存储层、判定层各自看起来都正常，
坏在"交出去的东西是空的"——不报错、不丢数据、指标正常。

本测试锁住两个防护：
  · 连接器遇到空壳形态必须**报错**，不允许静默入库
  · 判定前必须**并入已落盘的正文快照**
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors.base import ConnectorError  # noqa: E402
from app.connectors.bwb_nl import BwbNlConnector  # noqa: E402
from app.connectors.eur_lex import FULLTEXT_DIR, EurLexConnector  # noqa: E402
from app.core.relevance import judge_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 作品级 <work> XML 的真实开头（荷兰 BWBR0013707，纯元数据）
WORK_SHELL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<work xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    "<meta><datum_ontvangst>2002-07-02</datum_ontvangst>"
    "<hash>aa6b0735dab5d604f61a834d30960c49763c1cf6fa351</hash></meta>"
    "</work>"
)

# 版本级 <toestand> XML（含法条正文）
TOESTAND = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<toestand><kop><titel>Besluit beheer autowrakken</titel></kop>"
    "<artikel><al>In deze regeling wordt verstaan onder autowrak: een voertuig "
    "dat als afvalstof wordt aangemerkt.</al></artikel></toestand>"
)


def main() -> int:
    print("=" * 74)
    print("空壳内容防护测试")
    print("=" * 74)
    print()

    ok = total = 0

    # ---- ① BWB：<work> 必须报错，不允许静默入库 ----
    total += 1
    conn = BwbNlConnector()
    try:
        conn._parse_xml(WORK_SHELL.encode())
        print("  ❌ <work> 空壳被静默接受 —— **会导致'成功但空壳'的记录入库**")
    except ConnectorError as exc:
        ok += 1
        print(f"  ✅ <work> 空壳被拒：{str(exc)[:78]}")

    # ---- ② BWB：正常的 <toestand> 必须能解析出法条 ----
    total += 1
    text, meta = conn._parse_xml(TOESTAND.encode())
    if "autowrak" in text and meta.get("root") == "toestand":
        ok += 1
        print(f"  ✅ <toestand> 正常解析：{len(text)} 字符，root={meta['root']}")
    else:
        print(f"  ❌ <toestand> 解析异常：{len(text)} 字符 root={meta.get('root')}")

    # ---- ③ EUR-Lex：正文快照必须并入判定文本 ----
    total += 1
    celex = "32000L0053"                     # 报废车指令
    snapshot = FULLTEXT_DIR / f"{celex}.txt"
    meta_only = f"EU legislation CELEX {celex}"
    if not snapshot.exists():
        print(f"  ⚠️ 跳过：{snapshot} 不存在（先跑 scripts/fetch_eurlex_fulltext.py）")
        total -= 1
    else:
        merged = EurLexConnector._with_fulltext(celex, meta_only)
        grew = len(merged) > len(meta_only) + 1000
        print(f"  {'✅' if grew else '❌'} 空壳 {len(meta_only)} 字符 → "
              f"合并后 {len(merged)} 字符")
        ok += grew

    # ---- ④ EUR-Lex：合并后 ELV 指令必须判为相关（修复前它被判不相关）----
    total += 1
    if snapshot.exists():
        v = judge_policy(EurLexConnector._with_fulltext(celex, meta_only),
                         f"EU legislation CELEX {celex}")
        good = bool(getattr(v, "relevant", False))
        ok += good
        print(f"  {'✅' if good else '❌'} 合并后判定：relevant={v.relevant} "
              f"score={v.score} hits={getattr(v, 'hits', [])[:3]}")
        if not good:
            print("       ← **ELV 主干法被静默丢弃**（英语 ELV 词族缺失）")
    else:
        total -= 1

    print()
    print("-" * 74)
    print(f"  通过 {ok}/{total}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
