# -*- coding: utf-8 -*-
"""Legal Family 官方关系（Phase 4B-1 Step 7）—— Cellar SPARQL 反向关系。

实测谓词（2026-09-12，ELV 32000L0053）：
    resource_legal_amends_resource_legal                     → 16 个修订法
    resource_legal_corrects_resource_legal                   → 3 个更正（R(01)/(02)/(03)）
    resource_legal_repeals_resource_legal                    → 废止（入边=废止本法者）
    resource_legal_proposes_to_amend_resource_legal          → 提案
    resource_legal_does_replacement_of_resource_legal        → 替换
    measure_national_implementing_implements_resource_legal  → 成员国转化措施（NIM）
    act_consolidated_consolidates_resource_legal             → 合并版本（38 个）

纪律：家族关系**必须**来自官方数据（Cellar / EUR-Lex），不得由标题猜测。
"""
from __future__ import annotations

#: 家族关系 → Cellar 入边谓词（?src <pred> <root>）
RELATION_PREDICATES: dict[str, str] = {
    "AMENDS": "resource_legal_amends_resource_legal",
    "CORRIGENDUM_OF": "resource_legal_corrects_resource_legal",
    "REPEALS": "resource_legal_repeals_resource_legal",
    "REPLACED_BY": "resource_legal_does_replacement_of_resource_legal",
    "RELATED_PROPOSAL": "resource_legal_proposes_to_amend_resource_legal",
    "TRANSPOSES": "measure_national_implementing_implements_resource_legal",
    "CONSOLIDATED": "act_consolidated_consolidates_resource_legal",
}

Q_WORK_BY_CELEX = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?celexv WHERE {{
  ?work cdm:resource_legal_id_celex ?celexv .
  FILTER(STR(?celexv) = "{celex}")
}} LIMIT 5
"""

Q_INCOMING = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?src ?celex ?date WHERE {{
  ?src <{pred}> <{work}> .
  OPTIONAL {{ ?src cdm:resource_legal_id_celex ?celex }}
  OPTIONAL {{ ?src cdm:work_date_document ?date }}
}} LIMIT {limit}
"""


def normalize_rows(rows: list[dict]) -> list[dict]:
    """SPARQL bindings → [{celex, date, uri}]（去重、按 celex 排序）。"""
    out: list[dict] = []
    seen: set[str] = set()
    for b in rows or []:
        celex = ((b.get("celex") or {}).get("value") or "").strip()
        uri = ((b.get("src") or {}).get("value") or "").strip()
        date = ((b.get("date") or {}).get("value") or "")[:10]
        key = celex or uri
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"celex": celex, "date": date, "uri": uri})
    out.sort(key=lambda r: (r["celex"], r["date"]))
    return out


def merge_family(*, expected: list[str], corpus_found: set[str],
                 official: dict[str, list[dict]] | None) -> dict:
    """合并「语料内标题证据」与「官方关系」→ 解析结果。

    返回：{resolved_corpus, resolved_official, unresolved, absent_official, completeness}
    · absent_official：expected 中既无标题证据、也**无官方关系**的关系
      （= 官方确实不存在该关系，须在报告中标注，不得算作缺口）
    """
    official = official or {}
    resolved_corpus = [r for r in expected if r in corpus_found]
    resolved_official = [r for r in expected
                         if r not in resolved_corpus and official.get(r)]
    unresolved = [r for r in expected
                  if r not in resolved_corpus and r not in resolved_official]
    # 对 unresolved 做官方缺席判定：查询已执行且返回空 → absent_official
    absent_official = [r for r in unresolved
                       if r in (official or {}) and not official.get(r)]
    resolved_n = len(resolved_corpus) + len(resolved_official)
    return {
        "resolved_corpus": resolved_corpus,
        "resolved_official": resolved_official,
        "unresolved": unresolved,
        "absent_official": absent_official,
        "completeness": round(resolved_n / len(expected), 3) if expected else 1.0,
    }
