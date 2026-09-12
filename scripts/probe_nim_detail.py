# -*- coding: utf-8 -*-
"""探测 NIM 详情页可提取的字段结构。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

html = (ROOT / "outputs" / "_nim_detail.html").read_text(encoding="utf-8",
                                                         errors="replace")
print(f"HTML {len(html)} 字符\n")

# 1) meta 字段
for pat, label in [
    (r'<meta name="WT\.z_docTitle" content="([^"]+)"', "docTitle"),
    (r'<meta name="WT\.z_docType" content="([^"]+)"', "docType"),
    (r'<meta name="WT\.z_docId" content="([^"]+)"', "docId"),
    (r'<meta name="WT\.z_country" content="([^"]+)"', "country"),
    (r'<meta name="WT\.z_pubDate" content="([^"]+)"', "pubDate"),
    (r'<meta name="WT\.z_language" content="([^"]+)"', "language"),
]:
    m = re.search(pat, html)
    print(f"{label:10s}: {(m.group(1) if m else '—')[:120]}")

# 2) 正文主体（找 document 内容区）
body = re.search(r'id="documentContent"[\s\S]{0,400}', html)
print(f"\ndocumentContent 存在: {bool(body)}")
if body:
    print(re.sub(r"<[^>]+>", " ", body.group(0))[:300])

# 3) 常见标签（多语言）
for lbl in ["Publication reference", "Référence", "Date of publication",
            "Entry into force", "En vigueur", "Member State", "Country"]:
    for m in re.finditer(re.escape(lbl), html):
        seg = html[m.start():m.start() + 260]
        seg = re.sub(r"<[^>]+>", " ", seg)
        seg = re.sub(r"\s+", " ", seg)
        print(f"\n[{lbl}] {seg[:220]}")
        break

# 4) 国家代码与 NIM 号在 <title> 里
m = re.search(r"<title>([^<]+)</title>", html)
print(f"\n<title>: {m.group(1) if m else '—'}")
