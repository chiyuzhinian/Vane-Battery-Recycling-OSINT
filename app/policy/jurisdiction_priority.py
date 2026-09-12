# -*- coding: utf-8 -*-
"""Jurisdiction Priority Score（Phase 4B-2A Step 3）—— 纯逻辑。

8 维加权（权重和为 1.0，写死并测试锁定）：
    battery_recycling_business_relevance  0.25   ← signals.battery_industry/5
    EV_market_relevance                   0.15   ← signals.ev_market/5
    recycling_industry_presence           0.10   ← signals.recycling_industry/5
    known_policy_signal                   0.20   ← signals.policy_signal/5
    source_gap_risk                       0.10   ← (1 − accessibility)×0.10
        （语义：**缺口越大越需靠前补源** —— 这是优先度增量，不是质量惩罚）
    official_source_accessibility         0.10   ← accessibility×0.10
    legal_system_diversity                0.05   ← diversity×0.05
    existing_connector_reuse              0.05   ← reuse×0.05

选择规则（在分数之上加"可运行性 + 阶段目的"两种约束，均显式记录）：
    · accessibility < access_floor(0.5) → 只能作 RESERVE（需先修复通道）
    · US 州至少 min_policy(=2) 个来自 policy_signal ≥ 4（A1 栖息地约束）
    · EU 额外 1 个 stretch = 剩余候选中 diversity 最高者（结构多样性验证）
"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.policy.config import ConfigError, load_registry

ROOT = Path(__file__).resolve().parent.parent.parent
SIGNALS_FILE = ROOT / "sources" / "jurisdiction-priority-signals.yaml"

WEIGHTS = {
    "battery_recycling_business_relevance": 0.25,
    "EV_market_relevance": 0.15,
    "recycling_industry_presence": 0.10,
    "known_policy_signal": 0.20,
    "source_gap_risk": 0.10,
    "official_source_accessibility": 0.10,
    "legal_system_diversity": 0.05,
    "existing_connector_reuse": 0.05,
}

REFERENCE_JURISDICTIONS = ("DE", "NL", "ES", "FR")

#: 可达性打分：probe 分类 → 0..1
ACCESS_SCORE = {
    "http_200": 1.0,
    "http_200_spa": 0.6,
    "http_4xx": 0.3,
    "http_5xx": 0.3,
    "error": 0.1,
    "unknown": 0.5,
}

#: 既有 connector 复用（参考专线 1.0；US-CA 浏览器通道 0.3）
REUSE_OVERRIDES = {"DE": 1.0, "NL": 1.0, "ES": 1.0, "FR": 1.0, "US-CA": 0.3}

SIGNAL_FIELDS = ("battery_industry", "ev_market", "recycling_industry", "policy_signal")


def load_signals(path: Path | None = None) -> dict:
    fp = path or SIGNALS_FILE
    if not fp.exists():
        raise ConfigError(f"priority signals 不存在：{fp}")
    data = yaml.safe_load(fp.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("priority signals 顶层必须是映射")
    _validate_signals(data)
    return data


def _validate_signals(data: dict) -> None:
    reg = load_registry()
    want_ms, want_states = set(), set()
    for j in reg.jurisdictions:
        want_ms |= {c.get("code") for c in j.countries}
        want_states |= {s.get("code") for s in j.states}
    got_ms = set((data.get("eu_member_states") or {}).keys())
    got_states = set((data.get("us_states") or {}).keys())
    if want_ms - got_ms:
        raise ConfigError(f"signals 缺欧盟成员国：{sorted(want_ms - got_ms)}")
    if want_states - got_states:
        raise ConfigError(f"signals 缺州级：{sorted(want_states - got_states)}")
    for group in ("eu_member_states", "us_states"):
        for jid, entry in (data.get(group) or {}).items():
            for f in SIGNAL_FIELDS:
                v = entry.get(f)
                if not isinstance(v, int) or not 0 <= v <= 5:
                    raise ConfigError(f"信号值非法：{jid}.{f}={v!r}（须 0–5 整数）")
    # 权重和
    total = round(sum(WEIGHTS.values()), 6)
    if total != 1.0:
        raise ConfigError(f"优先级权重和必须为 1.0，当前 {total}")


def accessibility_from_probe(probe_rows: list[dict]) -> dict[str, dict]:
    """probe 行 → {jid: {score, detail}}。"""
    out: dict[str, dict] = {}
    for r in probe_rows or []:
        jid = r.get("id") or ""
        kind = r.get("probe_class") or _classify(r)
        score = ACCESS_SCORE.get(kind, ACCESS_SCORE["unknown"])
        out[jid] = {"score": score, "detail": kind,
                    "status": r.get("status"), "error": r.get("error", "")}
    return out


def _classify(row: dict) -> str:
    status = row.get("status")
    if status is None:
        return "error"
    if status == 200:
        return "http_200_spa" if row.get("spa_suspect") else "http_200"
    if 400 <= int(status) < 500:
        return "http_4xx"
    if 500 <= int(status) < 600:
        return "http_5xx"
    return "unknown"


def score_jurisdiction(jid: str, signals_entry: dict, *, accessibility: float,
                       diversity: float, reuse: float) -> dict:
    comps = {
        "battery_recycling_business_relevance":
            signals_entry["battery_industry"] / 5 * WEIGHTS["battery_recycling_business_relevance"],
        "EV_market_relevance":
            signals_entry["ev_market"] / 5 * WEIGHTS["EV_market_relevance"],
        "recycling_industry_presence":
            signals_entry["recycling_industry"] / 5 * WEIGHTS["recycling_industry_presence"],
        "known_policy_signal":
            signals_entry["policy_signal"] / 5 * WEIGHTS["known_policy_signal"],
        "source_gap_risk": (1.0 - accessibility) * WEIGHTS["source_gap_risk"],
        "official_source_accessibility": accessibility * WEIGHTS["official_source_accessibility"],
        "legal_system_diversity": diversity * WEIGHTS["legal_system_diversity"],
        "existing_connector_reuse": reuse * WEIGHTS["existing_connector_reuse"],
    }
    return {
        "jurisdiction_id": jid,
        "score": round(sum(comps.values()), 4),
        "accessibility": accessibility,
        "policy_signal": signals_entry["policy_signal"],
        "confidence": signals_entry.get("confidence", ""),
        "note": signals_entry.get("note", ""),
        **{k: round(v, 4) for k, v in comps.items()},
    }


def build_scores(signals: dict, probe_rows: list[dict]) -> dict:
    acc = accessibility_from_probe(probe_rows)
    diversity_map = signals.get("diversity_scores") or {}
    rows_ms, rows_us = [], []
    reg = load_registry()
    ms_codes, state_codes = set(), set()
    for j in reg.jurisdictions:
        ms_codes |= {c.get("code") for c in j.countries}
        state_codes |= {s.get("code") for s in j.states}
    for jid, entry in signals["eu_member_states"].items():
        a = acc.get(jid, {"score": ACCESS_SCORE["unknown"]})
        rows_ms.append(score_jurisdiction(
            jid, entry, accessibility=a["score"],
            diversity=(diversity_map.get("EU") or {}).get(jid, 0.5),
            reuse=REUSE_OVERRIDES.get(jid, 0.0)))
    for jid, entry in signals["us_states"].items():
        a = acc.get(jid, {"score": ACCESS_SCORE["unknown"]})
        rows_us.append(score_jurisdiction(
            jid, entry, accessibility=a["score"],
            diversity=(diversity_map.get("US") or {}).get("_default", 0.3),
            reuse=REUSE_OVERRIDES.get(jid, 0.0)))
    rows_ms.sort(key=lambda r: (-r["score"], r["jurisdiction_id"]))
    rows_us.sort(key=lambda r: (-r["score"], r["jurisdiction_id"]))
    return {"EU_MEMBER_STATES": rows_ms, "US_STATES": rows_us,
            "access_details": acc,
            "validated": {"ms": sorted(ms_codes), "states": sorted(state_codes)}}


def select_pilots(scores: dict, *, eu_new: int = 4, eu_stretch: int = 1,
                  us_states: int = 6, access_floor: float = 0.5,
                  min_policy: int = 2, policy_threshold: int = 4) -> dict:
    def split(rows):
        eligible = [r for r in rows if r["accessibility"] >= access_floor]
        low = [r for r in rows if r["accessibility"] < access_floor]
        return eligible, low

    eu_rows = scores["EU_MEMBER_STATES"]
    eu_cand = [r for r in eu_rows
               if r["jurisdiction_id"] not in REFERENCE_JURISDICTIONS]
    eu_elig, eu_low = split(eu_cand)
    eu_primary = eu_elig[:eu_new]
    chosen = {r["jurisdiction_id"] for r in eu_primary}
    rest = [r for r in eu_elig if r["jurisdiction_id"] not in chosen]
    stretch_pool = sorted(rest, key=lambda r: (-_diversity_of(scores, r), r["jurisdiction_id"]))
    eu_str = stretch_pool[:eu_stretch]

    us_rows = scores["US_STATES"]
    us_elig, us_low = split(us_rows)
    us_chosen = us_elig[:us_states]
    # A1 栖息地约束：至少 min_policy 个 policy ≥ threshold
    def policy_count(rows):
        return sum(1 for r in rows if r["policy_signal"] >= policy_threshold)
    if policy_count(us_chosen) < min_policy:
        need = min_policy - policy_count(us_chosen)
        pool = [r for r in us_elig if r not in us_chosen
                and r["policy_signal"] >= policy_threshold]
        for cand in pool[:need]:
            doomed = sorted(us_chosen,
                            key=lambda r: (r["policy_signal"] >= policy_threshold,
                                           r["score"]))[0]
            us_chosen = [r for r in us_chosen if r is not doomed] + [cand]
            us_chosen.sort(key=lambda r: (-r["score"], r["jurisdiction_id"]))

    def brief(rows, reason=""):
        out = []
        for r in rows:
            item = {"jurisdiction_id": r["jurisdiction_id"], "score": r["score"],
                    "accessibility": r["accessibility"],
                    "policy_signal": r["policy_signal"]}
            if reason:
                item["reserve_reason"] = reason
            out.append(item)
        return out

    stretch_ids = {s["jurisdiction_id"] for s in eu_str}
    eu_reserve = [r for r in eu_elig
                  if r["jurisdiction_id"] not in chosen
                  and r["jurisdiction_id"] not in stretch_ids][:4]
    us_reserve = [r for r in us_elig if r not in us_chosen][:4]
    return {
        "EU_new_pilots": brief(eu_primary),
        "EU_stretch_pilots": brief(eu_str),
        "EU_reserve": brief(eu_reserve) + brief(eu_low[:3],
                                                reason="accessibility < floor（需先修复通道）"),
        "US_state_pilots": brief(us_chosen),
        "US_reserve": brief(us_reserve) + brief(us_low[:3],
                                                reason="accessibility < floor（需先修复通道）"),
        "reference_jurisdictions": list(REFERENCE_JURISDICTIONS),
        "constraints": {"access_floor": access_floor,
                        "us_min_policy_states": min_policy,
                        "policy_threshold": policy_threshold},
    }


def _diversity_of(scores: dict, row: dict) -> float:
    return row.get("legal_system_diversity", 0.0) / WEIGHTS["legal_system_diversity"]
