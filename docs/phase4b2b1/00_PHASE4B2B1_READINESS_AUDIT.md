# Phase 4B-2B1 — Readiness Audit（Plan Mode）

> 生成时间：2026-09-14 ｜ 基线提交：`51c55c5`（phase4b2a）｜ 语料 3318 条
> 口径：**guarded 现算**（`classify_record` + `guarded_effective_class`，排除非政策源）为主；
> 与旧 `meta.acceptance_class`（overlay）对照时另行标注。

---

## 0. 审计范围

读入检查：`app/policy/{domain_scope,acceptance,jurisdiction*,saturation,legal_identity}.py`、
`scripts/audit_{topic_mapping_consistency,jurisdiction_coverage,jurisdiction_convergence}.py`、
`sources/{jurisdiction-onboarding,search-plans,policy-goldset.yaml}`、`outputs/audit/`。
实测探测：CO/GA/EE/BE 通道（2026-09-14）。

**guarded 口径分布**（corpus 排除 `eu_nim_` 与企线）：

| | A1 | A2 | B | C | D |
|---|---|---|---|---|---|
| corpus | 1 | 79 | 120 | 120 | 1593 |
| NIM | 0 | **227** | 0 | 148 | 0 |

---

## 1. Q1 — OUT_OF_SCOPE + B 为什么允许存在？

**代码**：`domain_scope.py::guard_class`（L124-133）——
`"OUT_OF_SCOPE": return "D" if acceptance_class in ("A1","A2") else acceptance_class`。
注释写明"不降 B —— eCFR 危废/危货文书标题无电池词……不得误伤"。

**量化（终态一致性检查）**：guarded 口径 **OUT_OF_SCOPE + B = 87 条**（overlay 口径 30 条）。
来源：us_federal_register 57 ｜ us_ecfr 10 ｜ browser_france 6 ｜ fr_ademe 6 ｜ us_wa_ecology 3 ｜ us_wa_rcw 2 ｜ nl_bwb 2 ｜ es_boe 1。

**构成分组**：
- **真支撑（~70 条，域词表缺词误判）**：49 CFR 危货族（171/172/173，25 条）；40 CFR RCRA（260/261）；联邦公报的州危废授权族（Texas/Utah/Alabama/Wyoming/Montana/…约 20 条）、Hazardous Materials 系列（Harmonization/FAST Act/e-Manifest/LDR/PFAS-listing）、清洁车辆抵免转移（4 条，用户判例 B）、FR REP-VHU 数据集（12 条：Tonnages/TRR/TRV/SYDEREP）、NL autowrakken、ES RD 846/2011（VFU）。
- **真无关（~10 条，历史 B 误判）**：40 CFR 1031/1036/1037/1039/1054（发动机排放）、Stratospheric Ozone substitutes、Phosphogypsum。
- **州/地方**：WA Ecology 3 条（Waste&Toxics）、WA RCW 2 条——SUPPORTING 误判为 OUT。

**根因**：① 域词表未覆盖 hazmat/RCRA/ELV 多语术语（VHU、autowrak、VFU）；② 当时用"B 例外"回避降级，而不是把域分类修对——**语义矛盾被固化**。

**修复方向（编码）**：
1. `sources/domain-scope-rules.yaml` 增词：`supporting_markers` += `hazardous materials|49 cfr|rcra|40 cfr 26x|e-manifest|land disposal|hazardous waste generator|clean vehicle credit|45x|advanced manufacturing`（真支撑归位）；`horizontal_applies_to_ev` += `vhu|autowrak|end-of-life vehicle.*(treatment|dismantl)|vfu`（ELV 体系归位）；`out_of_scope_markers` 保持排放类词。
2. `guard_class`：**OUT_OF_SCOPE + B → D**（恢复严格语义；"误伤"问题由词表解决）。
3. 新审计 `scripts/audit_domain_acceptance_consistency.py` → `domain_acceptance_mismatches.json`；目标 **=0**。
4. **兼容**：goldset 评估走 `classify_record`（无护栏）→ `hard_b_*` 断言不受影响；但
   `tests/phase4b2b0/test_domain_scope_guard.py` L52-53（`guard_class("B","OUT_OF_SCOPE")=="B"`）
   需按新语义更新为 `"D"`。

