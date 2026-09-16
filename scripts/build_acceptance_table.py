# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1C —— Policy Acceptance Table 构建器（规格 §七–§十一）。

产出（全部在 outputs/，随 .gitignore 本地留存）：
  outputs/acceptance/batch1_policy_acceptance.csv / .json   （23 字段主表）
  outputs/acceptance/gates/batch1_jurisdiction_gates.json   （§十二 Gate）
  outputs/acceptance/{JID}/ × 9 验收包                      （§十一）
  outputs/reporting/BATCH1_POLICY_REPORTING_TABLE.csv       （§十五 中文业务表）

纪律：
  · 不得以 relevant=true 作为最终状态（§八）；review_status 五态机
  · 中文业务字段 = 受控本体词表（regulatory-topics.yaml 的
    name_zh/description/business_relevance）+ 证据引用；不自动翻译原文、
    不脱离 evidence 推断（§十）
  · D 类不为数量收录：进入主表但 review_status=EXCLUDED
  · Evidence Gate 保留三口径：strict_fulltext_rate / applicable_fulltext_rate
    / no_independent_manifestation_count（§九）
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.policy.acceptance import classify_record          # noqa: E402
from app.policy.backfill import load_records                # noqa: E402
from app.policy.black_mass import LINES as BM_LINES, classify_line  # noqa: E402
from app.policy.config import load_topics                   # noqa: E402
from app.policy.content_state import (classify_content_state,  # noqa: E402
                                      needs_fulltext)
from app.policy.domain_scope import (classify_domain_scope,  # noqa: E402
                                     is_domain_acceptance_consistent,
                                     guard_class)
from app.policy.identity_jurisdiction import (               # noqa: E402
    ISSUERS, dedicated_identity_completeness)
from app.policy.instruments import (instrument_from_metadata,  # noqa: E402
                                    instrument_from_nim_title,
                                    instrument_from_shape)
from app.policy.jurisdiction_onboarding import (             # noqa: E402
    contract_summary, load_contract)
from app.policy.saturation_gates import evidence_gate        # noqa: E402

ACC_DIR = ROOT / "outputs" / "acceptance"
REP_DIR = ROOT / "outputs" / "reporting"
ROUNDS_INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
TITLE_OVERLAY = ROOT / "outputs" / "overlays" / "corpus_title_overlay.jsonl"
IDENT_OVERLAY = ROOT / "outputs" / "overlays" / "identity_overlay.jsonl"

#: 本次运行套用 overlay 的 evidence_id 集合（审计可见）
OVERLAY_IDS: set[str] = set()
IDENT_OVERLAY_IDS: set[str] = set()


def load_title_overlay() -> dict[str, str]:
    """outputs/corpus_title_overlay.jsonl → {eid: title}（原始 evidence 不可变）。"""
    out: dict[str, str] = {}
    if not TITLE_OVERLAY.exists():
        return out
    for line in TITLE_OVERLAY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid, t = row.get("evidence_id"), row.get("title_overlay")
        if eid and t:
            out[str(eid)] = str(t)
    return out


def load_identity_overlay() -> dict[str, dict]:
    """outputs/identity_overlay.jsonl → {eid: {doc_key, language}}。"""
    out: dict[str, dict] = {}
    if not IDENT_OVERLAY.exists():
        return out
    for line in IDENT_OVERLAY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = row.get("evidence_id")
        ident = row.get("identity") or {}
        if eid and ident:
            out[str(eid)] = ident
    return out

# ------------------------------------------------------------ 范围

BATCH1_EU = ["AT", "HU", "CZ", "SK", "IT"]
BATCH1_US = ["US-MI", "US-GA", "US-IL", "US-TN", "US-TX", "US-NV", "US-CO"]
BATCH1 = BATCH1_EU + BATCH1_US
PILOTS = ["SE", "FI", "US-CA", "US-WA"]        # reference / 不计入 Batch1

BLOCKED_WITH_EVIDENCE = {
    "BE": "MULTI_VANTAGE_BLOCKED（本地+云双出口实证；ejustice 超时/拒绝）",
    "US-OH": "MULTI_VANTAGE_BLOCKED（ohio.gov 品牌 404 WAF + codes.ohio.gov "
             "ERR_TIMED_OUT；本地+浏览器通道均实证）",
}

COUNTRY_ZH = {
    "AT": "奥地利", "HU": "匈牙利", "CZ": "捷克", "SK": "斯洛伐克",
    "IT": "意大利",
    "US-MI": "美国·密歇根州", "US-GA": "美国·佐治亚州", "US-IL": "美国·伊利诺伊州",
    "US-TN": "美国·田纳西州", "US-TX": "美国·得克萨斯州",
    "US-NV": "美国·内华达州", "US-CO": "美国·科罗拉多州",
}

CN_INSTRUMENT = {
    "statute": "议会立法/法律", "regulation": "行政法规/法令",
    "directive": "指令（需转化）", "delegated_act": "授权法案",
    "implementing_act": "实施法案", "administrative_rule": "部门规章/行政规则",
    "standard": "标准", "official_guidance": "官方指南",
    "advisory": "安全通告/建议", "proposal": "立法提案", "draft": "草案",
    "consultation": "征求意见", "information_page": "信息页/科普",
    "news": "新闻/行业文章", "unknown": "待人工核验",
}

