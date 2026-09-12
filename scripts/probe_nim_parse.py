# -*- coding: utf-8 -*-
"""解析 EUR-Lex NIM（成员国转化措施）页面 —— 探测脚本。

目标：验证「一个页面覆盖全部 27 国」的可解析性。
用法：py scripts/probe_nim_parse.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

html = (ROOT / "outputs" / "_nim_elv.html").read_text(encoding="utf-8",
                                                      errors="replace")
print(f"HTML {len(html)} 字符\n")

# 1) 找国家块：形如 id="XXX_transposition"
countries = re.findall(r'id="([A-Z]{3})_transposition"', html)
print(f"国家块 {len(countries)} 个: {countries}\n")

# 2) 找 numOfNims（该国条目数）
for cc in countries[:6]:
    m = re.search(rf'id="{cc}_numOfNims"[^>]*>(.*?)<', html, re.S)
    n = m.group(1).strip() if m else "?"
    print(f"  {cc}: numOfNims={n}")

# 3) 提取每个 NIM 条目链接（全局）
entries = re.findall(
    r'href="([^"]*uri=NIM:(\d+))"[^>]*>([^<]{8,300})</a>', html)
print(f"\nNIM 条目总数: {len(entries)}")
for href, num, title in entries[:10]:
    print(f"  NIM:{num}  {title[:110]}")

# 4) 看国家归属：条目出现在哪个国家块之间
#    （取 BEL_transposition 到下一个 _transposition 的距离）
idx_bel = html.find('id="BEL_transposition"')
if idx_bel > 0:
    seg = html[idx_bel: idx_bel + 200000]
    nxt = re.search(r'id="[A-Z]{3}_transposition"', seg[50:])
    end = (50 + nxt.start()) if nxt else len(seg)
    bel_seg = seg[:end]
    bel_items = re.findall(r'uri=NIM:(\d+)', bel_seg)
    print(f"\nBEL 块内条目数: {len(bel_items)}")
    print(f"BEL 条目: {bel_items[:20]}")

# 5) 顺带看 NIM 详情页有没有正文/国家链接（用已下载的？没有——打印统计即可）
print("\n完成。")