---

## 2. Q2 — NIM 是否仅影响 Discovery？**否，已影响最终 Acceptance**

**代码证据**（`acceptance.py`）：
- L203：`system_anchor` 包含 `source_id.startswith("eu_nim_")` —— NIM 自动获体系锚点；
- L230-235：**5b 特例**——`eu_nim_*` 且 `record.relevant` → 直接返回 **A2**（不要求主题/条款）。
- `domain_scope.py` L143：NIM 豁免 OUT_OF_SCOPE 惩罚。

**量化**：NIM 375 条 → 现算 A2 **227 条**（+C 148）。corpus 矩阵虽已排除 NIM
（`jurisdiction_coverage._is_corpus_strong`），但 acceptance 字段/审计/报告仍被 A2 污染；
且"域豁免"允许 NIM 绕过 Domain Scope。

**修复方向（编码）**：
1. 删除 5b 特例；`system_anchor` 移除 `eu_nim_` 前缀项；`guarded_effective_class` 移除域豁免。
2. NIM 记录正路判定 → 最多 **C**（索引）＋ `discovery_layer=True` 标记（供 coverage/identity/topic 口径统一）。
3. "母语文档不得误杀"改由真实 national 通道承接（这正是 role closure 的意义，而非 NIM 假升）。
4. 新测试 `test_nim_discovery_only.py`：NIM + relevant + 无主题文本 → **不得** A1/A2/B；NIM 受域护栏。
5. **兼容面**：`tests/policy/test_acceptance.py::test_native_language_not_killed`（L76 断言 A2）
   改写；`test_domain_scope_guard.py::test_nim_out_of_scope_exempt_*` 改写为"NIM 不豁免"。
6. 影响评估：NIM A2→C 后，EU NIM 覆盖相关计数（A2 计数）下降——**符合语义**；
   `legal_identity`/`instrument` 的 NIM 特判保留（身份层独立）。

---

## 3. Q3 — A1/A2/B 中多少没有 fulltext？

**corpus 口径（排除 NIM）**：

| 类 | 总数 | 全文（≥600 字符） | % |
|---|---|---|---|
| A1 | 1 | 1 | **100.0%** |
| A2 | 79 | 9 | **11.4%** |
| B | 120 | 104 | **86.7%** |

**A2 缺口主体 = EU 占位**：`eu_eurlex_battery_reg` 142 条中 132 条 <600 字符：
- `eu_32023R1542` 主占位（111 字符）＝ 已有 `eu_fulltext_32023R1542`（351K）可回填；
- **Corrigendum 系列** `32023R1542R(01)–R(13)+`（116 字符 × 多条）＋其它 CELEX 占位
  （keyword 检索 4 条：`eu_eurlex_keyword`）。
**B 缺口 16 条**：`int_basel` 8 条（技术指南索引）、`eu_eurlex_keyword` 4、`us_federal_register` 3、`browser_france` 1、其余零散。

**修复方向**：① 已有 `sources/eurlex-fulltext/*.txt` 8 部对 `eu_{celex}` 占位做回填；
② Corrigendum 短文书批量抓（EUR-Lex HTML 存在）；③ Basel 技术指南页真抓（int_basel 通道）；
④ 目标 A1/A2/B ≥95%。

---

## 4. Q4 — B 中多少没有 clause evidence？

- **overlay B 50 条：0 条持久化 `evidence_quotes`**（旧语料生成时无该字段落盘）。
- 现算 B：`classify_record` 要求 `scan_topics` 的 quotes 非空（`B_CLAUSE_EVIDENCE`），
  但 quotes **仅存在于分类返回值，未落盘**；其中 21 条 B 文本 <600 字符（引句质量可疑）。

