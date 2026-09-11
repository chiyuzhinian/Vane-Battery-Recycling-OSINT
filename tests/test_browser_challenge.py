"""JS 人机验证（WAF challenge）识别测试 —— py tests/test_browser_challenge.py

为什么需要
----------
这是 2026-09-11 踩过的坑，代价是差点把 ECHA 整站误判为"不可用"：

    ECHA 的 Azure WAF 返回 403 + 一张 JS 挑战页
    （"One moment, we're checking you're not a bot."）
    挑战跑完约 6-9 秒后，页面**正常加载**。

    但首版浏览器层只等 1.2 秒就取正文 → 拿到的是挑战页
    → 页面标题 "Azure WAF"、正文 1030 字符
    → 被记为「403 反爬」，ECHA 在源清单里长期挂着 blocked。

教训：**403 不等于硬拦截。判定一个源失效之前，必须给它通过挑战的时间。**

这个测试确保：
  ① 真实的挑战页能被识别（否则会等不到、直接抓走挑战页）
  ② 正常内容页不会被误判为挑战页（否则每页都白等 8 秒）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors.browser import _CHALLENGE_RE  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


# 真实抓到的挑战页（2026-09-11，ECHA / Azure WAF）
REAL_CHALLENGE = (
    "Azure WAF\n"
    "One moment, we're checking you're not a bot.\n"
    "d53e6fd8842b047664669f2cc49fffd5"
)

# 真实抓到的正常内容页（挑战通过后）
REAL_CONTENT = (
    "Understanding the Batteries Regulation - ECHA\n"
    "An agency of the European Union Sign In English (en) About us "
    "Regulations Batteries Regulation The new Batteries Regulation "
    "(EU) 2023/1542 entered into force on 17 August 2023 and repeals "
    "the Batteries Directive 2006/66/EC. ECHA supports the implementation "
    "of the Regulation, in particular for substances in batteries."
)

OTHER_CHALLENGES = [
    ("Cloudflare", "Just a moment...\nChecking your browser before accessing."),
    ("通用 JS 要求", "Please enable JavaScript to continue."),
    ("验证码", "Please complete the CAPTCHA to proceed."),
    ("DDoS 防护", "DDoS protection by Cloudflare"),
    ("人工确认", "Verifying you are human. This may take a few seconds."),
]

NOT_CHALLENGES = [
    ("欧盟电池法正文", "Regulation (EU) 2023/1542 on batteries and waste "
                       "batteries. This Regulation lays down requirements for "
                       "sustainability, safety, labelling and information."),
    ("PHMSA 通告", "Safety Advisory Notice for the Transportation of Lithium "
                   "Batteries for Disposal or Recycling. Issued Date: May 17, 2022."),
    ("提到 JS 的普通页", "This guidance explains how to enable reporting under "
                        "the Batteries Regulation. JavaScript is used on this "
                        "site for interactive charts."),
]


def main() -> int:
    print("JS 人机验证识别测试")
    print("=" * 84)
    results = []

    hit = any(rx.search(REAL_CHALLENGE) for rx in _CHALLENGE_RE)
    results.append(("① 真实 ECHA/Azure WAF 挑战页被识别", hit))
    print(f"  {'✅' if hit else '❌'} ① 真实挑战页 → {'识别为挑战' if hit else '漏判！'}")

    miss = any(rx.search(REAL_CONTENT) for rx in _CHALLENGE_RE)
    results.append(("② 正常内容页不被误判", not miss))
    print(f"  {'✅' if not miss else '❌'} ② 正常内容页 → "
          f"{'误判为挑战！' if miss else '正确放行'}")

    for name, text in OTHER_CHALLENGES:
        ok = any(rx.search(text) for rx in _CHALLENGE_RE)
        results.append((f"③ 其他挑战页：{name}", ok))
        print(f"  {'✅' if ok else '❌'} ③ {name:<12} → {'识别' if ok else '漏判'}")

    for name, text in NOT_CHALLENGES:
        ok = not any(rx.search(text) for rx in _CHALLENGE_RE)
        results.append((f"④ 非挑战页：{name}", ok))
        print(f"  {'✅' if ok else '❌'} ④ {name:<14} → {'放行' if ok else '误判为挑战'}")

    print("-" * 84)
    passed = sum(1 for _, ok in results if ok)
    print(f"  通过 {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
