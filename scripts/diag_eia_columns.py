"""环评"受理公示"专栏入口发现工具。

背景
----
上一轮发现：省级生态环境厅的**首页**给的是政策与审批原则，不是企业项目公示。
企业级产能/废料量数据在各站的「建设项目环评受理公示」专栏里。

本工具遍历 eia-sources.yaml 中登记的站点，抓首页并找出所有"像环评专栏"的链接，
输出候选入口供人工确认后回填配置。

用法：py scripts/diag_eia_columns.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import yaml  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ANCHOR_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")

# 想要的栏目：受理 / 公示 / 审批 / 环评 相关
WANT = ["受理", "公示", "审批", "环境影响", "环评"]
# 明确排除：政策解读、党建、办事指南等常见噪声
DENY = ["政策解读", "党建", "学习贯彻", "办事指南", "表格下载", "联系我们",
        "网站地图", "无障碍", "登录", "注册", "意见征集", "法律法规"]


async def discover(client: httpx.AsyncClient, site: dict) -> None:
    url = site["url"]
    print("=" * 96)
    print(f" {site['id']}  {site['name']}")
    print(f" {url}")
    print("=" * 96)
    try:
        r = await client.get(url, timeout=35.0)
        html = r.text
        if len(html) < 3000:
            print(f" ⚠️ 疑似挑战页（{len(html)} bytes），跳过\n")
            return
    except Exception as exc:  # noqa: BLE001
        print(f" ❌ {type(exc).__name__}: {str(exc)[:100]}\n")
        return

    hits: dict[str, str] = {}
    for href, raw in ANCHOR_RE.findall(html):
        text = TAG_RE.sub("", raw).replace("&nbsp;", " ").strip()
        if not (2 <= len(text) <= 40):
            continue
        if not any(w in text for w in WANT):
            continue
        if any(d in text for d in DENY):
            continue
        full = urljoin(url, href)
        if urlparse(full).netloc != urlparse(url).netloc:
            continue
        hits.setdefault(full, text)

    if not hits:
        print(" （首页未找到环评专栏链接，可能需要二级页跳转）\n")
        return

    # 优先展示含"受理""公示"的
    ranked = sorted(hits.items(), key=lambda kv: (
        0 if "受理" in kv[1] else 1, 0 if "公示" in kv[1] else 1, len(kv[1])))
    for full, text in ranked[:12]:
        print(f"   · {text:<26} {full}")
    print()


async def main() -> None:
    cfg = yaml.safe_load((ROOT / "sources" / "eia-sources.yaml").read_text(encoding="utf-8"))
    sites = [s for s in cfg.get("sources", []) if s.get("enabled", True)]

    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=35.0, follow_redirects=True,
    ) as client:
        for s in sites:
            await discover(client, s)


if __name__ == "__main__":
    asyncio.run(main())