**修复方向**：content_completeness 审计为每条 B 计算：
`clause_evidence_available = (现算 quotes 非空 ∧ 文本 ≥600 ∧ quote 非纯标题回声)`；
不满足 → `B_CANDIDATE`（overlay 标注，不修改 raw）；目标 ≥95%、最终 100%。
新增 `test_b_requires_clause_evidence.py`。

---

## 5. Q5 — US-CA 缺什么才能 eligible？

- 覆盖 5/8；**缺 3 角色**：`STATE_ADMIN_CODE`（CCR 未接入）、`STATE_REGISTER`（公报未接入）、`STATE_TRANSPORT_HAZMAT`（Caltrans 未接入）。
- routes = A,C → **缺第 3 类**（禁止 leginfo 换词充数）。
- 已知可用证据（2B0 探测留档）：**Caltrans 200/42KB 已实测可达**（当时未接）；
  OAL/CCR 403（此网络环境）。
- 修复方向（编码实证）：
  1. **Caltrans connector**（真实样本：hazmat 运输规则/危险品路线页）→ `STATE_TRANSPORT_HAZMAT` → **6/8**；
  2. `STATE_ADMIN_CODE` 候选：DTSC 官站（dtsc.ca.gov，危废主管，站上有 Law & Regulations/CCR 条文）+ 重探 OAL；
  3. routes：新增 **D（CCR 章节号段缺口枚举）** 或 A 扩展（Caltrans 手册章节）→ `US_CA_PLAN_V2`（hash reset）；
  4. 之后 MODE B 三轮验证 → 目标 eligible。

---

## 6. Q6 — SE 缺什么才能 eligible？

- 覆盖 3/7；**缺 4 角色**：`MS_WASTE_REGULATOR`、`MS_TRANSPORT_OR_DANGEROUS_GOODS`、
  `MS_CUSTOMS_OR_TRADE`、`MS_STANDARDS_METADATA`。
- routes = B,C → **缺 A（官方枚举）**。
- 修复方向（编码实证）：
  1. `MS_TRANSPORT_OR_DANGEROUS_GOODS` → **Transportstyrelsen**（transportstyrelsen.se，官方，静态概率高）；
  2. `MS_CUSTOMS_OR_TRADE` → **Tullverket**（tullverket.se）；
  3. `MS_WASTE_REGULATOR` → NV 升级（客户端渲染问题→找官方文档端点）或 Länsstyrelsen；
  4. `MS_STANDARDS_METADATA` → SIS metadata 页（metadata-only 口径）；
  5. A 路线：SFST 官方枚举（rkrattsbaser 按年 SFS 目录）→ `SE_PLAN_V2`（reset）；
  6. 补 ≥2 角色 + A → 5/7 + routes A,B,C → 目标 eligible。FI（缺 5）保持备选。

---

## 7. Q7 — 哪两个受阻通道最容易真实适配？

**今日实测**（UA 浏览器头，follow_redirects）：

| 通道 | 探测结果 | 判定 |
|---|---|---|
| **US-CO** | `leg.colorado.gov/laws/colorado-revised-statutes` → **200/40KB**（sos.state.co.us CCR 仍 403） | **最容易**——CRS 条目真实可采；定位条文体 URL 模式即连 |
| **US-GA** | `epd.georgia.gov` → **200/139KB**（rules.sos.ga.gov 仍 403） | **次之**——EPD 官方环保机构站可达（Solid/Hazardous Waste 页）；官方替代入口 |
| EE | 全路径通配 **51763B SPA 壳**（含 /akt/{id}.xml），Angular 壳（main.*.js） | 中——需浏览器 XHR 侦察后端 API；备选 Keskkonnaamet |
| BE | ejustice 全路径同障（4B-2B0 实测） | 低——当前环境无解 |

**结论**：优先 **CO → GA**（两者均有当日 200 实证），EE 第三（依赖 XHR 侦察），
BE 维持 BLOCKED_SITE_LEVEL。与规格建议序（CO→EE→GA→BE）的偏差以**实测证据**为准。
纪律重申：**adapted = 官方通道 + 真实样本 + 可重复采集**，URL 能开 ≠ adapted。

