# -*- coding: utf-8 -*-
"""Domain Scope Guard（Phase 4B-2B0 Step 4）—— 域相关性五级分类与约束。

背景（2B0 审计 Q5/P1-A4）：
    NIM 默认 A2 通道把泛便携电池文书（paristoista ja akuista、portable
    battery 安排）升为体系强证据——EV traction 主线被污染。

五级域（正交字段，规格 §五）：
    CORE_EV_TRACTION            EV/动力电池/车用/黑粉（标题级对象）
    HORIZONTAL_APPLIES_TO_EV    电池法/ELV/WSR/WFD/CRM 等横向体系法案
    SUPPORTING_REGULATION       回收效率/再生含量/运输/标准等方法学
    GENERAL_BATTERY_BACKGROUND  便携/消费/纽扣/家用电池（**不得** A1/A2/B）
    OUT_OF_SCOPE                域外对象（仅 D）

约束（guard_class）：
    GENERAL + A1/A2/B → 降 C ｜ OUT_OF_SCOPE + 非 D → 降 D
    SUPPORTING + A1/A2 → 降 B ｜ CORE/HORIZONTAL 无约束

规则文件：sources/domain-scope-rules.yaml（词表；代码只做判定）
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = ROOT / "sources" / "domain-scope-rules.yaml"

SCOPES = ("CORE_EV_TRACTION", "HORIZONTAL_APPLIES_TO_EV",
          "SUPPORTING_REGULATION", "GENERAL_BATTERY_BACKGROUND",
          "OUT_OF_SCOPE")

#: 非政策域通道（企业情报线）——域护栏_**不适用**_
#: cninfo=中国企业公告 · eia=美国能源署数据 · eol_=行业网企业线
NON_POLICY_PREFIXES = ("cninfo", "eia", "eol_")


def is_policy_domain_source(source_id: str) -> bool:
    """政策域通道判定（域护栏仅作用于政策记录）。"""
    return not str(source_id or "").startswith(NON_POLICY_PREFIXES)


class DomainRulesError(Exception):
    pass


@lru_cache(maxsize=1)
def _rules() -> dict:
    raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise DomainRulesError(f"域规则文件非法：{RULES_PATH}")
    out = {}
    for key in ("core_ev_traction", "horizontal_applies_to_ev",
                "supporting_markers", "supporting_unconditional",
                "general_battery_markers", "out_of_scope_markers"):
        pats = raw.get(key)
        if key == "supporting_unconditional":
            out[key] = [re.compile(p, re.I) for p in (pats or [])]
            continue
        if not isinstance(pats, list) or not pats:
            raise DomainRulesError(f"域规则缺少非空列表：{key}")
        out[key] = [re.compile(p, re.I) for p in pats]
    return out


def classify_domain_scope(record: dict) -> str:
    """记录 → 域五级（标题优先；标题无信号时看正文前 2000 字符）。"""
    rules = _rules()
    title = record.get("title") or ""
    text_head = (record.get("text") or "")[:2000]
    hay = title + "\n" + text_head

    def _hit(key: str, s: str) -> bool:
        return any(rx.search(s) for rx in rules[key])

    # 核心 CELEX 锚点（2B1）：eeu_fulltext_* 记录标题为占位样式，全文含
    # 核心体系法案（2000/53、2008/98、2023/1542…）→ 直接归位 HORIZONTAL
    celex = str((record.get("meta") or {}).get("celex") or "")
    if celex.startswith(("32000L0053", "32006L0066", "32008L0098",
                         "32023R1542", "32024R1157", "32024R1252",
                         "32018L0849", "32026R1738")):
        return "HORIZONTAL_APPLIES_TO_EV"

    # 域外对象（标题级）且无横向电池法引用 → OUT_OF_SCOPE
    if _hit("out_of_scope_markers", title) \
            and not _hit("horizontal_applies_to_ev", hay):
        return "OUT_OF_SCOPE"
    # 核心对象（标题级——"明确针对"与 A1 同口径）
    if _hit("core_ev_traction", title):
        return "CORE_EV_TRACTION"
    # 横向体系法案
    if _hit("horizontal_applies_to_ev", title) or _hit(
            "horizontal_applies_to_ev", hay[:1200]):
        return "HORIZONTAL_APPLIES_TO_EV"
    # 泛电池背景（标题级）
    if _hit("general_battery_markers", title):
        # 标题含电池但泛——若正文头部有核心对象词，升 CORE
        if _hit("core_ev_traction", hay):
            return "CORE_EV_TRACTION"
        return "GENERAL_BATTERY_BACKGROUND"
    # 支撑体系（无条件档；2B1）：危废/危货/激励——不要求电池字面词
    if _hit("supporting_unconditional", title) \
            or _hit("supporting_unconditional", hay[:400]):
        return "SUPPORTING_REGULATION"
    # 支撑性方法学（含电池对象语境）
    if _hit("supporting_markers", title) or _hit("supporting_markers",
                                                 hay[:600]):
        from app.policy.acceptance import _BATTERY_OBJ  # noqa: PLC0415
        if _BATTERY_OBJ.search(hay[:600]):
            return "SUPPORTING_REGULATION"
    # 正文出现核心对象 → CORE（发现层常见：标题编号、正文有对象）
    if _hit("core_ev_traction", hay):
        return "CORE_EV_TRACTION"
    # 有电池对象词 → 泛背景兜底
    from app.policy.acceptance import _BATTERY_OBJ  # noqa: PLC0415
    if _BATTERY_OBJ.search(hay):
        return "GENERAL_BATTERY_BACKGROUND"
    return "OUT_OF_SCOPE"


FORBIDDEN_BY_SCOPE: dict[str, frozenset] = {
    "OUT_OF_SCOPE": frozenset(("A1", "A2", "B")),
    "GENERAL_BATTERY_BACKGROUND": frozenset(("A1", "A2", "B")),
    "SUPPORTING_REGULATION": frozenset(("A1", "A2")),
}


def is_domain_acceptance_consistent(scope: str, final_class: str) -> bool:
    """域/acceptance 语义一致性（Phase 4B-2B1 §2；contradiction 目标 0）。

    final_class 应为**护栏后**的最终类；矛盾定义：
      OUT_OF_SCOPE / GENERAL + A1/A2/B；SUPPORTING + A1/A2。
    """
    return final_class not in FORBIDDEN_BY_SCOPE.get(scope, frozenset())


def guard_class(acceptance_class: str, domain_scope: str, *, is_nim: bool = False) -> str:
    """域约束下的最终类（2B1 口径；语义一致性纪律）。

    约束矩阵：
      · OUT_OF_SCOPE + 任意强类（A1/A2/B）→ **D**（2B1：不得再允许 OOS+B 终态；
        真支撑法规由词表归位到 SUPPORTING——hazmat/RCRA/VHU 等）；
      · GENERAL_BATTERY_BACKGROUND + A1/A2/B → C（便携/消费不得冒充 EV）；
      · SUPPORTING_REGULATION + A1/A2 → B；
      · CORE/HORIZONTAL 无约束。
    例外：NIM discovery 层（is_nim=True）封顶 C，不受 OUT_OF_SCOPE 降级影响
    （多语言域判定不可靠；且 NIM 本就不充当 corpus 强证据）。
    """
    if is_nim:
        return acceptance_class if acceptance_class in ("C", "D") else "C"
    if domain_scope == "OUT_OF_SCOPE":
        return "D" if acceptance_class in ("A1", "A2", "B") else acceptance_class
    if domain_scope == "GENERAL_BATTERY_BACKGROUND":
        return "C" if acceptance_class in ("A1", "A2", "B") else acceptance_class
    if domain_scope == "SUPPORTING_REGULATION":
        return "B" if acceptance_class in ("A1", "A2") else acceptance_class
    return acceptance_class


def guarded_effective_class(record: dict, acceptance_class: str) -> str:
    """对已得分类应用域护栏（供 effective_class 接入）。

    作用域细则（2B1 修订）：
      · 仅政策域通道；企业线（cninfo/eia/eol）原样返回；
      · NIM（discovery layer）封顶 C（see guard_class is_nim）——
        **不再豁免**域护栏逻辑分支；域判定结果仅作诊断报告。
    """
    sid = str(record.get("source_id") or "")
    if not is_policy_domain_source(sid):
        return acceptance_class
    scope = classify_domain_scope(record)
    return guard_class(acceptance_class, scope,
                       is_nim=sid.startswith("eu_nim_"))


def audit_domain_guard(records: list[dict]) -> dict:
    """全量域审计：分布 + 违规（被护栏改写的）清单。"""
    from app.policy.acceptance import classify_record
    from app.policy.jurisdiction_map import jurisdiction_of

    dist: dict[str, int] = {s: 0 for s in SCOPES}
    dist["non_policy_excluded"] = 0
    violations: list[dict] = []
    for r in records:
        if not is_policy_domain_source(str(r.get("source_id") or "")):
            dist["non_policy_excluded"] += 1
            continue
        try:
            scope = classify_domain_scope(r)
        except Exception:  # noqa: BLE001
            continue
        dist[scope] = dist.get(scope, 0) + 1
        try:
            cls = classify_record(r).classification
        except Exception:  # noqa: BLE001
            continue
        guarded = guarded_effective_class(r, cls)
        if guarded != cls:
            violations.append({
                "evidence_id": r.get("evidence_id"),
                "jurisdiction": jurisdiction_of(r),
                "source_id": r.get("source_id"),
                "class_before": cls, "class_after": guarded,
                "domain_scope": scope,
                "title": (r.get("title") or "")[:80],
            })
    return {"distribution": dist,
            "violations_count": len(violations),
            "violations": violations[:60]}
