# -*- coding: utf-8 -*-
"""Source Access Model（Phase 4B-1 Step 1）—— 纯逻辑，无网络。

三块内容（用户口径 2026-09-12）：
    1) failure taxonomy：SOURCE_FAILURE 与 NO_RESULTS 严格分离
       · HTTP 403/500 ≠ paywalled_known（付费墙必须有明确付费机制证据）
       · NO_RESULTS = 请求成功 + 解析成功 + 查询确实 0 条（**不是**失败）
    2) Standards 访问模型五概念分离：
       metadata_available / fulltext_available / open_access_status
       / metadata_source_type / endpoint_status
    3) 角色状态推导：**单个 endpoint 不得决定 source role 状态**
       （一个入口坏了 ≠ 整个官方源不可用）

测试：tests/phase4b1/test_failure_taxonomy.py / test_source_role_status.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ============================================================ 1) Failure taxonomy

#: 真实失败类型（会阻断/降级端点）
SOURCE_FAILURES = (
    "HTTP_403", "HTTP_404", "HTTP_429", "HTTP_5XX", "HTTP_OTHER_4XX",
    "TIMEOUT", "DNS_FAILURE", "TLS_FAILURE", "CONNECTION_ERROR",
    "CAPTCHA", "API_KEY_REQUIRED", "AUTH_REQUIRED", "ROBOTS_RESTRICTED",
    "PAYWALL_CONFIRMED", "PARSER_FAILURE", "SCHEMA_DRIFT", "UNSUPPORTED_FORMAT",
)
#: 非失败标记
NON_FAILURES = ("NONE", "NO_RESULTS")
FAILURE_TYPES = SOURCE_FAILURES + NON_FAILURES


def is_source_failure(failure_type: str | None) -> bool:
    """NO_RESULTS / NONE 不是失败；其余一律视为 source failure。"""
    return bool(failure_type) and failure_type in SOURCE_FAILURES


def classify_http_status(status_code: int | None) -> str:
    if status_code is None:
        return "CONNECTION_ERROR"
    if status_code == 403:
        return "HTTP_403"
    if status_code == 404:
        return "HTTP_404"
    if status_code == 429:
        return "HTTP_429"
    if 400 <= status_code < 500:
        return "HTTP_OTHER_4XX"
    if status_code >= 500:
        return "HTTP_5XX"
    return "NONE"


# ---- 正文信号（仅用于区分同类失败的具体原因；不得推断付费墙） ----
# 4xx/5xx 响应可放宽匹配（错误页文本简单、误判风险低）
_CHALLENGE_MARKERS = (
    "captcha", "cf-challenge", "cloudflare", "are you a robot",
    "unusual traffic", "verify you are human", "challenge-platform",
)
# HTTP 200 页面必须用**更严**的挑战页标记：
# 普通页面里出现 recaptcha 脚本引用/cloudflare CDN 字样不能判挑战页
_CHALLENGE_STRICT = (
    "solve the captcha", "verify you are human", "checking your browser",
    "cf-challenge", "challenge-platform", "unusual traffic",
    "are you a robot", "enable javascript and cookies to continue",
    "attention required",
)
_APIKEY_MARKERS = (
    "api key", "api_key", "apikey", "missing key", "invalid key",
    "key is required", "requires an api key", "x-api-key",
)
_AUTH_MARKERS = (
    "sign in to continue", "log in to continue", "authentication required",
    "login required", "access denied for user",
)
_ROBOTS_MARKERS = ("robots.txt", "robots restriction", "not allowed by robots")

# ★ 付费墙必须有**强证据**（用户纪律：HTTP 403/500 ≠ paywalled_known）：
#   ① 明确的订阅/购买短语，或
#   ② 价格数字 + 窄购买语境（购物车/结算/订阅）同时出现
#   ⚠️ 实测教训（2026-09-12）：裸词 "price"/"eur"/"standard" 会把 EUR-Lex、
#      Basel、JRC 的免费官方页误判为付费墙（"EUR" 命中 "EUR-Lex"，
#      "standard" 命中法律正文）——已废弃。
_PAYWALL_STRONG = (
    "subscribe to read", "subscription required", "subscribers only",
    "full text is available to subscribers", "sign in to access the full text",
    "purchase this standard", "buy this standard", "buy the standard",
    "add to cart", "add to basket", "proceed to checkout",
)
_PAYWALL_PRICE_RE = re.compile(
    r"(?:[€$£]\s?\d{2,}|\b(?:usd|eur|gbp|chf|jpy)\s?\d{2,}\b)", re.I)
# 价格数字必须与**购物车/结算/立即购买**语境同时出现才判付费墙：
# 实测教训（2026-09-12）：BIS EAR 页含 "$250,000 罚款" + "Subscribe 新闻订阅"
# 被误判 PAYWALL → 已把 subscribe 从语境词中移除。
_PAYWALL_CTX = ("add to cart", "add to basket", "checkout", "buy now",
                "purchase now")


def classify_body_signals(body: str, *, status_code: int | None = None,
                          strict: bool = False) -> str | None:
    """正文标记 → 失败类型细化（可能返回 None = 无信号）。

    strict=True（HTTP 200 页面）：仅接受强挑战页/强付费墙证据。
    """
    text = (body or "").lower()
    if not text:
        return None
    challenge = _CHALLENGE_STRICT if strict else _CHALLENGE_MARKERS
    if any(m in text for m in challenge):
        return "CAPTCHA"
    if any(m in text for m in _APIKEY_MARKERS):
        return "API_KEY_REQUIRED"
    if any(m in text for m in _ROBOTS_MARKERS):
        return "ROBOTS_RESTRICTED"
    if any(m in text for m in _AUTH_MARKERS):
        return "AUTH_REQUIRED"
    # 付费墙：强短语，或（价格数字 + 窄购买语境）
    if any(m in text for m in _PAYWALL_STRONG):
        return "PAYWALL_CONFIRMED"
    if _PAYWALL_PRICE_RE.search(text) and any(m in text for m in _PAYWALL_CTX):
        return "PAYWALL_CONFIRMED"
    return None


def classify_exception(exc: BaseException | None) -> str:
    """网络异常 → 失败类型。"""
    if exc is None:
        return "NONE"
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "timeout" in name or "timeout" in msg or "timed out" in msg:
        return "TIMEOUT"
    if "ssl" in name or "certificate" in msg or "tls" in msg:
        return "TLS_FAILURE"
    if "gaierror" in msg or "name or service not known" in msg or \
            "getaddrinfo" in msg or "name resolution" in msg:
        return "DNS_FAILURE"
    return "CONNECTION_ERROR"


# ============================================================ 2) Standards 访问模型

OPEN_ACCESS_STATUSES = ("open_fulltext", "official_metadata_only",
                        "paywalled_known", "unavailable")
METADATA_SOURCE_TYPES = ("OFFICIAL_PUBLISHER", "EU_OFFICIAL_REFERENCE",
                         "JRC_REFERENCE", "OTHER_OFFICIAL_REFERENCE")


def resolve_open_access_status(*, fulltext_available: bool,
                               metadata_available: bool,
                               paywall_confirmed: bool) -> str:
    """四值映射（纪律：403/500 不得推断 paywalled）。

    · open_fulltext           全文可得（且可解析）
    · paywalled_known         有明确付费机制证据
    · official_metadata_only  有官方 metadata（含 EU 官方引用），无全文
    · unavailable             两者皆无
    """
    if fulltext_available:
        return "open_fulltext"
    if paywall_confirmed:
        return "paywalled_known"
    if metadata_available:
        return "official_metadata_only"
    return "unavailable"


# ============================================================ 3) Endpoint status

ENDPOINT_STATUSES = ("ACCESSIBLE", "PARTIAL", "BLOCKED", "UNVERIFIED")


@dataclass
class EndpointResult:
    """单端点探测结果（与 outputs/audit/source_probe_results.json 同构）。"""
    source_role: str
    endpoint_id: str
    official_url: str
    checked_at: str = ""
    http_status: int | None = None
    response_type: str = ""
    latency_ms: int | None = None
    reachable: bool = False
    metadata_available: bool = False
    fulltext_available: bool = False
    endpoint_status: str = "UNVERIFIED"
    failure_type: str = "NONE"
    failure_detail: str = ""
    capabilities: dict = field(default_factory=dict)
    metadata_source_type: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def evaluate_probe_response(
    *, source_role: str, endpoint_id: str, official_url: str,
    checked_at: str, status_code: int | None, content_type: str,
    body: str = "", latency_ms: int | None = None,
    exception: BaseException | None = None,
    capabilities: dict | None = None,
    content_kind: str = "html",
    parsers: tuple[str, ...] = ("html", "json", "xml"),
    expect_keys: list[str] | None = None,
    json_parsed: bool | None = None,
    payload_empty_for: str | None = None,
    metadata_source_type: str = "",
) -> EndpointResult:
    """把一次探测的原始素材判定为 EndpointResult（纯函数，测试可达）。

    json_parsed=None 时按 body 自行解析判断（由调用方传入 body 文本）。
    """
    caps = capabilities or {}
    res = EndpointResult(
        source_role=source_role, endpoint_id=endpoint_id,
        official_url=official_url, checked_at=checked_at,
        http_status=status_code, response_type=content_type or "",
        latency_ms=latency_ms, capabilities=dict(caps),
        metadata_source_type=metadata_source_type,
    )

    # --- 网络异常 ---
    if exception is not None:
        res.failure_type = classify_exception(exception)
        res.failure_detail = f"{type(exception).__name__}: {str(exception)[:200]}"
        res.endpoint_status = "BLOCKED"
        return res

    # --- HTTP 层失败 ---
    ftype = classify_http_status(status_code)
    if ftype != "NONE":
        refined = classify_body_signals(body, status_code=status_code)
        res.failure_type = refined or ftype
        res.failure_detail = f"HTTP {status_code} {res.response_type}".strip()
        res.endpoint_status = "BLOCKED"
        return res

    res.reachable = True

    # --- HTTP 200 的正文信号（挑战页/付费墙可能以 200 返回）---
    # 只对 html/xml 扫描：JSON API 正文里的 "price" 等字段不得被判付费墙
    # strict=True：普通页面里的 recaptcha 脚本引用不得误判
    if content_kind in ("html", "xml"):
        sig = classify_body_signals(body, status_code=status_code, strict=True)
        if sig in ("CAPTCHA", "PAYWALL_CONFIRMED"):
            res.failure_type = sig
            res.failure_detail = f"HTTP 200 但正文信号命中：{sig}"
            res.endpoint_status = "BLOCKED"
            return res

    # --- 内容类型不可解析（如 PDF 无解析器）---
    if content_kind not in parsers:
        res.failure_type = "UNSUPPORTED_FORMAT"
        res.failure_detail = (f"content-kind={content_kind} 不在可解析集合 "
                              f"{list(parsers)}（可下载/可引用，但不生成条款证据）")
        res.endpoint_status = "PARTIAL"
        res.metadata_available = bool(caps.get("metadata"))
        res.fulltext_available = False
        return res

    # --- JSON 结构校验 ---
    if content_kind == "json":
        parsed = json_parsed
        if parsed is None:
            try:
                import json as _json
                _json.loads(body or "")
                parsed = True
            except Exception:  # noqa: BLE001
                parsed = False
        if not parsed:
            res.failure_type = "PARSER_FAILURE"
            res.failure_detail = "HTTP 200 但 JSON 解析失败"
            res.endpoint_status = "BLOCKED"
            return res
        if expect_keys:
            try:
                import json as _json
                payload = _json.loads(body or "{}")
            except Exception:  # noqa: BLE001
                payload = {}
            missing = [k for k in expect_keys
                       if not isinstance(payload, dict) or k not in payload]
            if missing:
                res.failure_type = "SCHEMA_DRIFT"
                res.failure_detail = f"缺少期望键：{missing}"
                res.endpoint_status = "BLOCKED"
                return res
            if payload_empty_for and isinstance(payload.get(payload_empty_for), list) \
                    and not payload[payload_empty_for]:
                res.failure_type = "NO_RESULTS"
                res.failure_detail = (f"请求成功+解析成功，{payload_empty_for}=0 条"
                                      f"（NO_RESULTS ≠ 失败）")
                res.endpoint_status = "ACCESSIBLE"
                res.metadata_available = bool(caps.get("metadata"))
                res.fulltext_available = bool(caps.get("fulltext"))
                return res

    # --- 正常可达 ---
    res.failure_type = "NONE"
    res.endpoint_status = "ACCESSIBLE"
    res.metadata_available = bool(caps.get("metadata"))
    res.fulltext_available = bool(caps.get("fulltext"))
    return res


# ============================================================ 4) 角色状态推导

#: 状态强弱序（仅用于 status_ceiling 封顶；BLOCKED 单独处理）
_STATUS_ORDER = ["NOT_ONBOARDED", "DISCOVERED", "ACCESSIBLE", "PARTIAL",
                 "CONNECTED", "COMPLETE"]
_WEAK_DECLARED = ("NOT_ONBOARDED", "DISCOVERED", "ACCESSIBLE", "BLOCKED")


@dataclass
class RoleStatus:
    status: str
    reachable: str               # yes | no | UNVERIFIED
    block_reason: str = ""
    blocked_endpoints: list[str] = field(default_factory=list)
    usable_endpoints: list[str] = field(default_factory=list)
    enumeration_available: bool = False
    metadata_available: bool = False
    fulltext_available: bool = False
    last_checked: str = ""


def derive_role_status(
    *, declared_status: str, sources_configured: bool, has_collector: bool,
    evidence_count: int, endpoint_results: list[dict] | None,
    status_ceiling: str = "", gap_reason: str = "",
) -> RoleStatus:
    """由 **全部端点** + 采集器 + 数据反推综合得出角色状态。

    规则（写死在文档与测试里）：
      · 无端点声明 → 沿用注册表 + 数据反推（Phase 4A 兼容行为）
      · 有端点：
          全部 BLOCKED                → BLOCKED
          有可用端点 + 有采集器 + 有数据 → CONNECTED（声明为 COMPLETE 且无 blocked → COMPLETE）
          有可用端点 + 有采集器 + 零数据 → PARTIAL
          有可用端点 + 无采集器         → ACCESSIBLE（若有 blocked 端点 → PARTIAL）
      · status_ceiling 封顶（如 STANDARDS 最高 PARTIAL：EU 官方引用 ≠ 标准库接入）
      · ★ 单端点失败不得把角色判死（blocked 端点只进 blocked_endpoints 清单）
    """
    eps = list(endpoint_results or [])
    usable = [e for e in eps
              if e.get("endpoint_status") in ("ACCESSIBLE", "PARTIAL")]
    blocked = [e for e in eps if e.get("endpoint_status") == "BLOCKED"]

    out = RoleStatus(status=declared_status, reachable="UNVERIFIED")
    out.blocked_endpoints = [e.get("endpoint_id", "") for e in blocked if e.get("endpoint_id")]
    out.usable_endpoints = [e.get("endpoint_id", "") for e in usable if e.get("endpoint_id")]
    if eps:
        out.last_checked = max((e.get("checked_at") or "") for e in eps) or ""
        out.reachable = "yes" if usable else ("no" if blocked else "UNVERIFIED")
        out.enumeration_available = any(
            e.get("capabilities", {}).get("enumeration") for e in usable)
        out.metadata_available = any(
            e.get("metadata_available") for e in usable)
        out.fulltext_available = any(
            e.get("fulltext_available") for e in usable)

    if not eps:
        # 无端点声明：兼容 Phase 4A 行为
        status = declared_status
        if evidence_count > 0 and status in _WEAK_DECLARED:
            status = "CONNECTED"
        if sources_configured and evidence_count == 0 and \
                status in ("CONNECTED", "COMPLETE"):
            status = "PARTIAL"
        out.status = status
    else:
        if not usable and blocked:
            # ★ 直连端点全被阻：若有替代采集通道且有真实数据 → 不判死
            #   例：CalRecycle/ECHA 直连 403(CAPTCHA)，但浏览器通道已采集入库
            if has_collector and evidence_count > 0:
                out.status = "CONNECTED"
                reasons = "；".join(
                    f"{e.get('endpoint_id')}={e.get('failure_type')}"
                    for e in blocked)
                out.block_reason = (
                    f"直连端点全部被阻（{reasons}）；经替代采集通道入库"
                    f"（evidence={evidence_count}）")
            else:
                out.status = "BLOCKED"
                reasons = [f"{e.get('endpoint_id')}={e.get('failure_type')}"
                           for e in blocked]
                out.block_reason = "；".join(reasons)
        elif usable:
            if has_collector and evidence_count > 0:
                out.status = ("COMPLETE"
                              if (declared_status == "COMPLETE" and not blocked)
                              else "CONNECTED")
            elif has_collector:
                out.status = "PARTIAL"
            else:
                out.status = "PARTIAL" if blocked else "ACCESSIBLE"
        else:
            out.status = declared_status      # 未探测（无结果文件）→ 保持声明值

    # status_ceiling 封顶
    if status_ceiling and out.status in _STATUS_ORDER and \
            status_ceiling in _STATUS_ORDER:
        if _STATUS_ORDER.index(out.status) > _STATUS_ORDER.index(status_ceiling):
            out.status = status_ceiling

    if not out.block_reason:
        out.block_reason = gap_reason if out.status in ("BLOCKED", "NOT_ONBOARDED",
                                                        "PARTIAL") else ""
    # 失败端点单独标注（角色仍可用时也要可见）
    if out.blocked_endpoints and out.status not in ("BLOCKED",):
        suffix = "；".join(
            f"{e.get('endpoint_id')}={e.get('failure_type')}"
            for e in blocked if e.get("failure_type"))
        if suffix:
            out.block_reason = (out.block_reason + " ｜ blocked_endpoints: " + suffix) \
                if out.block_reason else ("blocked_endpoints: " + suffix)
    return out


def has_usable_endpoint(endpoint_results: list[dict] | None) -> bool:
    return any(e.get("endpoint_status") in ("ACCESSIBLE", "PARTIAL")
               for e in (endpoint_results or []))


# ============================================================ 5) 源别名展开

def expand_source_patterns(patterns: list[str],
                           known_source_ids: list[str] | set[str]) -> list[str]:
    """把“逻辑源 patterns”展开为库内真实 source_id 列表（支持末尾 `*`）。"""
    known = list(known_source_ids)
    out: list[str] = []
    for p in patterns or []:
        if not p:
            continue
        if p.endswith("*"):
            prefix = p[:-1]
            out += [s for s in known if s.startswith(prefix)]
        elif p in known or not known:
            out.append(p)
    # 去重保序
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def expand_role_sources(role_sources: list[str],
                        alias_map: dict,
                        known_source_ids: list[str] | set[str]) -> list[str]:
    """角色 sources（含逻辑名）→ 完整真实 source_id 列表。

    alias_map: {logical_name: {"patterns": [...], ...}} 或 {logical_name: AliasEntry}
    未登记别名的直接原样保留（不猜）。
    """
    known = list(known_source_ids)
    out: list[str] = []
    for sid in role_sources or []:
        entry = alias_map.get(sid)
        if entry is None:
            out.append(sid)
            continue
        patterns = entry["patterns"] if isinstance(entry, dict) else entry.patterns
        out += expand_source_patterns(list(patterns), known)
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


_WS = re.compile(r"\s+")


def normalize_reason(text: str) -> str:
    return _WS.sub(" ", (text or "").strip())
