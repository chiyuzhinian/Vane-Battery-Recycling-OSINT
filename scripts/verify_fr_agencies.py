"""验证 Federal Register 新机构 slug 是否真的可用。

为什么必须验证：**slug 猜错不会报错，只会静默返回 0 条。**
所以每个 slug 都要用"一定能命中的常见词"做对照，区分
    A. slug 无效（机构不存在）→ 永远 0 条
    B. slug 有效但该词无文档 → 这个组合本身就是 0 条

对照组：environmental-protection-agency + "battery"（必然有命中）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import get_connector  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

NEW_SLUGS = [
    "homeland-security-department",
    "justice-department",
    "mine-safety-and-health-administration",
    "council-on-environmental-quality",
    "surface-transportation-board",
    "environment-office-energy-department",
    "trade-representative-office-of-united-states",
    "international-trade-commission",
    "national-transportation-safety-board",
    "national-oceanic-and-atmospheric-administration",
    "agriculture-department",
    "health-and-human-services-department",
]

CONTROL = "environmental-protection-agency"


async def count(term: str, agency: str) -> int:
    conn = get_connector("us_federal")
    try:
        items = await conn.fetch(terms=[term], agencies=[agency],
                                 since="2015-01-01", max_pages=1, per_page=5)
        return len(items)
    except Exception as exc:  # noqa: BLE001
        print(f"      ERR {type(exc).__name__}: {exc}")
        return -1
    finally:
        await conn.aclose()


async def main() -> None:
    print("=" * 88)
    print("对照：environmental-protection-agency + 「battery」（必然有命中）")
    print("=" * 88)
    n = await count("battery", CONTROL)
    print(f"  {CONTROL:<58} {n} 条")
    if n <= 0:
        print("  ⚠️ 对照组就是 0 —— 说明是查询/接口层的问题，下面的结果不可信")
    print()

    print("=" * 88)
    print("新 slug：用「battery」验证有效性，再用本领域词看实际命中")
    print("=" * 88)
    for slug in NEW_SLUGS:
        n1 = await count("battery", slug)
        n2 = await count("black mass", slug)
        ok = "✅" if n1 > 0 else "❓"
        print(f"  {ok} {slug:<58} battery={n1:>3}  black mass={n2:>3}")


if __name__ == "__main__":
    asyncio.run(main())
