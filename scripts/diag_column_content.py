"""查看指定栏目的实际条目内容 —— 用于判断"这个栏目是不是我要的"。

用法：py scripts/diag_column_content.py
（URL 列表写在下面的 TARGETS 里）
"""

from __future__ import annotations

import asyncio
import re
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

TARGETS = [
    ("广东-审批文件公示公告(当前用的)", "https://gdee.gd.gov.cn/gsgg/index.html"),
    ("广东-建设项目环评审批", "https://gdee.gd.gov.cn/hp5836/index.html"),
    ("广东-环境影响评价", "https://gdee.gd.gov.cn/hpsp/index.html"),
    ("宁德-市生态环境局", "https://sthjj.ningde.gov.cn/"),
    ("宜春-市生态环境局", "https://sthjj.yichun.gov.cn/"),
    ("荆门-市生态环境局", "http://sthjj.jingmen.gov.cn/"),
]

ANCHOR_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
_ARTICLE = re.compile(r"(20\d{2})[-_/]|/\d{5,}|\.(s?html?|jsp|aspx?)(\?|$)", re.I)


async def main() -> None:
    async with httpx.AsyncClient(headers={"User-Agent": UA},
                                 timeout=35.0, follow_redirects=True) as c:
        for name, url in TARGETS:
            print("=" * 92)
            print(f" {name}\n {url}")
            print("=" * 92)
            try:
                r = await c.get(url)
                html = r.text
            except Exception as exc:  # noqa: BLE001
                print(f" ❌ {type(exc).__name__}\n")
                continue

            titles = []
            for href, raw in ANCHOR_RE.findall(html):
                if not _ARTICLE.search(href):
                    continue
                t = TAG_RE.sub("", raw).replace("&nbsp;", " ").strip()
                t = re.sub(r"\s+", " ", t)
                if 10 <= len(t) <= 120:
                    titles.append(t)

            # 去重保序
            seen, uniq = set(), []
            for t in titles:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)

            print(f" 条目数 {len(uniq)}")
            # 统计行业噪声占比
            noise = ["核技术", "医院", "医疗", "辐照", "CT", "探伤", "放射性",
                     "输变电", "海砂", "航道", "水库", "道路", "医院"]
            n_noise = sum(1 for t in uniq if any(k in t for k in noise))
            battery = ["电池", "锂", "正极", "负极", "前驱体", "回收", "梯次", "黑粉", "新能源"]
            n_batt = sum(1 for t in uniq if any(k in t for k in battery))
            print(f"   → 核技术/医疗类噪声 {n_noise} 条（{n_noise/max(len(uniq),1)*100:.0f}%）"
                  f" | 电池相关 {n_batt} 条")
            for t in uniq[:8]:
                print(f"     · {t[:80]}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
