# -*- coding: utf-8 -*-
"""leg_utils —— 立法类 HTML 站点的共享解析工具（Phase 4B-2A Step 5）。

为什么需要：SE(SFST)/PL(ISAP)/FI(Finlex)/US-CA(leginfo)/US-WA(RCW) 都是
服务端渲染的立法站点，正文形态不同但"去标签→取标题→取正文"的步骤一致。
共享解析器 + 站点级薄连接器（只声明 URL 结构），避免 6 份重复代码。
"""
from __future__ import annotations

import html as _html
import re

_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_BLOCK_RE = re.compile(r"</?(p|div|br|li|tr|h[1-6]|section|article)[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def strip_html(html: str) -> str:
    """去脚本/样式/标签，保留段落换行，压掉重复空白。"""
    t = _SCRIPT_RE.sub(" ", html or "")
    t = _BLOCK_RE.sub("\n", t)
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    t = _WS_RE.sub(" ", t)
    lines = [ln.strip() for ln in t.splitlines()]
    return _BLANK_RE.sub("\n\n", "\n".join(ln for ln in lines if ln)).strip()


def extract_title(html: str) -> str:
    """页面标题：<title> → 回退 <h1>。"""
    for rx in (_TITLE_RE, _H1_RE):
        m = rx.search(html or "")
        if m:
            title = _html.unescape(_TAG_RE.sub("", m.group(1)))
            title = _WS_RE.sub(" ", title).strip()
            if title:
                return title
    return ""


def find_iso_date(text: str) -> str:
    m = _DATE_RE.search(text or "")
    return m.group(1) if m else ""


#: 反爬/挑战页标记（命中即不得当作正文；必须记为 SOURCE_FAILURE，不是 0 结果）
_CHALLENGE_MARKERS: tuple[tuple[str, re.Pattern], ...] = (
    ("pardon_our_interruption", re.compile(r"pardon our interruption", re.I)),
    ("cloudflare_challenge", re.compile(r"just a moment", re.I)),
    ("access_denied", re.compile(r"access denied", re.I)),
    ("captcha", re.compile(r"recaptcha|captcha", re.I)),
    ("js_required", re.compile(r"enable javascript|javascript is required", re.I)),
)


def detect_challenge(html: str) -> str:
    """检测反爬/挑战页；返回标记名或空串。"""
    head = (html or "")[:20000]
    for name, rx in _CHALLENGE_MARKERS:
        if rx.search(head):
            return name
    return ""
