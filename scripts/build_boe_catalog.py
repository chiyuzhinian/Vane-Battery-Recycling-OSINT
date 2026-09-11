"""一次性构建 BOE 立法整合库目录（~12,000 部），落盘缓存。

用法
----
    py scripts/build_boe_catalog.py               # 用缓存（未过期则不重扫）
    py scripts/build_boe_catalog.py --refresh     # 强制重扫
    py scripts/build_boe_catalog.py --pages 400   # 限制页数

为什么要建目录
--------------
BOE 的 `?offset=N` 是**真翻页**，但**没有标题检索 API**：
    · `?titulo=` / `?materia=` / `?rango=` 一律 400 "Parámetros no soportados"
    · 网页检索页 `/buscar/legislacion.php` 的结果不落在 HTML 里（JS 渲染）
    · **绝不能猜编号** —— 猜的两个 BOE-A 编号全部 404
所以正解是德国 `gii-toc.xml` 那一套：**先拿全量目录，再本地筛标题**。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import get_connector  # noqa: E402
from app.connectors.boe_es import CATALOG_CACHE  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


async def main(refresh: bool, pages: int) -> None:
    conn = get_connector("es_boe")
    print("枚举 BOE 立法整合库目录…")
    laws = await conn.catalog(max_pages=pages, refresh=refresh)
    print(f"目录共 {len(laws)} 部（缓存：{CATALOG_CACHE}）")

    for score, label in [(3, "专有词（电池/报废车）"), (2, "中等（破碎/回收）"),
                         (1, "通用废物")]:
        hits = conn.match(laws, min_score=score)
        hits = [h for h in hits if h["score"] == score]
        print(f"\n分={score} {label}：{len(hits)} 部")
        for h in hits[:25]:
            est = "国家" if (h.get("ambito") == "Estatal") else "地方"
            vig = h.get("vigencia_agotada") or "?"
            print(f"   [{est}/{vig}] {h['id']}  {(h.get('titulo') or '')[:88]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--pages", type=int, default=400)
    a = ap.parse_args()
    asyncio.run(main(a.refresh, a.pages))
