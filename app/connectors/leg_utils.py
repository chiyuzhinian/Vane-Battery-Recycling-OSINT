# -*- coding: utf-8 -*-
"""leg_utils —— 立法类 HTML 站点的共享解析工具（Phase 4B-2A Step 5）。

为什么需要：SE(SFST)/PL(ISAP)/FI(Finlex)/US-CA(leginfo)/US-WA(RCW) 都是
服务端渲染的立法站点，正文形态不同但"去标签→取标题→取正文"的步骤一致。
共享解析器 + 站点级薄连接器（只声明 URL 结构），避免 6 份重复代码。
"""
from __future__ import annotations

import html as _html
import json as _json
import re

_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_BLOCK_RE = re.compile(r"</?(p|div|br|li|tr|h[1-6]|section|article)[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

#: Next.js 流式载荷（self.__next_f.push([1,"…"])）—— 实测 Finlex 的法条正文在其中
#: （页面 <script> 被常规 strip 误删 → 正文丢失）。
_NEXT_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)')

#: React flight 树中的文本节点（"text":"…"）—— 实测 Finlex 的法条标题/条款文本在此
_TEXT_NODE_RE = re.compile(r'"text":"((?:[^"\\]|\\.)*)"')


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


def extract_next_flight(html: str) -> str:
    """从 Next.js 流式载荷（__next_f）中提取服务端数据（拼接为文本）。

    实测（2026-09-13）：Finlex 页面为 React 流式渲染，法条正文（"12 §"/"1 luku"）
    存在于 `self.__next_f.push([1,"..."])` 的 JSON 字符串分片中；
    常规 strip_html 会连 <script> 一起删除 → 正文丢失。
    本函数仅回放**服务端已下发**的数据（与浏览器所见一致），不做任何伪造。
    """
    chunks = _NEXT_FLIGHT_RE.findall(html or "")
    if not chunks:
        return ""
    parts: list[str] = []
    for c in chunks:
        try:
            parts.append(_json.loads(c))
        except Exception:  # noqa: BLE001 —— 单分片解码失败不中断
            continue
    return "".join(parts)


def extract_text_nodes(payload: str) -> str:
    """从 React flight 树中抽取全部 `"text":"…"` 节点并拼接为文本。

    实测（Finlex Jätelaki）：3.4MB 页面 → 2.9MB 解码载荷 → 1042 个文本节点、
    约 2.8 万字符（含标题/条款文本；"Akkujen ja paristojen" 等电池条款在场）。
    """
    vals = _TEXT_NODE_RE.findall(payload or "")
    out: list[str] = []
    for v in vals:
        try:
            out.append(_json.loads('"' + v + '"'))
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out)


def trim_nav(text: str, *, min_len: int = 120, scan_lines: int = 160) -> tuple[str, int]:
    """裁掉开头的站点导航/菜单行，让**法条正文前置**。

    背景（实测）：RCW/leginfo/SFST 页面的 stripped 文本开头是
    “Menu Website Search Term …” 导航（>1000 字符），而验收分类只扫
    `text[:1600]` → 真法案被判 NO_THEME/D。导航是样板内容，裁头不丢正文。

    算法：在前 scan_lines 行内找到首个“长行”（长度 ≥ min_len 且空格多，
    视为正文段落），从其前 2 行开始保留；找不到则原样返回。
    → (裁剪后文本, 被裁字符数)
    """
    lines = (text or "").splitlines()
    if not lines:
        return "", 0
    for i, ln in enumerate(lines[:scan_lines]):
        if len(ln) >= min_len and ln.count(" ") >= 12:
            start = max(0, i - 2)
            removed = sum(len(x) + 1 for x in lines[:start])
            return "\n".join(lines[start:]), removed
    return text, 0