CN_LEVEL = {"member_state": "国家层级（欧盟成员国）", "state": "州层级（美国）"}

CN_STATUS = {
    "ACCEPTED": "已验收", "REVIEW_REQUIRED": "待人工复核",
    "BACKGROUND": "背景资料", "EXCLUDED": "已排除",
    "BLOCKED_EVIDENCE": "通道受阻（含证据）",
}

CN_LEGAL_STATUS = {
    "in_force": "现行有效", "amending_act": "修订法案",
    "repealed": "已废止", "unknown": "待人工核验",
}

#: 受控映射：主题 → 受影响主体（由主题描述领域归纳；人工可审）
ACTOR_BY_TOPIC = {
    "T01": "生产者/进口商/投放市场方", "T02": "回收企业/收集网点",
    "T03": "拆解企业/车辆处理企业", "T04": "梯次利用/再制造企业",
    "T05": "运输企业/仓储企业", "T06": "回收处理企业（黑粉链路）",
    "T07": "再生料采购方/加工企业", "T08": "出口商/进口商",
    "T09": "合规负责人/申报责任主体", "T10": "车辆制造商",
    "T11": "检测认证机构", "T12": "全链条经营者",
    "T13": "监管部门相对人", "T14": "海关/跨境经营者",
}

#: 受控映射：黑粉六线中文（black_mass.LINES 同步）
BM_ZH = {lid: name for lid, name, _pat in BM_LINES}

#: 动力电池关联标记（多语种——只做"是否直接提及"的抽取，不做程度推断）
TRACTION_RE = re.compile(
    r"traction\s+batter|trakčn|trak[čc]ni|hnac[íy]|vontat|trazione|laadvermogen"
    r"|elektromos\s+járm|elektromob|Antriebsbatter|Traktionsbatter|elektro"
    r"|batteria\s+di\s+trazione|lithium|li-?ion|litium|l[íi]tiov[áa]"
    r"|Traktionsbatterie", re.I)

EFFECTIVE_DATE_RES = [
    re.compile(r"účinnosti?\s+(?:dne\s+|od\s+)?(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"),
    re.compile(r"s\s+účinnosťou\s+od\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"),
    re.compile(r"hatályba\s+lép[a-záéíóöőúüű]*\s+(\d{4}\.\s*\w+\s*\d{1,2})"),
    re.compile(r"hatályos\s+(\d{4}\.\s*\w+\s*\d{1,2})"),
    re.compile(r"entra\s+in\s+vigore[^.]{0,40}?(\d{1,2}\s+\w+\s+\d{4})"),
    re.compile(r"in\s+Kraft[^.]{0,40}?(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"),
    re.compile(r"mit\s+Wirkung\s+vom\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"),
    re.compile(r"effective\s+(?:date\s*[:\-]?\s*)?([A-Z][a-z]+ \d{1,2},\s*\d{4})"),
]

CLAUSE_RES = [
    re.compile(r"§+\s*\d+\s*[a-z]?(?:\s*ods\.\s*\d+)?"),
    re.compile(r"čl(?:ánek|\.)\s*\d+"),
    re.compile(r"čl\.\s*\d+"),
    re.compile(r"\d+\s*\.?\s*cikk"),
    re.compile(r"\bart(?:icolo|\.)\s*\d+", re.I),
    re.compile(r"Section\s+\d+[\d\.\-]*", re.I),
    re.compile(r"\b§+\s*\d+"),
    re.compile(r"\bR\s?\d+\.?\d*"),            # IT regolamento 编号
]

AMEND_TITLE_RE = re.compile(
    r"měníc|mění\s|o\s+změně|noveliz|zmeny|o\s+zmene|módosít|modific|"
    r"Änderung|änderung|amendment|amend(?:ing|ment)", re.I)

