"""验证 Vane 通道（通道 A）是否真的打通 —— 从「连接」到「产出证据」全链路。

为什么单独写这个脚本
--------------------
    通道 A 是**可选通道**：没部署 Vane 时主管线要能安静跳过。
    所以上线前必须先回答三个问题：
      1. Vane 到底起来没有？（probe）
      2. 模型配好了没有？（/api/providers 有没有 chat + embedding）
      3. **搜出来的东西，判定器认不认？**（最关键 —— 采到了但判不相关等于白采）

用法
----
    py scripts/test_vane_channel.py                      # 用默认查询
    py scripts/test_vane_channel.py "自定义查询串"        # 自定义
    py scripts/test_vane_channel.py --sources web,academic
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from app.connectors import get_connector            # noqa: E402
from app.connectors.base import ConnectorError      # noqa: E402
from app.core.relevance import judge                # noqa: E402

# 默认查询：直接问本项目最关心的东西，顺带检验 Vane 能不能发现**新源**
DEFAULT_QUERY = (
    "black mass from end-of-life EV batteries: cross-border shipment rules, "
    "recyclers and capacity in EU and US"
)


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if args else DEFAULT_QUERY
    sources = ("web",)
    for a in sys.argv[1:]:
        if a.startswith("--sources"):
            sources = tuple(a.split("=", 1)[-1].split(",")) if "=" in a else ("web",)

    conn = get_connector("vane")

    print("=" * 78)
    print("① 存活探测")
    print("=" * 78)
    probe = await conn.probe()
    print(f"   {probe}")
    if not probe.reachable:
        print("\n❌ Vane 未运行。启动命令：")
        print("   docker run -d -p 3000:3000 -v vane-data:/home/vane/data "
              "--name vane itzcrazykns1337/vane:latest")
        print("   然后打开 http://localhost:3000 完成 setup（填 LLM API Key）")
        await conn.aclose()
        return 1
    if probe.error:
        print(f"\n⚠️ 服务在跑但模型未配好：{probe.error}")
        await conn.aclose()
        return 2

    print("\n" + "=" * 78)
    print(f"② 真实查询：{query}")
    print("=" * 78)
    try:
        items = await conn.fetch(query, sources=sources)
    except ConnectorError as exc:
        print(f"   ❌ {exc}")
        await conn.aclose()
        return 3
    print(f"   返回 {len(items)} 条引用来源\n")

    print("=" * 78)
    print("③ 判定器是否认可（这是通道 A 有没有价值的关键）")
    print("=" * 78)
    kept = 0
    for i, it in enumerate(items, 1):
        v = judge(it.raw_text, it.source_title, scenario="policy")
        kept += 1 if v.relevant else 0
        mark = "✅" if v.relevant else "❌"
        print(f"  {i:>2}. {mark} {v.score:>4.1f}  {(it.source_title or '')[:62]}")
        print(f"      {it.source_url[:88]}")

    print(f"\n   相关率：{kept}/{len(items)}"
          f"（{kept / len(items) * 100:.0f}%）" if items else "   （无结果）")

    if items:
        print("\n" + "=" * 78)
        print("④ Vane 的答案（仅供人工发现线索，不入库）")
        print("=" * 78)
        print("   " + (items[0].meta.get("vane_answer") or "")[:500])

    await conn.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
