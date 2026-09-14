# -*- coding: utf-8 -*-
"""Network Vantage & Access Classification（Phase 4B-2B Batch 1R §A1/A3）。

**运行/审计层 overlay**（不修改冻结的 Policy Core Schema）：
区分「源不可用」与「当前 runner 不可用」——当前 runner 的访问失败
**不得**自动等价为 SOURCE_MISSING / NO_RESULTS。

访问状态枚举（规格 §A3）：
    SOURCE_AVAILABLE      当前 runner（或第二 vantage）真实可达（200+内容）
    CURRENT_RUNNER_BLOCKED 本 vantage 被拒但存在可达的替代 vantage/官方路由
    SOURCE_PARTIAL        部分可达（重定向壳/短内容/部分 role）
    ACCESS_CONTROLLED     服务器主动控制（401/403/429/challenge 503）
    MULTI_VANTAGE_BLOCKED 独立出口 ≥2 且全部失败（本机同出口场景不下此结论）
    SOURCE_FAILURE        DNS 层确认不存在（NXDOMAIN，含 DoH 复核）
    UNKNOWN               无法分层归因

判定纪律：
    · 独立性：同出口的浏览器回退 **不算独立 vantage**（independent_egress 须显式标注）；
    · 只有 independent_vantages >= 2 且全部失败才允许 MULTI_VANTAGE_BLOCKED；
    · 连接层失败（timeout/reset/refused）在独立环境未复核前，一律
      CURRENT_RUNNER_BLOCKED（awaiting_independent_runner=true），不得上升。
"""
from __future__ import annotations

ACCESS_STATUSES = (
    "SOURCE_AVAILABLE",
    "CURRENT_RUNNER_BLOCKED",
    "SOURCE_PARTIAL",
    "ACCESS_CONTROLLED",
    "MULTI_VANTAGE_BLOCKED",
    "SOURCE_FAILURE",
    "UNKNOWN",
)

FAILURE_REASONS = (
    "NONE",
    "HTTP_200_OK",
    "HTTP_3XX_REDIRECT_SHELL",
    "HTTP_401_AUTH",
    "HTTP_403_FORBIDDEN",
    "HTTP_429_RATE_LIMIT",
    "HTTP_5XX_CHALLENGE",
    "HTTP_5XX_ERROR",
    "DNS_NXDOMAIN",
    "DNS_ERROR",
    "TCP_TIMEOUT",
    "TCP_RESET",
    "TCP_REFUSED",
    "TCP_ERROR",
    "TLS_ERROR",
    "CONNECT_TIMEOUT",
    "CONNECTION_RESET",
    "JS_RENDERED_NO_STATIC_CONTENT",
    "EMPTY_CONTENT",
    "UNCLASSIFIED",
)


def classify_access(
    *,
    dns_status: str = "unknown",          # ok | nxdomain | error
    doh_confirms: str = "",               # 第二解析器复核（如 dns.google 结果）
    tcp_status: str = "unknown",          # ok | timeout | reset | refused | error
    tls_status: str = "unknown",          # ok | error | skipped
    http_status: int | None = None,
    content_len: int = 0,
    alt_vantage_ok: bool = False,         # 浏览器 vantage 可达
    official_alt_used: bool = False,      # 官方替代端点（API/mirror）可达
    js_rendered: bool = False,            # 返回 200 但无静态文书内容
    independent_vantages_failed: int = 0,  # 独立出口失败计数（同出口不计）
    independent_vantages_checked: int = 1,
) -> dict:
    """分层观测 → (access_status, failure_reason, awaiting_independent_runner)。

    优先级：替代 vantage 成功（证明源可用、runner 被拒）> 200 判定 >
    HTTP 控制类 > DNS > 连接层 > 其他。
    """
    def _out(status: str, reason: str, awaiting: bool = False) -> dict:
        return {
            "access_status": status,
            "failure_reason": reason,
            "awaiting_independent_runner": awaiting,
            "source_vs_runner": (
                "SOURCE" if status in ("SOURCE_AVAILABLE", "SOURCE_PARTIAL",
                                       "SOURCE_FAILURE", "ACCESS_CONTROLLED")
                else "RUNNER" if status in ("CURRENT_RUNNER_BLOCKED",
                                            "MULTI_VANTAGE_BLOCKED")
                else "UNKNOWN"),
        }

    # 1) 第二 vantage / 官方替代路由成功 → 源可用、当前 runner 被拒
    if alt_vantage_ok or official_alt_used:
        return _out("CURRENT_RUNNER_BLOCKED",
                    "ALT_VANTAGE_OK" if alt_vantage_ok
                    else "OFFICIAL_ALT_ROUTE_OK", awaiting=True)
    # 2) 200 判定
    if http_status == 200:
        if js_rendered:
            return _out("SOURCE_PARTIAL", "JS_RENDERED_NO_STATIC_CONTENT")
        if content_len > 0:
            return _out("SOURCE_AVAILABLE", "HTTP_200_OK")
        return _out("SOURCE_PARTIAL", "EMPTY_CONTENT")
    # 3) HTTP 控制类
    if http_status == 401:
        return _out("ACCESS_CONTROLLED", "HTTP_401_AUTH")
    if http_status == 403:
        return _out("ACCESS_CONTROLLED", "HTTP_403_FORBIDDEN")
    if http_status == 429:
        return _out("ACCESS_CONTROLLED", "HTTP_429_RATE_LIMIT")
    if http_status is not None and 500 <= http_status < 600:
        return _out("ACCESS_CONTROLLED" if http_status == 503
                    else "SOURCE_PARTIAL", "HTTP_5XX_CHALLENGE")
    if http_status is not None and 300 <= http_status < 400:
        return _out("SOURCE_PARTIAL", "HTTP_3XX_REDIRECT_SHELL")
    # 4) DNS 层
    if dns_status == "nxdomain":
        if doh_confirms == "nxdomain":
            return _out("SOURCE_FAILURE", "DNS_NXDOMAIN")
        return _out("UNKNOWN", "DNS_ERROR")
    if dns_status == "error":
        return _out("UNKNOWN", "DNS_ERROR")
    # 5) 连接层（独立出口未复核前不得上升为 SOURCE_FAILURE）
    if tcp_status == "ok" and tls_status == "ok" and http_status is None:
        # TCP/TLS 建立成功但 HTTP 层无响应：runner 侧或中途设备中断
        return _out("CURRENT_RUNNER_BLOCKED", "HTTP_NO_RESPONSE",
                    awaiting=True)
    if tcp_status in ("timeout", "reset", "refused", "error") \
            or tls_status == "error":
        reason = {"timeout": "CONNECT_TIMEOUT", "reset": "CONNECTION_RESET",
                  "refused": "TCP_REFUSED", "error": "TCP_ERROR"}.get(
                      tcp_status, "TLS_ERROR")
        if tls_status == "error" and tcp_status == "ok":
            reason = "TLS_ERROR"
        if independent_vantages_checked >= 2 and \
                independent_vantages_failed >= independent_vantages_checked:
            return _out("MULTI_VANTAGE_BLOCKED", reason)
        return _out("CURRENT_RUNNER_BLOCKED", reason, awaiting=True)
    # 6) 其他
    if http_status is not None and content_len == 0:
        return _out("SOURCE_PARTIAL", "EMPTY_CONTENT")
    return _out("UNKNOWN", "UNCLASSIFIED")