---

## 8. Q8 — FR identity 73.3% 缺失原因

- 缺失 4 条（15 中）：全部 `fr_dila` 的 **LEGI 快照**（Code de l'environnement ×2、
  Code général des impôts、Code de la sécurité intérieure）。
- **逐条证据**：`meta.legi_file` 路径均含官方编号——
  `LEGITEXT000006074220`（环境法典）、`LEGITEXT000006069577`（税法）、
  `LEGITEXT000025503132` + `LEGIARTI000037017856`（内安法条文）。
- **根因 = PARSER_MISSING**（v2 builder 的 fr_dila 分支未解析 `legi_file` 路径；
  对"整法典/条文快照"没有 article 编号可提——但其实**有** LEGITEXT/LEGIARTI）。
- **修复**：`identity_hardening.build_identity_v2` 的 fr_dila 分支提取
  `LEGITEXT\d+` / `LEGIARTI\d+`（官方编号，非伪造）→ canonical `FR:LEGI:{id}`；
  预计 4/4 修复 → **FR 100%**。兜底 `OFFICIAL_IDENTIFIER_UNAVAILABLE + reason`（本批不需要）。

---

## 9. 附带审计发现（供编码排期）

1. **Black Mass 州/联邦边界**：transboundary/customs 州级=0（天然联邦权限）——
   编码时标注 `NOT_APPLICABLE_STATE_LEVEL`，不计入 MISSING。
2. **Saturation preconditions**：现 `near_saturated=False` 正确；2B1 新增
   `EVIDENCE_COMPLETENESS_GATE` 与 `DOMAIN_CONSISTENCY_GATE` 作为 precondition（不重编号 SG1–SG9）。
3. **B 类安全阀**：`acceptance.py` B 判定已要求 quotes（好），但 quotes 未落盘、
   且未见 `B_CANDIDATE` 状态——统一由 content_completeness 输出。
4. **测试影响清单**（预计改动）：
   `test_domain_scope_guard.py`（B 降级断言）、`test_general_battery_not_core.py`（OOS 违规断言核对）、
   `test_acceptance.py::test_native_language_not_killed`（NIM 不再 A2）。

---

## 10. 审计结论 → 编码顺序

| # | 任务 | 依赖 |
|---|---|---|
| 1 | P0 Domain 语义：词表归位 + `guard_class` 收紧 + consistency audit + 测试 4 件 | 无 |
| 2 | P0 NIM 仅 Discovery：删 5b/锚点/豁免 + `test_nim_discovery_only.py` | 1 |
| 3 | P0 Evidence Completeness：content_state 模型 + `content_completeness.json` + B_CANDIDATE + 测试 | 1,2 |
| 4 | P0 Content backfill：EU 占位回填 + Corrigendum 抓取 + Basel；A1/A2/B ≥95% | 3 |
| 5 | P0 US-CA closure：Caltrans + DTSC/ADMIN_CODE 探测 + D route → US_CA_PLAN_V2 → MODE B | 1 |
| 6 | P0 SE closure：Transportstyrelsen/Tullverket + A route → SE_PLAN_V2 → MODE B | 1 |
| 7 | P0 Channels：CO connector + GA EPD connector（EE 视 XHR 侦察）→ ≥5/7 | 1 |
| 8 | P1 FR identity parser 修复 → 100% | 无 |
| 9 | P1 A1 goldset 继续（不降阈值）；topic 高价值回填；黑粉 NOT_APPLICABLE_STATE_LEVEL | 3,4 |
| 10 | Saturation preconditions + 全量测试 + 报告/终端摘要 | 全部 |

**Gate 复算预期**（如全部落地）：eligible 3（WA/CA/SE）｜ 通道 5–6/7 ｜
A1/A2/B 全文 ≥95% ｜ B clause ≥95% ｜ Domain 矛盾 =0 ｜ A1 仍如实（1–2 案例）。
