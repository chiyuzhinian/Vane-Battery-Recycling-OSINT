"""企业侧数据源接口探测 —— 在写连接器之前先摸清真实接口。

用法：py scripts/diag_cn_sources.py

探测目标：
  1) 巨潮资讯（cninfo）：公告 / 年报 —— 上市公司的官方披露平台
  2) 环评公示（EIA）—— 非上市企业的唯一产能/废料量来源，最关键的缺口
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


async def probe(client: httpx.AsyncClient, label: str, method: str, url: str, **kw) -> None:
    try:
        if method == "GET":
            r = await client.get(url, **kw)
        else:
            r = await client.post(url, **kw)
        ct = r.headers.get("content-type", "")
        body = r.text
        preview = body[:300].replace("\n", " ")
        print(f"[{r.status_code}] {label}")
        print(f"      {url[:110]}")
        print(f"      {ct}  {len(r.content)} bytes")
        print(f"      {preview[:260]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR ] {label}: {type(exc).__name__}: {str(exc)[:140]}")
        print(f"      {url[:110]}")
    print()


async def main() -> None:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "http://www.cninfo.com.cn/",
    }
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as c:

        print("=" * 90)
        print(" 一、巨潮资讯（cninfo）接口探测")
        print("=" * 90)

        # 1. 全文检索（最省事：不需要 orgId）
        await probe(
            c, "cninfo 全文检索 fulltextSearch",
            "GET",
            "http://www.cninfo.com.cn/new/fulltextSearch/full",
            params={
                "searchkey": "动力电池回收",
                "sdate": "", "edate": "",
                "isfulltext": "false", "sortName": "nothing", "sortType": "desc",
                "pageNum": "1", "pageSize": "10",
            },
        )

        # 2. 历史公告查询（官方接口，需要 stock=代码,orgId）
        await probe(
            c, "cninfo 历史公告 query（带 orgId）",
            "POST",
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data={
                "pageNum": "1", "pageSize": "10",
                "column": "szse", "tabName": "fulltext",
                "plate": "", "stock": "002340,gssz0002340",
                "searchkey": "", "secid": "", "category": "",
                "trade": "", "seDate": "2024-01-01~2026-09-10",
                "sortName": "", "sortType": "", "isHLtitle": "true",
            },
        )

        # 3. 历史公告查询（不带 stock，走关键词全市场检索）
        await probe(
            c, "cninfo 历史公告 query（纯关键词）",
            "POST",
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data={
                "pageNum": "1", "pageSize": "10", "column": "szse",
                "tabName": "fulltext", "plate": "", "stock": "",
                "searchkey": "电池回收", "secid": "", "category": "",
                "trade": "", "seDate": "", "sortName": "", "sortType": "",
                "isHLtitle": "true",
            },
        )

        # 4. 深交所/上交所关键词检索（不同 column）
        for col in ("sse", "szse"):
            await probe(
                c, f"cninfo 全市场检索 column={col}",
                "POST",
                "http://www.cninfo.com.cn/new/fulltextSearch/full",
                data={
                    "searchkey": "电池回收", "sdate": "", "edate": "",
                    "isfulltext": "false", "sortName": "nothing",
                    "sortType": "desc", "pageNum": "1", "pageSize": "10",
                },
            )

        print("=" * 90)
        print(" 二、环评公示（EIA）接口探测")
        print("=" * 90)

        for label, url in [
            ("生态环境部-环评管理", "https://www.mee.gov.cn/ywgz/hjyxpj/"),
            ("生态环境部-受理公示", "https://www.mee.gov.cn/ywgz/hjyxpj/jsxmhjyxpj/"),
            ("湖南省生态环境厅", "https://sthjt.hunan.gov.cn/"),
            ("广东省生态环境厅", "https://gdee.gd.gov.cn/"),
            ("江苏省生态环境厅", "https://sthjt.jiangsu.gov.cn/"),
            ("江西省生态环境厅", "http://sthjt.jiangxi.gov.cn/"),
            ("全国环评信息公开(中国环评网)", "https://www.chinaeia.com/"),
        ]:
            await probe(c, label, "GET", url)


if __name__ == "__main__":
    asyncio.run(main())
