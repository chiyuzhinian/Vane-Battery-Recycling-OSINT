# -*- coding: utf-8 -*-
"""batch1r_recovery_decisions.py —— Phase 4B-2B Batch 1R §A4 + Track B MODE A 日志。

产物：
  outputs/audit/batch1_channel_recovery.json   （7 个原 blocked 的恢复决策）
  outputs/audit/batch1r_mode_a_log.json        （CONNECTED 辖区 MODE A 启动记录）

数据来源：network_vantage_matrix（两轮复测）+ 本轮恢复动作实证
（AT OGD 路由、GA/CO 复测、HU gazette 路由、GA epd 4 样本等，见 Batch 1R 报告）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

AUDIT = ROOT / "outputs" / "audit"

# A4：7 个原 blocked jurisdiction 的恢复决策（实证结论）
RECOVERY = [
    {
        "jurisdiction": "AT", "source_role": "MS_LEGISLATION_DATABASE",
        "main_endpoint": "https://www.ris.bka.gv.at/Bundesrecht/",
        "current_runner_result": "ACCESS_CONTROLLED / HTTP_5XX_CHALLENGE（503，curl 同）",
        "second_runner_result": "无云 Runner；浏览器未测（主域）",
        "official_alternative_routes": [
            {"route": "RIS OGD API（官方开放数据）",
             "endpoint": "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht?Applikation=BrKons&Suchworte=*",
             "verified": "200（两轮稳定，返回 JSON 含文档直链）"},
            {"route": "RIS OGD 文档（官方）",
             "endpoint": "https://ogd.ris.bka.gv.at/Dokumente/Bundesnormen/NOR12151966/NOR12151966.html",
             "verified": "200（46KB HTML；XML 亦 200）"},
        ],
        "final_access_classification": "ACCESS_CONTROLLED（main）/ OFFICIAL_ALT_OK",
        "recommended_execution_route": "official OGD API（data.bka 检索 → ogd.bka 文档）",
        "remaining_blocker": "无（已恢复 CONNECTED：2 真实文档样本）",
    },
    {
        "jurisdiction": "HU", "source_role": "MS_LEGISLATION_DATABASE",
        "main_endpoint": "https://njt.hu/",
        "current_runner_result": "CURRENT_RUNNER_BLOCKED / HTTP_NO_RESPONSE（RemoteProtocolError + curl reset）",
        "second_runner_result": "无云 Runner",
        "official_alternative_routes": [
            {"route": "Magyar Közlöny（官方公报）",
             "endpoint": "https://magyarkozlony.hu/",
             "verified": "200（两轮稳定）"},
        ],
        "final_access_classification": "CURRENT_RUNNER_BLOCKED（official gazette 可达）",
        "recommended_execution_route": "official gazette（magyarkozlony.hu）",
        "remaining_blocker": "公报文档 URL 枚举（MODE A 任务；站点检索路径未公开）",
    },
    {
        "jurisdiction": "BE", "source_role": "MS_LEGISLATION_DATABASE",
        "main_endpoint": "https://www.ejustice.just.fgov.be/cgi_loi/loi_a.pl",
        "current_runner_result": "CURRENT_RUNNER_BLOCKED / CONNECT_TIMEOUT（两轮一致）",
        "second_runner_result": "无云 Runner（ssh 模板为空，无云凭据）",
        "official_alternative_routes": [
            {"route": "http 变体", "endpoint": "http://www.ejustice.just.fgov.be/",
             "verified": "未测（同出口）"},
        ],
        "final_access_classification": "CURRENT_RUNNER_BLOCKED（awaiting_independent_runner）",
        "recommended_execution_route": "cloud runner（待用户配置授权云主机）",
        "remaining_blocker": "网络出口层（非源问题：域可达性无法从本出口判定）",
    },
    {
        "jurisdiction": "US-MI", "source_role": "STATE_LEGISLATURE / STATE_ENVIRONMENT",
        "main_endpoint": "https://www.legislature.mi.gov/ + https://www.michigan.gov/egle",
        "current_runner_result": "CURRENT_RUNNER_BLOCKED / HTTP_NO_RESPONSE（legislature）；ACCESS_CONTROLLED / HTTP_403（EGLE，域级）",
        "second_runner_result": "无云 Runner",
        "official_alternative_routes": [],
        "final_access_classification": "CURRENT_RUNNER_BLOCKED + ACCESS_CONTROLLED",
        "recommended_execution_route": "cloud runner + browser channel（EGLE 403 需浏览器验证）",
        "remaining_blocker": "出口层 + EGLE 403 控制壳",
    },
    {
        "jurisdiction": "US-GA", "source_role": "STATE_ENVIRONMENT",
        "main_endpoint": "https://epd.georgia.gov/",
        "current_runner_result": "SOURCE_AVAILABLE / HTTP_200_OK（复测翻转；原 DNS_RESOLVE_FAIL 为 runner 瞬态）",
        "second_runner_result": "无云 Runner（不需要：本机已可达）",
        "official_alternative_routes": [],
        "final_access_classification": "RECOVERED（SOURCE_AVAILABLE）",
        "recommended_execution_route": "local runner（runner_id=runner-local-dev-1）",
        "remaining_blocker": "无（已恢复 CONNECTED：EPD 4 真实样本）",
    },
    {
        "jurisdiction": "US-OH", "source_role": "STATE_STATUTES",
        "main_endpoint": "https://codes.ohio.gov/ + https://www.legislature.ohio.gov/",
        "current_runner_result": "CURRENT_RUNNER_BLOCKED / CONNECT_TIMEOUT；alt 轮 DNS_ERROR",
        "second_runner_result": "无云 Runner",
        "official_alternative_routes": [],
        "final_access_classification": "CURRENT_RUNNER_BLOCKED（awaiting_independent_runner）",
        "recommended_execution_route": "cloud runner（待配置）",
        "remaining_blocker": "网络出口层（两轮一致 timeout/解析失败）",
    },
    {
        "jurisdiction": "US-CO", "source_role": "STATE_ENVIRONMENT",
        "main_endpoint": "https://cdphe.colorado.gov/",
        "current_runner_result": "SOURCE_AVAILABLE / HTTP_200_OK（主页复测 200；子路径间歇 403）",
        "second_runner_result": "browser channel 验证可达（cdphe 主页正常渲染；console 部分资源 ERR_CONNECTION_CLOSED——同出口栈）",
        "official_alternative_routes": [
            {"route": "colorado.gov 主域", "endpoint": "https://colorado.gov/",
             "verified": "200"},
        ],
        "final_access_classification": "RECOVERED（SOURCE_AVAILABLE；browser 回退保留）",
        "recommended_execution_route": "local（+browser fallback for 子路径）",
        "remaining_blocker": "无（已恢复 CONNECTED：cdphe 1 真实样本；深层文档待枚举）",
    },
]

# Track B：CONNECTED 辖区 MODE A（DISCOVERY_EXPANSION）启动记录
MODE_A = [
    {"jurisdiction": "IT", "roles": ["MS_LEGISLATION_DATABASE"],
     "endpoints": ["normattiva.it（搜索 + urn:nir URN 直链）"],
     "native_keywords": ["batterie", "accumulatori", "rifiuti"],
     "enumeration": "固定 URN/nir 直链枚举（搜索页 SPA 限制记录在案）",
     "samples_ok": 3, "status": "IN_PROGRESS"},
    {"jurisdiction": "SK", "roles": ["MS_LEGISLATION_DATABASE"],
     "endpoints": ["slov-lex.sk（predpisy 直链）"],
     "native_keywords": ["batéria", "akumulátor", "odpad"],
     "enumeration": "Slov-Lex 直链（ZZ/{year}/{num}）枚举",
     "samples_ok": 2, "status": "IN_PROGRESS"},
    {"jurisdiction": "CZ", "roles": ["MS_LEGISLATION_DATABASE"],
     "endpoints": ["psp.cz/sbirka.sqw（参数枚举）"],
     "native_keywords": ["baterie", "akumulátor", "odpad"],
     "enumeration": "sbirka.sqw?cz=&r= 参数枚举",
     "samples_ok": 2, "status": "IN_PROGRESS"},
    {"jurisdiction": "AT", "roles": ["MS_LEGISLATION_DATABASE"],
     "endpoints": ["data.bka.gv.at OGD API（分页检索）", "ogd.bka.gv.at 文档"],
     "native_keywords": ["Batterie", "Altbatterie", "Abfallwirtschaft"],
     "enumeration": "OGD API Suchworte 分页 + 文档 URL 直取（Batch 1R 新增通道）",
     "samples_ok": 2, "status": "NEWLY_CONNECTED（1R）"},
    {"jurisdiction": "US-GA", "roles": ["STATE_ENVIRONMENT"],
     "endpoints": ["epd.georgia.gov（Land Protection / Hazardous Waste）"],
     "native_keywords": ["battery", "hazardous waste", "solid waste"],
     "enumeration": "EPD 站内主题页枚举",
     "samples_ok": 4, "status": "NEWLY_CONNECTED（1R）"},
    {"jurisdiction": "US-CO", "roles": ["STATE_ENVIRONMENT"],
     "endpoints": ["cdphe.colorado.gov（+ browser fallback）"],
     "native_keywords": ["battery", "hazardous", "recycling"],
     "enumeration": "CDPHE 站内页枚举（子路径 403 → 浏览器回退）",
     "samples_ok": 1, "status": "NEWLY_CONNECTED（1R）"},
    {"jurisdiction": "US-IL", "roles": ["STATE_ENVIRONMENT"],
     "endpoints": ["epa.illinois.gov（waste-management）"],
     "native_keywords": ["battery", "recycling", "waste"],
     "enumeration": "IL EPA 主题页枚举",
     "samples_ok": 1, "status": "IN_PROGRESS"},
    {"jurisdiction": "US-TN", "roles": ["STATE_ENVIRONMENT"],
     "endpoints": ["tn.gov/environment（TDEC）"],
     "native_keywords": ["battery", "solid waste"],
     "enumeration": "TDEC 站内页枚举",
     "samples_ok": 1, "status": "IN_PROGRESS"},
    {"jurisdiction": "US-TX", "roles": ["STATE_STATUTES"],
     "endpoints": ["statutes.capitol.texas.gov（Docs/HS 直链）"],
     "native_keywords": ["battery", "hazardous", "solid waste"],
     "enumeration": "Texas HSC 章节（HS.xxx.htm）枚举",
     "samples_ok": 2, "status": "IN_PROGRESS"},
    {"jurisdiction": "US-NV", "roles": ["STATE_ENVIRONMENT"],
     "endpoints": ["ndep.nv.gov"],
     "native_keywords": ["battery", "waste"],
     "enumeration": "NDEP 站内页枚举（NRS 403 记录在案）",
     "samples_ok": 3, "status": "IN_PROGRESS"},
]


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n_blk = len(RECOVERY)
    # recovered：直接复测可用（RECOVERED）或经官方替代路由恢复（OFFICIAL_ALT_OK）
    recovered = [r for r in RECOVERY
                 if "RECOVERED" in r["final_access_classification"]
                 or "OFFICIAL_ALT_OK" in r["final_access_classification"]]
    # 官方替代路由可达：仅统计 **已验证** 的（未测/同出口变体不计）
    alt_route = [r for r in RECOVERY
                 if any(isinstance(a, dict) and a.get("verified")
                        and not str(a["verified"]).startswith("未测")
                        for a in (r.get("official_alternative_routes") or []))]
    still = [r for r in RECOVERY if r not in recovered]
    payload = {
        "generated_at": now,
        "originally_blocked": n_blk,
        "recovered_count": len(recovered),
        "recovered_via_rerun_or_alt_route": [r["jurisdiction"]
                                              for r in recovered],
        "official_alt_route_available": [r["jurisdiction"]
                                         for r in alt_route],
        "still_blocked_count": len(still),
        "still_blocked": [r["jurisdiction"] for r in still],
        "runner_note": ("Runner B（独立云环境）当前不可用（无云凭据，ssh 模板为空）"
                        "——仍在待配置状态；所有 CURRENT_RUNNER_BLOCKED 均标记"
                        " awaiting_independent_runner=true，不得上升为 SOURCE_FAILURE。"),
        "decisions": RECOVERY,
    }
    (AUDIT / "batch1_channel_recovery.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT / "batch1r_mode_a_log.json").write_text(
        json.dumps({"generated_at": now, "track": "B/MODE A（DISCOVERY_EXPANSION）",
                    "note": "MODE B 未进入（PLAN_V1 待 MODE A 稳定后生成）",
                    "jurisdictions": MODE_A},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"recovered: {payload['recovered_via_rerun_or_alt_route']}")
    print(f"official_alt_route: {payload['official_alt_route_available']}")
    print(f"still_blocked: {payload['still_blocked']}")
    print("→ batch1_channel_recovery.json / batch1r_mode_a_log.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
