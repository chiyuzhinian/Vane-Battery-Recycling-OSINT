# -*- coding: utf-8 -*-
"""Policy Acceptance Classification —— A1 / A2 / B / C / D（Phase 4A §3）。

设计纪律：
  · 不推翻现有三层判定器；**串联**——现有已拒 → D（拒绝优先）
  · B 类必须「具体条款证据存在」（evidence_quotes 非空），不能只凭主题关联
  · AI 可辅助，但不得作为唯一 gate —— 本模块为**规则可审计**的确定性分类；
    AI 辅助是可选增强（预留 hook，不内置 LLM 调用）
  · 主题判据来自 regulatory-topics.yaml；分类门槛来自 policy-acceptance-rules.yaml

判定顺序（与 YAML decision_order 一致）：
  0 现有判据已拒 → D ｜ 1 信息页 → D ｜ 2 信息型文书 → D ｜ 3 对象边界 → D
  4 A1 ｜ 5 A2 ｜ 6 B ｜ 7 C ｜ 8 D
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.relevance import V2_IN_SCOPE, V2_OFF_SCOPE
from app.policy.config import compiled_topics, load_acceptance
from app.policy.instruments import detect_instrument

# ---- 对象边界（复用 relevance.py 的既有口径；不重复造词表）----
_V2_IN_RE = [re.compile(p, re.I) for p in V2_IN_SCOPE]
_V2_OFF_RE = [re.compile(p, re.I) for p in V2_OFF_SCOPE]

# A1 专属对象：车用动力电池 / 黑粉（规格 §3：A1 要"明确针对"，对象须在标题；
# ELV 拆除属 B 域示例，经体系锚点归 A2，不得冒充 A1）
_A1_OBJECT = [
    re.compile(p, re.I) for p in (
        r"traction batter", r"vehicle batter", r"automotive batter",
        r"electric\s+vehicle\s+batter", r"\bev\s+batter", r"motive batter",
        r"动力电池", r"车用.{0,6}电池",
        r"black\s+mass", r"masse\s+noire", r"schwarzmasse",
        r"zwarte\s+massa", r"masa\s+negra", r"黑粉",
    )
]

# 体系锚点：电池法/ELV/WSR 法规号（家族成员识别）
_SYSTEM_NUM = re.compile(
    r"\b2023/1542\b|\b2006/66\b|\b2000/53\b|\b2024/1157\b|\b2008/98\b|"
    r"\b2018/849\b|\b2026/1738\b|\b2024/1252\b",
    re.I,
)

# 核心法案 CELEX 前缀（占位标题记录也能认体系成员——数据质量兼容）
_CORE_CELEX = (
    "32023R1542", "32006L0066", "32000L0053", "32024R1157", "32008L0098",
    "32018L0849", "32026R1738", "32024R1252",
)

# 电池对象词（标题/身份区）——A2 的"对象存在"门槛（多语言词根）
_BATTERY_OBJ = re.compile(
    r"waste\s+batter|batter(?:y|ies)|bateri|batteri|akkumul|akumul|accumul|accumulator|废电池|废锂",
    re.I)

# 综合立法包（omnibus）：标题≥4 部 (EU) 法规号 → 非电池专主题
_EU_NUM_RE = re.compile(r"\(EU\)\s*(?:No\s*)?\d{4}/\d+", re.I)
_BARE_EU_NUM_RE = re.compile(r"\d{4}/\d+")
_STRONG_OBJ = re.compile(
    r"waste\s+batter|black\s+mass|batter(?:y|ies)\s+and\s+accumulator|"
    r"end-?of-?life\s+vehicle|shipments?\s+of\s+waste|waste\s+shipment|"
    r"transboundary",
    re.I)

# 背景路由（无主题也归 C 而非 D）：来自 acceptance YAML 的 background_routes
from app.policy.config import load_acceptance as _load_acc
_BG_ROUTES = [re.compile(p, re.I) for p in _load_acc().background_routes]

_REJECTED_BY_PREFIX = (
    "browser_noise", "browser_sibling", "browser_nav", "procedural",
    "off_scope", "browser_no_identity_anchor", "project_reject",
)

_SENT_SPLIT = re.compile(r"(?<=[.;。；])\s+")


@dataclass
class PolicyAcceptanceResult:
    classification: str                 # A1 | A2 | B | C | D
    relevant: bool
    confidence: float
    topic_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    evidence_quotes: list[str] = field(default_factory=list)
    requires_human_review: bool = False

    def to_dict(self) -> dict:
        return {
            "acceptance_class": self.classification,
            "acceptance_relevant": self.relevant,
            "acceptance_confidence": round(self.confidence, 3),
            "topic_ids": self.topic_ids,
            "acceptance_reasons": self.reason_codes,
            "evidence_quotes": self.evidence_quotes,
            "acceptance_review": self.requires_human_review,
        }


def scan_topics(text: str) -> tuple[list[str], list[str]]:
    """返回 (topic_ids, evidence_quotes)。quote = 命中 topic 模式的句子。"""
    comp = compiled_topics()
    topic_ids: list[str] = []
    quotes: list[str] = []
    sentences = _SENT_SPLIT.split(text or "")
    for tid, (includes, excludes) in comp.items():
        if any(rx.search(text or "") for rx in excludes):
            continue
        hit = False
        for rx in includes:
            m = rx.search(text or "")
            if not m:
                continue
            hit = True
            # 取所在句子作为条款证据（≤200 字）
            for s in sentences:
                if rx.search(s):
                    q = s.strip()[:200]
                    if q and q not in quotes:
                        quotes.append(q)
                    break
            break
        if hit:
            topic_ids.append(tid)
    return topic_ids, quotes[:5]


def classify_record(record: dict) -> PolicyAcceptanceResult:
    """单条记录 → 验收分类。record 为 outputs/*.jsonl 的一行（dict）。"""
    rules = load_acceptance()
    title = record.get("title") or ""
    text = record.get("text") or ""
    meta = record.get("meta") or {}
    identity = (title + "\n" + text[:900])
    hay = title + "\n" + text[:1600]

    # ---- 0) 现有判据已拒 → D（拒绝优先）----
    rb = str(record.get("rejected_by") or "")
    if rb:
        code = ("DEMOTED_INFO_PAGE" if rb.startswith("info_page")
                else "DEMOTED_OUT_OF_SCOPE_OBJECT" if rb.startswith("off_scope")
                else "DEMOTED_PROCEDURAL" if rb.startswith("procedural")
                else "DEMOTED_PROCEDURAL")
        return PolicyAcceptanceResult("D", False, 0.9, [], [code], [])
    if not record.get("relevant"):
        # ⚠️ 语义修正（Step 3，2026-09-12）：
        #   旧行为把「字段缺失」与「被判不相关」一律当 D，
        #   导致新采集器（eCFR 等不会预置 relevant 的记录）直接早退。
        #   现在：仅**显式 False**（旧判定器真的拒了）才早退；
        #   字段缺失 → 交给内容分类（主题/对象/证据）自行判定。
        if "relevant" in record:
            return PolicyAcceptanceResult("D", False, 0.7, [], ["NO_THEME"], [])

    # ---- 1/2) 文书类型闸门 ----
    inst = detect_instrument(title, text)
    if inst.instrument_type in ("information_page", "news"):
        return PolicyAcceptanceResult("D", False, 0.85, [],
                                      ["DEMOTED_INFO_PAGE"],
                                      [f"instrument:{inst.instrument_type}"])
    if inst.instrument_type == "consultation" and not record.get("needs_human_review"):
        # 征求意见类：保留但标待人工（不直接升 A/B）
        pass

    # ---- 3) 对象边界（消费/铅酸且无电池法引用 → D）----
    off = next((rx.search(title) for rx in _V2_OFF_RE if rx.search(title)), None)
    regref = re.search(r"2023/1542|batter(?:y|ies)\s+regulation", title, re.I)
    if off and not regref:
        return PolicyAcceptanceResult("D", False, 0.85, [],
                                      ["DEMOTED_OUT_OF_SCOPE_OBJECT"],
                                      [off.group(0)[:40]])

    # ---- 主题扫描 ----
    topic_ids, quotes = scan_topics(hay)
    theme_hit = bool(topic_ids)

    # ---- 对象锚点 ----
    a1_obj = next((rx.search(identity) for rx in _A1_OBJECT
                   if rx.search(identity)), None)
    in_scope = any(rx.search(identity) for rx in _V2_IN_RE)
    battery_obj = bool(_BATTERY_OBJ.search(identity))
    core_celex = any(str(meta.get("celex") or "").startswith(c)
                     for c in _CORE_CELEX)

    # ---- 泛框架守护：标题≥3 个法规号且无强对象词 → C（非业务主库）----
    #   实测判例：
    #   · 中小企业简化包（≥4 个 (EU) 号）→ C（omnibus）
    #   · ESPR 全标题 = "...amending ... (EU) 2023/1542 and repealing 2009/125"
    #     → 4 个法规号 → C（泛产品母法，用户🟡，不得冒充 A2）
    #   反例守护：2018/849（4 个号但含 "batteries and accumulators" 强对象）、
    #             2026/1738（3 个号但含 "end-of-life vehicles"）→ 不受影响
    num_hits = len(set(re.findall(r"\b\d{4}/\d{2,4}\b", title)))
    if num_hits >= 3 and not _STRONG_OBJ.search(title):
        return PolicyAcceptanceResult("C", False, 0.6, topic_ids,
                                      ["C_OMNIBUS_PACKAGE"], quotes[:2])

    # ---- 体系锚点（A2）----
    celex = str(meta.get("celex") or "")
    system_anchor = bool(
        _SYSTEM_NUM.search(title)
        or (celex and _SYSTEM_NUM.search(celex))
        or core_celex
        or str(record.get("source_id") or "").startswith("eu_nim_")
        or meta.get("directive")
    )

    # ---- 4) A1（对象必须在标题中——"明确针对"）----
    a1_title = next((rx.search(title) for rx in _A1_OBJECT
                     if rx.search(title)), None)
    if a1_title and (theme_hit or battery_obj):
        return PolicyAcceptanceResult(
            "A1", True, 0.9, topic_ids, ["A1_EV_OR_BLACKMASS"], quotes[:3],
        )

    # ---- 5) A2：体系成员且（主题命中 ∨ 电池对象 ∨ 核心CELEX ∨ 家族工具）----
    #   家族工具（supplementing/implementing/amending/corrigendum X）即体系义务载体
    family_instrument = bool(re.search(
        r"supplementing|implementing|laying\s+down\s+rules\s+for\s+the\s+application"
        r"|amending|corrigendum", title, re.I))
    if system_anchor and (theme_hit or battery_obj or core_celex
                          or family_instrument):
        return PolicyAcceptanceResult(
            "A2", True, 0.8 if theme_hit else 0.72, topic_ids,
            ["A2_BATTERY_SYSTEM"], quotes[:3],
        )

    # ---- 5b) NIM 层特例：采集器已按多语言分层判相关 → 认可为体系成员 ----
    #   （与 rejudge 跳过 NIM 同一纪律：该层由采集器的 24 语种词表自治）
    sid = str(record.get("source_id") or "")
    if sid.startswith("eu_nim_") and record.get("relevant"):
        if record.get("needs_human_review"):
            return PolicyAcceptanceResult("C", False, 0.5, topic_ids,
                                          ["C_THEME_ONLY"], quotes[:2])
        return PolicyAcceptanceResult("A2", True, 0.7, topic_ids,
                                      ["A2_BATTERY_SYSTEM"], quotes[:2])

    # ---- 6) B（条款证据必需）----
    b_topics = set(rules.classes["B"].required_any_topics)
    if theme_hit and set(topic_ids) & b_topics and quotes:
        conf = min(0.85, 0.65 + 0.05 * min(len(quotes), 4))
        # 标题无任何电池/对象词 + 仅 1 条证据 → 低置信转人工
        weak = (not battery_obj and not in_scope and len(quotes) < 2)
        return PolicyAcceptanceResult(
            "B", True, conf if not weak else min(conf, 0.68),
            topic_ids, ["B_CLAUSE_EVIDENCE"], quotes[:3],
            requires_human_review=weak,
        )

    # ---- 7) C：仅主题关联 ----
    if theme_hit:
        return PolicyAcceptanceResult("C", False, 0.5, topic_ids,
                                      ["C_THEME_ONLY"], quotes[:2])

    # ---- 8) C 背景路由（无主题但属背景类）→ 否则 D ----
    bg_hit = next((rx.search(title) for rx in _BG_ROUTES if rx.search(title)), None)
    if bg_hit:
        return PolicyAcceptanceResult("C", False, 0.5, topic_ids,
                                      ["C_THEME_ONLY"], quotes[:2])
    if record.get("needs_human_review"):
        return PolicyAcceptanceResult("C", False, 0.5, topic_ids,
                                      ["C_REVIEW_PENDING"], quotes[:2])
    return PolicyAcceptanceResult("D", False, 0.6, [], ["NO_THEME"], [])


# ------------------------------------------------------------ AI 辅助 hook
def ai_assist_hook(record: dict) -> dict | None:
    """预留：AI 辅助分类（规格 §3：AI 可辅助但不得作为唯一 gate）。

    当前返回 None = 不参与。将来接入时，其结果只允许：
      · 把 requires_human_review 置 True（更保守）
      · 上调证据权重（附 quote）
    绝不允许单独把 D 提升为 A/B。
    """
    return None