REPEAL_TITLE_RE = re.compile(
    r"o\s+zrušen|zrušení|o\s+zrušen[íi]|zrušovac|o\s+zrušení|"
    r"repeal|derogat", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


# ------------------------------------------------------------ 装载

def jid_of(rec: dict) -> str:
    meta = rec.get("meta") or {}
    j = str(meta.get("jurisdiction") or "")
    if j:
        return j
    try:
        from app.policy.jurisdiction_map import jurisdiction_of
        return jurisdiction_of(rec) or ""
    except Exception:  # noqa: BLE001
        return ""


def load_snapshot_map() -> dict[str, str]:
    """evidence_id → 语料快照文件名（outputs/*.jsonl）。"""
    snap: dict[str, str] = {}
    for fp in glob.glob(str(ROOT / "outputs" / "*.jsonl")):
        name = Path(fp).name
        if name.startswith(("_", "review", "policy_metadata", "fr_identity")):
            continue
        for line in Path(fp).read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                eid = json.loads(line).get("evidence_id")
            except json.JSONDecodeError:
                continue
            if eid and eid not in snap:
                snap[eid] = name
    return snap


def load_plan_convergence() -> tuple[dict, dict]:
    """→ (hash12→convergence, plan_id→convergence)。"""
    if not ROUNDS_INDEX.exists():
        return {}, {}
    try:
        data = json.loads(ROUNDS_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, {}
    by_hash = data.get("plan_convergence") or {}
    by_plan: dict[str, dict] = {}
    for r in data.get("rounds") or []:
        pid = r.get("plan_id") or ""
        h = str(r.get("plan_hash") or "")[:12]
        if pid and h in by_hash:
            by_plan.setdefault(pid, by_hash[h])
    return by_hash, by_plan


# ------------------------------------------------------------ 单条映射

def classify(rec: dict):
    """→ (res, raw_class, stored_class)。raw 为分类器原输出（未过 domain 护栏）。"""
    res = None
    try:
        res = classify_record(rec)
    except Exception:  # noqa: BLE001
        res = None
    meta = rec.get("meta") or {}
    stored = str(meta.get("acceptance_class") or "")
    cls = (res.classification if res else "") or stored or "D"
    return res, cls, stored


def final_class_of(rec: dict) -> str:
    """最终类 = 分类器输出经 domain 护栏（2B1 口径：OOS+强类→D 等）。"""
    cache = getattr(final_class_of, "_cache", None)
    if cache is None:
        cache = {}
        final_class_of._cache = cache
    eid = str(rec.get("evidence_id"))
    if eid in cache:
        return cache[eid]
    try:
        raw = classify_record(rec).classification
    except Exception:  # noqa: BLE001
        raw = str((rec.get("meta") or {}).get("acceptance_class") or "D")
    scope = _safe(lambda: classify_domain_scope(rec), "unknown")
    is_nim = str(rec.get("source_id") or "").startswith("eu_nim_")
    cls = _safe(lambda: guard_class(raw, scope, is_nim=is_nim), raw)
    cache[eid] = cls
    return cls


def instrument_of(rec: dict) -> tuple[str, str, str]:
    meta = rec.get("meta") or {}
    title = rec.get("title") or ""
    r = _safe(lambda: instrument_from_metadata(meta), None)
    r = r or _safe(lambda: instrument_from_shape(title), None) \
        or _safe(lambda: instrument_from_nim_title(title), None)
    if r:
        return r.instrument_type, r.binding_force, r.matched
    return "unknown", "unknown", ""


def extract_clause(res, rec: dict) -> str:
    quote = (res.evidence_quotes[0] if res and res.evidence_quotes else "")
    hay = quote + "\n" + (rec.get("text") or "")[:6000]
    for rx in CLAUSE_RES:
        m = rx.search(hay)
        if m:
            return m.group(0).strip()
    return ""


def extract_effective_date(rec: dict) -> str:
    text = (rec.get("text") or "")[:20000]
    for rx in EFFECTIVE_DATE_RES:
        m = rx.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    meta = rec.get("meta") or {}
    return str(meta.get("effective_date") or "")


def legal_status_of(rec: dict) -> str:
    meta = rec.get("meta") or {}
    explicit = str(meta.get("legal_status") or "").strip().lower()
    if explicit:
        return explicit
    title = rec.get("title") or ""
    if REPEAL_TITLE_RE.search(title):
        return "repealed"
    if AMEND_TITLE_RE.search(title):
        return "amending_act"
    return "unknown"


def identity_ok(rec: dict) -> bool:
    meta = rec.get("meta") or {}
    doc_key = str(meta.get("doc_key") or "")
    return bool(doc_key and ":" in doc_key
                and str(meta.get("language") or ""))


def status_of(cls: str, rec: dict, res, clause: str) -> tuple[str, list[str]]:
    """§八 五态机（不得使用 relevant=true 作为最终状态）。"""
    notes: list[str] = []
    if cls == "D":
        return "EXCLUDED", ["CLASS_D"]
    if cls == "C":
        return "BACKGROUND", []
    if cls in ("A1", "A2"):
        if identity_ok(rec):
            return "ACCEPTED", []
        return "REVIEW_REQUIRED", ["IDENTITY_INCOMPLETE"]
    if cls == "B":
        ft = classify_content_state(rec) == "FULLTEXT"
        if not clause:
            notes.append("B_CANDIDATE_NO_CLAUSE")
        if not ft:
            notes.append("PLACEHOLDER_TEXT")
        if not identity_ok(rec):
            notes.append("IDENTITY_INCOMPLETE")
        return ("ACCEPTED" if not notes else "REVIEW_REQUIRED"), notes
    return "REVIEW_REQUIRED", ["UNCLASSIFIED"]


def build_row(rec: dict, snap: dict[str, str]) -> dict:
    meta = rec.get("meta") or {}
    res, cls_raw, stored = classify(rec)
    jid = jid_of(rec)
    title = rec.get("title") or ""
    doc_key = str(meta.get("doc_key") or "")
    oid = doc_key.split(":", 1)[1] if ":" in doc_key else doc_key
    itype, binding, _matched = instrument_of(rec)
    clause = extract_clause(res, rec)
    quotes = list(res.evidence_quotes) if res else []
    topics = list(res.topic_ids) if res else list(meta.get("topic_ids") or [])
    bm_lines = [lid for lid, _n, _p in BM_LINES if classify_line(rec, lid)]
    scope = _safe(lambda: classify_domain_scope(rec), "unknown")
    cls = final_class_of(rec)          # domain 护栏后最终类
    lst = legal_status_of(rec)
    status, notes = status_of(cls, rec, res, clause)
    if cls != cls_raw:
        notes = [f"DOMAIN_GUARD({cls_raw}->{cls})"] + notes
    if stored and stored != cls_raw:
        notes = notes + [f"CLASS_MISMATCH(stored={stored},raw={cls_raw})"]
    eid = str(rec.get("evidence_id") or "")
    return {
        "jurisdiction": jid,
        "country_or_state": COUNTRY_ZH.get(jid, jid),
        "title": title,
        "official_identifier": oid,
        "canonical_id": doc_key or f"{jid}:{eid}",
        "issuer": ISSUERS.get(jid, ""),
        "instrument_type": itype,
        "binding_force": binding,
        "legal_status": lst,
        "publication_date": rec.get("publish_date") or "",
        "effective_date": extract_effective_date(rec),
        "domain_scope": scope,
        "acceptance_class": cls,
        "topic_ids": topics,
        "black_mass_lines": bm_lines,
        "evidence_quote": (quotes[0] if quotes else ""),
        "article_section_clause": clause,
        "official_url": rec.get("url") or "",
        "snapshot_path": f"outputs/{snap.get(eid, '')}" if snap.get(eid) else "",
        "legal_family": itype,
        "source_role": str(meta.get("source_role") or ""),
        "retrieved_at": str(meta.get("discovered_by_round") or
                            meta.get("collector") or ""),
        "review_status": status,
        # ---- 审计附加（不进 23 字段必填口径，CSV 附列）----
        "evidence_id": eid,
        "stored_acceptance_class": stored,
        "review_notes": ";".join(notes),
        "requires_fulltext": needs_fulltext(rec, cls),
        "content_state": classify_content_state(rec),
        "source_id": rec.get("source_id") or "",
        "title_overlay_applied": eid in OVERLAY_IDS,
        "identity_overlay_applied": eid in IDENT_OVERLAY_IDS,
    }


# ------------------------------------------------------------ 聚合

def topic_matrix(records: list[dict], rows_by_eid: dict[str, dict],
                 topics_cfg) -> dict:
    out = {"topics": [], "p0_missing": []}
    for t in topics_cfg.topics:
        docs, strong = [], []
        for r in records:
            row = rows_by_eid.get(str(r.get("evidence_id")))
            if not row or t.id not in (row["topic_ids"] or []):
                continue
            if row["acceptance_class"] in ("A1", "A2", "B", "C"):
                docs.append(row["evidence_id"])
            if row["acceptance_class"] in ("A1", "A2", "B"):
                strong.append(row["evidence_id"])
        status = ("COVERED" if strong else
                  "PARTIAL" if docs else "MISSING")
        out["topics"].append({
            "id": t.id, "name_zh": t.name_zh, "risk_level": t.risk_level,
            "status": status, "docs": len(docs), "strong": len(strong),
            "evidence_ids": docs[:8],
        })
        if t.risk_level == "P0" and not docs:
            out["p0_missing"].append(t.id)
    return out


def black_mass_matrix(records: list[dict], rows_by_eid: dict[str, dict],
                      jid: str) -> dict:
    is_state = jid.startswith("US-")
    out = {"lines": [], "notes": []}
    for lid, name, _pat in BM_LINES:
        docs, strong = [], []
        for r in records:
            row = rows_by_eid.get(str(r.get("evidence_id")))
            if not row:
                continue
            if lid in (row["black_mass_lines"] or []):
                docs.append(row["evidence_id"])
                if row["acceptance_class"] in ("A1", "A2", "B"):
                    strong.append(row["evidence_id"])
        if is_state and lid in ("transboundary", "customs"):
            status = "NOT_APPLICABLE_FEDERAL_ONLY"
        else:
            status = ("COVERED" if strong else
                      "PARTIAL" if docs else "MISSING")
        out["lines"].append({"id": lid, "name_zh": name, "status": status,
                             "docs": len(docs), "strong": len(strong),
                             "evidence_ids": docs[:8]})
    return out


def source_roles_of(jid: str, records: list[dict]) -> dict:
    sid_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for r in records:
        sid = str(r.get("source_id") or "")
        sid_counts[sid] = sid_counts.get(sid, 0) + 1
        role = str((r.get("meta") or {}).get("source_role") or "")
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    try:
        c = load_contract(jid)
        summary = contract_summary(c)
    except Exception as exc:  # noqa: BLE001
        return {"jurisdiction": jid, "contract": None, "error": str(exc),
                "roles": [], "corpus_source_ids": sid_counts}
    roles = []
    for r in summary["roles"]:
        srcs = [ch.get("source_id") for ch in r.get("channels") or []]
        corpus = sum(sid_counts.get(s, 0) for s in srcs)
        roles.append({**r, "corpus_records": corpus,
                      "corpus_backed": corpus > 0})
    return {
        "jurisdiction": jid,
        "coverage_pct": summary["coverage_pct"],
        "covered_roles": summary["covered_roles"],
        "mandatory_roles": summary["mandatory_roles"],
        "roles": roles,
        "corpus_source_ids": sid_counts,
        "corpus_role_records": role_counts,
    }


def convergence_of(jid: str, by_hash: dict, by_plan: dict) -> dict:
    plans = {pid: conv for pid, conv in by_plan.items()
             if pid.startswith(jid + "_") or pid == jid + "_PLAN"}
    converged_any = any(bool(v.get("converged")) for v in plans.values())
    return {
        "jurisdiction": jid,
        "plans": plans,
        "converged": converged_any,
        "state": ("CONVERGED" if converged_any else "NOT_YET_CONVERGED"),
    }


def evidence_summary_of(records: list[dict]) -> dict:
    """A1/A2/B 三口径（§九）：strict / applicable / no_independent_manifestation。"""
    summary: dict = {}
    for cls in ("A1", "A2", "B"):
        sub = [r for r in records if final_class_of(r) == cls]
        n = len(sub)
        strict = sum(1 for r in sub
                     if classify_content_state(r) == "FULLTEXT")
        exempt = [r for r in sub if (r.get("meta") or {}).get("no_online_variant")]
        misses = [r for r in sub
                  if needs_fulltext(r, cls) and r not in exempt]
        applicable_n = n
        applicable_ok = n - len(misses)
        # 空类（n=0）：fulltext_pct 计 100（vacuous truth；是否存在高价值
        # 文书由 high_value_docs_ge_1 检查单独把关）
        apt_rate = (round(100.0 * applicable_ok / applicable_n, 1)
                    if applicable_n else 100.0)
        clause_ok = sum(1 for r in sub if has_clause(r))
        clause_rate = (round(100.0 * clause_ok / n, 1) if n else 100.0)
        summary[cls] = {
            "n": n,
            "fulltext_n": strict,
            "fulltext_pct": apt_rate,          # evidence_gate 口径（applicable）
            "strict_fulltext_rate": round(100.0 * strict / n, 1) if n else 0.0,
            "applicable_fulltext_rate": apt_rate,
            "no_independent_manifestation_count": len(exempt),
            "clause_ok": clause_ok,
            # 空类计 100（vacuous；B 是否存在由 high_value/evidence 检查把关）
            "clause_pct": clause_rate if n else 100.0,
        }
    return summary


def has_clause(rec: dict) -> bool:
    """B 条款证据：现算分类器 quotes 非空（content_state 同口径）。"""
    try:
        return bool(classify_record(rec).evidence_quotes)
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------ Gate（§十二）

def gate_of(jid: str, level: str, records: list[dict], rows: list[dict],
            roles: dict, conv: dict, tm: dict, ev: dict,
            domain_contradictions: int) -> dict:
    critical = {"member_state": ("MS_LEGISLATION_DATABASE", "MS_OFFICIAL_GAZETTE"),
                "state": ("STATE_LEGISLATURE", "STATE_STATUTES")}.get(level, ())
    role_map = {r["role"]: r for r in roles.get("roles") or []}
    crit_ok = [role_map.get(r, {}).get("covered") for r in critical] if critical else []
    crit_pct = (round(100.0 * sum(1 for c in crit_ok if c) / len(crit_ok), 1)
                if crit_ok else 0.0)
    crit_corpus = [role_map.get(r, {}).get("corpus_backed") for r in critical] \
        if critical else []
    crit_corpus_pct = (round(100.0 * sum(1 for c in crit_corpus if c)
                             / len(crit_corpus), 1) if crit_corpus else 0.0)

    idc = _safe(lambda: dedicated_identity_completeness(records, jid), {})
    id_pct = float(idc.get("pct") or 0.0)

    eg = evidence_gate(ev)
    hv_n = sum(ev[c]["n"] for c in ("A1", "A2", "B"))
    b = ev.get("B") or {}
    # P0 映射缺陷（§十二 "Topic Mapping 无 P0"）：高价值文书不得
    # **完全无标注**（主题/黑粉线/证据引用均空）——否则为映射缺陷；
    # 仅主题空但有其他标注 → topic_gap（descriptive，不 gate）
    hv_rows = [r for r in rows if r["acceptance_class"] in ("A1", "A2", "B")]
    hv_unmapped = sum(1 for r in hv_rows
                      if not r["topic_ids"] and not r["black_mass_lines"]
                      and not r["evidence_quote"])
    hv_topic_gap = sum(1 for r in hv_rows if not r["topic_ids"])

    checks = {
        "critical_source_coverage_ge_90": crit_pct >= 90.0,
        "identity_completeness_ge_95": id_pct >= 95.0,
        "high_value_docs_ge_1": hv_n >= 1,
        "evidence_gate_a1a2b_fulltext_ge_95": bool(eg.get("ok")) or hv_n == 0,
        "b_clause_ge_95": (float(b.get("clause_pct") or 0.0) >= 95.0)
                          or int(b.get("n") or 0) == 0,
        "domain_contradiction_zero": domain_contradictions == 0,
        "no_p0_topic_mapping_defect": hv_unmapped == 0,
        "mode_b_converged_or_declared": True,   # converged 或显式 NOT_YET
    }
    accepted = all(checks.values())
    return {
        "jurisdiction": jid, "level": level,
        "JURISDICTION_CORPUS_ACCEPTED": bool(accepted),
        "checks": checks,
        "detail": {
            "critical_roles": list(critical),
            "critical_coverage_pct": crit_pct,
            "critical_corpus_backed_pct": crit_corpus_pct,
            "identity_pct": id_pct,
            "high_value_n": hv_n,
            "hv_unmapped": hv_unmapped,
            "hv_topic_gap": hv_topic_gap,
            "evidence_gate": eg,
            "domain_contradictions": domain_contradictions,
            "p0_topic_gaps": tm.get("p0_missing") or [],
            "convergence_state": conv.get("state"),
            "convergence_note": (None if conv.get("converged")
                                 else "NOT_YET_CONVERGED（V2 扩产进行/未收敛）"),
        },
    }


# ------------------------------------------------------------ 中文业务字段（§十）

def biz_fields(row: dict, topics_cfg) -> dict:
    tid_names = {t.id: t for t in topics_cfg.topics}
    tids = [t for t in (row.get("topic_ids") or []) if t in tid_names]
    names = [tid_names[t].name_zh for t in tids]
    impacts = [tid_names[t].business_relevance for t in tids
               if getattr(tid_names[t], "business_relevance", "")]
    descs = [tid_names[t].description for t in tids]
    actor = next((ACTOR_BY_TOPIC[t] for t in tids if t in ACTOR_BY_TOPIC), "")
    material = ("废电池/废锂离子电池（黑粉链条相关）"
                if any(t in ("T02", "T06", "T07") for t in tids)
                else "废电池" if tids else "")
    return {
        "policy_summary_cn": (
            f"{row['country_or_state']}{CN_INSTRUMENT.get(row['instrument_type'], '文书')}"
            f"《{row['title']}》（编号 {row['official_identifier']}）——"
            f"主题：{'；'.join(names) if names else '未映射'}；"
            f"证据段落见「证据条款」栏。"),
        "business_impact_cn": (" ".join(impacts[:2]) if impacts
                               else "主题未映射（人工复核后补充）"),
        "compliance_obligation_cn": ("；".join(descs[:2]) if descs
                                     else "未映射义务（人工复核后补充）"),
        "affected_actor": actor or "待人工核验",
        "affected_material": material or "待人工核验",
        "effective_status_cn": CN_LEGAL_STATUS.get(row.get("legal_status") or
                                                   "unknown", "待人工核验"),
    }


def traction_note(row: dict, rec: dict) -> str:
    if TRACTION_RE.search((rec.get("title") or "") + "\n"
                          + (rec.get("text") or "")[:8000]):
        return "直接提及（动力电池/锂电）"
    return "未直接提及"


# ------------------------------------------------------------ 输出

def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k in ("topic_ids", "black_mass_lines"):
                if isinstance(out.get(k), list):
                    out[k] = ";".join(str(x) for x in out[k])
            w.writerow(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    topics_cfg = load_topics()
    records = load_records(ROOT)
    overlay = load_title_overlay()
    ident_overlay = load_identity_overlay()
    if overlay or ident_overlay:
        merged = []
        for r in records:
            eid = str(r.get("evidence_id") or "")
            nrec = r
            if eid in overlay:
                nrec = dict(nrec)
                nrec["title"] = overlay[eid]
                nrec["_title_overlay"] = True
                OVERLAY_IDS.add(eid)
            if eid in ident_overlay:
                nrec = dict(nrec)
                meta = dict(nrec.get("meta") or {})
                meta.update(ident_overlay[eid])
                nrec["meta"] = meta
                nrec["_identity_overlay"] = True
                IDENT_OVERLAY_IDS.add(eid)
            merged.append(nrec)
        records = merged
    snap = load_snapshot_map()
    by_hash, by_plan = load_plan_convergence()

    recs = [r for r in records if jid_of(r) in BATCH1]
    rows = [build_row(r, snap) for r in recs]
    rows_by_eid = {r["evidence_id"]: r for r in rows}
    by_jid: dict[str, list[dict]] = {}
    for r in recs:
        by_jid.setdefault(jid_of(r), []).append(r)
    rows_by_jid: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_jid.setdefault(row["jurisdiction"], []).append(row)

    # ---- 主表 ----
    main_fields = [
        "jurisdiction", "country_or_state", "title", "official_identifier",
        "canonical_id", "issuer", "instrument_type", "binding_force",
        "legal_status", "publication_date", "effective_date", "domain_scope",
        "acceptance_class", "topic_ids", "black_mass_lines", "evidence_quote",
        "article_section_clause", "official_url", "snapshot_path",
        "legal_family", "source_role", "retrieved_at", "review_status",
        # 审计附列
        "evidence_id", "stored_acceptance_class", "review_notes",
        "requires_fulltext", "content_state", "source_id",
    ]
    # 排序：管辖地 → 类 → 编号
    cls_order = {"A1": 0, "A2": 1, "B": 2, "C": 3, "D": 4}
    rows_sorted = sorted(rows, key=lambda r: (BATCH1.index(r["jurisdiction"])
                          if r["jurisdiction"] in BATCH1 else 99,
                          cls_order.get(r["acceptance_class"], 9),
                          r["official_identifier"]))

    gates: dict[str, dict] = {}
    packages_root = ACC_DIR
    counts_by_jid: dict[str, dict] = {}

    for jid in BATCH1:
        jrecs = by_jid.get(jid, [])
        jrows = rows_by_jid.get(jid, [])
        level = "state" if jid.startswith("US-") else "member_state"
        tm = topic_matrix(jrecs, rows_by_eid, topics_cfg)
        bm = black_mass_matrix(jrecs, rows_by_eid, jid)
        roles = source_roles_of(jid, jrecs)
        conv = convergence_of(jid, by_hash, by_plan)
        ev = evidence_summary_of(jrecs)
        contradictions = 0
        for r in jrecs:
            cls = final_class_of(r)
            scope = _safe(lambda: classify_domain_scope(r), "unknown")
            if not _safe(lambda: is_domain_acceptance_consistent(scope, cls),
                         True):
                contradictions += 1
        gate = gate_of(jid, level, jrecs, jrows, roles, conv, tm, ev,
                       contradictions)
        gates[jid] = gate
        counts = {c: sum(1 for r in jrows if r["acceptance_class"] == c)
                  for c in ("A1", "A2", "B", "C", "D")}
        counts_by_jid[jid] = counts

        if args.dry:
            continue

        pkg = packages_root / jid
        pkg.mkdir(parents=True, exist_ok=True)
        # 1. accepted_policies.csv（ACCEPTED + REVIEW_REQUIRED）
        acc_rows = [r for r in jrows
                    if r["review_status"] in ("ACCEPTED", "REVIEW_REQUIRED")]
        write_csv(pkg / "accepted_policies.csv", acc_rows, main_fields)
        # 2. coverage.json
        (pkg / "coverage.json").write_text(json.dumps({
            "jurisdiction": jid, "level": level,
            "generated_at": _now_iso(),
            "records": len(jrecs), "classes": counts,
            "high_value": sum(counts[c] for c in ("A1", "A2", "B")),
            "evidence": ev,
            "identity": _safe(lambda: dedicated_identity_completeness(
                jrecs, jid), {}),
            "domain_contradictions": contradictions,
            "contract_coverage_pct": roles.get("coverage_pct"),
            "gate": gate["checks"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # 3. topic_matrix.json
        (pkg / "topic_matrix.json").write_text(
            json.dumps(tm, ensure_ascii=False, indent=2), encoding="utf-8")
        # 4. black_mass_matrix.json
        (pkg / "black_mass_matrix.json").write_text(
            json.dumps(bm, ensure_ascii=False, indent=2), encoding="utf-8")
        # 5. source_roles.json
        (pkg / "source_roles.json").write_text(
            json.dumps(roles, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # 6. convergence.json
        (pkg / "convergence.json").write_text(
            json.dumps(conv, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # 7. blocked_gaps.json
        blocked_roles = [r for r in (roles.get("roles") or [])
                         if not r.get("covered")]
        (pkg / "blocked_gaps.json").write_text(json.dumps({
            "jurisdiction": jid,
            "blocked_or_missing_roles": [
                {"role": r["role"], "gap": r.get("gap") or "",
                 "channels": r.get("channels") or []}
                for r in blocked_roles],
            "p0_missing_topics": tm.get("p0_missing") or [],
            "missing_black_mass_lines": [
                l["id"] for l in bm["lines"]
                if l["status"] == "MISSING"],
            "notes": ("US-OH/BE 类外部阻断案例见 BATCH1 全局说明；"
                      "本包只记录本管辖地内缺口。"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # 8. evidence_samples.md
        top = [r for r in sorted(acc_rows,
                                 key=lambda x: cls_order[x["acceptance_class"]])
               ][:6]
        lines_md = [f"# {jid} — Evidence Samples（{len(top)} 例）", ""]
        for r in top:
            lines_md += [
                f"## {r['acceptance_class']} · {r['title']}",
                f"- 编号：`{r['official_identifier']}` ｜ 角色：{r['source_role']}",
                f"- 官方链接：{r['official_url']}",
                f"- 条款证据：{r['article_section_clause'] or '（正文段落）'}",
                f"- 引用：{(r['evidence_quote'] or '')[:260]}",
                "",
            ]
        (pkg / "evidence_samples.md").write_text("\n".join(lines_md),
                                                 encoding="utf-8")
        # 9. summary.md
        gate_cn = "✅ JURISDICTION_CORPUS_ACCEPTED" if \
            gate["JURISDICTION_CORPUS_ACCEPTED"] else "⚠️ REVIEW_REQUIRED"
        fails = [k for k, v in gate["checks"].items() if not v]
        (pkg / "summary.md").write_text("\n".join([
            f"# {jid}（{COUNTRY_ZH.get(jid, jid)}）验收摘要",
            "",
            f"- 状态：**{gate_cn}**",
            f"- 文书：A1={counts['A1']} · A2={counts['A2']} · B={counts['B']}"
            f" · C={counts['C']} · D={counts['D']}（共 {len(jrecs)} 条）",
            f"- 身份完整度：{gate['detail']['identity_pct']}%",
            f"- 关键角色覆盖：{gate['detail']['critical_coverage_pct']}%"
            f"（语料支撑 {gate['detail']['critical_corpus_backed_pct']}%）",
            f"- MODE B：{gate['detail']['convergence_state']}",
            f"- 未过检查：{'、'.join(fails) if fails else '无'}",
            "",
            "> 本包字段口径见 batch1_policy_acceptance.csv 表头；"
            "中文业务字段生成规则见构建器文档字符串（受控词表 + 证据引用）。",
        ]), encoding="utf-8")

    if not args.dry:
        ACC_DIR.mkdir(parents=True, exist_ok=True)
        write_csv(ACC_DIR / "batch1_policy_acceptance.csv", rows_sorted,
                  main_fields)
        (ACC_DIR / "batch1_policy_acceptance.json").write_text(json.dumps({
            "generated_at": _now_iso(),
            "scope": {"eu": BATCH1_EU, "us": BATCH1_US, "pilots": PILOTS,
                      "blocked_with_evidence": BLOCKED_WITH_EVIDENCE},
            "counts_by_jid": counts_by_jid,
            "rows": rows_sorted,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        gates_dir = ACC_DIR / "gates"
        gates_dir.mkdir(parents=True, exist_ok=True)
        (gates_dir / "batch1_jurisdiction_gates.json").write_text(
            json.dumps({"generated_at": _now_iso(), "gates": gates},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        # ---- 业务汇报总表（§十五）----
        biz_rows = []
        for r in rows_sorted:
            if r["review_status"] not in ("ACCEPTED", "REVIEW_REQUIRED",
                                          "BACKGROUND"):
                continue
            rec = next((x for x in recs
                        if str(x.get("evidence_id")) == r["evidence_id"]), {})
            bf = biz_fields(r, topics_cfg)
            topic_names = [t.name_zh for t in topics_cfg.topics
                           if t.id in (r["topic_ids"] or [])]
            bm_names = [BM_ZH.get(l, l) for l in (r["black_mass_lines"] or [])]
            biz_rows.append({
                "国家/州": r["country_or_state"],
                "政策名称": r["title"],
                "政策编号": r["official_identifier"],
                "政策层级": CN_LEVEL.get(
                    "state" if r["jurisdiction"].startswith("US-")
                    else "member_state", ""),
                "政策类型": CN_INSTRUMENT.get(r["instrument_type"],
                                              r["instrument_type"]),
                "当前状态": bf["effective_status_cn"],
                "发布日期": r["publication_date"] or "待补",
                "生效日期": r["effective_date"] or "待补",
                "A1/A2/B/C/D": r["acceptance_class"],
                "监管主题": "；".join(topic_names) or "未映射",
                "黑粉关联": "；".join(bm_names) or "未命中六线",
                "动力电池关联": traction_note(r, rec) if rec else "待核",
                "核心要求": bf["compliance_obligation_cn"],
                "对回收企业影响": bf["business_impact_cn"],
                "证据条款": ((r["article_section_clause"] + "｜") if
                            r["article_section_clause"] else "")
                            + (r["evidence_quote"] or "")[:160],
                "官方链接": r["official_url"],
                "审核状态": CN_STATUS.get(r["review_status"],
                                          r["review_status"]),
                # 附：证据字段（§十 保留便于人工复核）
                "policy_summary_cn": bf["policy_summary_cn"],
                "affected_actor": bf["affected_actor"],
                "affected_material": bf["affected_material"],
            })
        REP_DIR.mkdir(parents=True, exist_ok=True)
        biz_fields_list = ["国家/州", "政策名称", "政策编号", "政策层级",
                           "政策类型", "当前状态", "发布日期", "生效日期",
                           "A1/A2/B/C/D", "监管主题", "黑粉关联",
                           "动力电池关联", "核心要求", "对回收企业影响",
                           "证据条款", "官方链接", "审核状态",
                           "policy_summary_cn", "affected_actor",
                           "affected_material"]
        write_csv(REP_DIR / "BATCH1_POLICY_REPORTING_TABLE.csv", biz_rows,
                  biz_fields_list)
        try:
            from openpyxl import Workbook  # type: ignore
            wb = Workbook()
            ws = wb.active
            ws.title = "Batch1Policy"
            ws.append(biz_fields_list)
            for row in biz_rows:
                ws.append([row.get(k, "") for k in biz_fields_list])
            wb.save(REP_DIR / "BATCH1_POLICY_REPORTING_TABLE.xlsx")
            xlsx = True
        except Exception:  # noqa: BLE001
            xlsx = False

    # ---- 终端摘要 ----
    total = {c: sum(1 for r in rows if r["acceptance_class"] == c)
             for c in ("A1", "A2", "B", "C", "D")}
    print(f"BATCH1 records={len(rows)} classes={total}")
    for jid in BATCH1:
        g = gates[jid]
        print(f"  {jid:7s} {str(counts_by_jid[jid])} "
              f"accepted={g['JURISDICTION_CORPUS_ACCEPTED']} "
              f"fail={[k for k, v in g['checks'].items() if not v]}")
    n_acc = sum(1 for g in gates.values() if g["JURISDICTION_CORPUS_ACCEPTED"])
    print(f"corpus_accepted={n_acc}/{len(BATCH1)}")
    if not args.dry:
        print(f"→ {ACC_DIR / 'batch1_policy_acceptance.csv'}")
        print(f"→ {REP_DIR / 'BATCH1_POLICY_REPORTING_TABLE.csv'}"
              + (" + .xlsx" if 'xlsx' in dir() and xlsx else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
