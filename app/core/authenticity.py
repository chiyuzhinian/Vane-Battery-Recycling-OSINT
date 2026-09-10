"""源真实性校验 —— 保证"数据源本身是真的"。

防线设计（与 sources/search-boundary.yaml 的 source_authenticity 段对应）
------------------------------------------------------------------------
  L1 域名白名单      : 是否匹配 *.gov / *.europa.eu 等可信模式
  L2 同形字检测      : 防 gоv.cn（西里尔字母 о）冒充 gov.cn
  L3 编辑距离        : 与白名单域名距离 ≤2 的"近似域名"一律告警
  L4 TLS/跳转链      : 证书有效 + 跳转不落到非白名单域名
  L5 主办方声明      : 页面是否声明主管/主办单位（抓取后二次校验）

注意：本模块只判"源"的真伪，不判"数据"的对错。
     数据真伪由 engines/validator.py 的五层交叉验证负责（见 04 篇 §2.4）。
"""

from __future__ import annotations

import ipaddress
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

# ---------- 白名单模式（后缀匹配）----------
TRUSTED_SUFFIXES: tuple[str, ...] = (
    ".gov", ".gov.cn", ".gov.uk", ".gov.au",
    ".europa.eu", ".edu", ".edu.cn", ".ac.cn", ".org.cn",
    ".mil",
)

# 需要精确匹配的域名（europa.eu 的常用子站）
TRUSTED_EXACT: tuple[str, ...] = (
    "eur-lex.europa.eu",
    "publications.europa.eu",
    "environment.ec.europa.eu",
    "echa.europa.eu",
    "ec.europa.eu",
    "federalregister.gov",
    "www.federalregister.gov",
    "congress.gov",
    "api.congress.gov",
)

# 已人工确认的行业源（需定期复核）
INDUSTRY_CONFIRMED: tuple[str, ...] = (
    "cninfo.com.cn",
    "smm.cn",
)

# 已知的反爬/不可直采站点（不是"假"，是"抓不到"）
KNOWN_BLOCKED: tuple[str, ...] = (
    "echa.europa.eu",     # 实测 403
)

# 同形字表：西里尔/希腊字母 → 拉丁字母（最常见的域名仿冒手法）
CONFUSABLES: dict[str, str] = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0445": "x", "\u0443": "y", "\u0456": "i",
    "\u03bf": "o", "\u03b1": "a", "\u03c1": "p", "\u03bd": "v",
    "\u0131": "i", "\u2010": "-", "\u2011": "-",
}


@dataclass
class AuthenticityResult:
    url: str
    host: str
    trusted: bool
    tier: str                                  # official | industry | unknown | suspicious
    checks: dict[str, bool] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    blocked: bool = False                      # 反爬拦截（可换入口，不是造假）

    def __str__(self) -> str:
        icon = "✅" if self.trusted else ("🚫" if self.blocked else "❌")
        return (f"{icon} {self.host} tier={self.tier}"
                + (f" 违规={self.violations}" if self.violations else ""))


def normalize_confusables(text: str) -> str:
    """把同形字替换回拉丁字母，便于比对。"""
    out = []
    for ch in text:
        out.append(CONFUSABLES.get(ch, ch))
    return "".join(out)


def has_mixed_script(text: str) -> bool:
    """是否混用了不同文字系统（典型的同形字攻击特征）。"""
    scripts = set()
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        scripts.add(name.split()[0])       # LATIN / CYRILLIC / GREEK ...
    return len(scripts) > 1


def levenshtein(a: str, b: str) -> int:
    """标准编辑距离（仅用于短域名比对，无需优化）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def check_url(url: str) -> AuthenticityResult:
    """对单个 URL 做源真实性判定。"""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    res = AuthenticityResult(url=url, host=host, trusted=False, tier="unknown")

    if not host:
        res.violations.append("无主机名")
        return res

    # --- L1 域名白名单 ---
    if _is_ip(host):
        res.checks["not_raw_ip"] = False
        res.violations.append("直接使用 IP 地址，无法核验主办方")
    else:
        res.checks["not_raw_ip"] = True

    official = host in TRUSTED_EXACT or host.endswith(TRUSTED_SUFFIXES)
    industry = host in INDUSTRY_CONFIRMED or any(
        host == d or host.endswith("." + d) for d in INDUSTRY_CONFIRMED
    )
    res.trusted = official or industry
    res.tier = "official" if official else ("industry" if industry else "unknown")

    # --- L2 同形字检测 ---
    mixed = has_mixed_script(host)
    res.checks["no_mixed_script"] = not mixed
    if mixed or normalize_confusables(host) != host:
        res.trusted = False
        res.tier = "suspicious"
        res.violations.append(
            f"域名含非常规字符（同形字仿冒风险）: {host} → {normalize_confusables(host)}"
        )

    # --- L3 编辑距离（与白名单域名的近似域名）---
    if not res.trusted and not mixed:
        for ref in TRUSTED_EXACT:
            if 0 < levenshtein(host, ref) <= 2:
                res.tier = "suspicious"
                res.violations.append(f"与可信域名 {ref} 仅差 {levenshtein(host, ref)} 个字符")
                break

    # --- L4 协议 ---
    res.checks["https"] = parsed.scheme == "https"
    if not res.checks["https"]:
        res.violations.append("非 HTTPS")

    # --- 反爬拦截标记（可换入口，不算造假）---
    if host in KNOWN_BLOCKED:
        res.blocked = True

    return res


def check_redirect_chain(final_url: str, hop_urls: list[str]) -> list[str]:
    """校验跳转链：任何一跳落到可疑域名都要报出来。"""
    problems: list[str] = []
    for hop in hop_urls:
        r = check_url(hop)
        if r.tier == "suspicious":
            problems.append(f"跳转链出现可疑域名: {hop} ({'; '.join(r.violations)})")
    if hop_urls:
        last = check_url(hop_urls[-1])
        if not last.trusted and last.tier == "unknown":
            problems.append(f"最终落地域名不在白名单: {last.host}")
    return problems


def assign_base_credibility(result: AuthenticityResult) -> int:
    """按真实性结果给出可信度基线（与 03 篇金字塔对应）。"""
    if result.tier == "official":
        return 100
    if result.tier == "industry":
        return 85
    if result.tier == "suspicious":
        return 0          # 可疑源直接不给分，连进池资格都没有
    return 60             # 未确认域名，进人工队列


if __name__ == "__main__":
    for demo in (
        "https://www.federalregister.gov/api/v1/documents.json",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/",
        "https://www.g\u043ev.cn/notice",       # 同形字（西里尔 о）
        "https://www.federalreg1ster.gov/doc",  # 编辑距离近似
        "http://203.0.113.9/battery",
    ):
        print(check_url(demo))
