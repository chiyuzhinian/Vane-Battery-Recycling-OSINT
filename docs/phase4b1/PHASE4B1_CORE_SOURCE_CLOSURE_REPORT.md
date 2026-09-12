# Phase 4B-1 — Core Source Closure & Legal Identity Hardening · 验收报告

> 阶段：**Phase 4B-1**（正式）｜ 基线：Phase 4A 交付 `1d0e69d`（EU=WEAK 4/9、US=WEAK 3/9）
> 执行日：2026-09-12 ｜ 模式：Plan → Step 1–10 步进（每步独立提交、独立测试、独立真实运行）
> 纪律：未重写 Phase 4A 架构（relevance / review overlay / feedback / raw evidence / collectors / saturation 框架）；
> 未降低阈值；未人工凑 A1 样本；HTTP 403/500 ≠ paywalled；单端点失败 ≠ 判死角色；EU 官方引用 ≠ 标准库接入；
> binding force 由人工/规则证据决定，AI 不单独裁定。

---

## 1. Executive Summary

**结论：CONDITIONAL PASS（部分目标达成，其余如实记为 PARTIAL / INSUFFICIENT）。**

| P0 目标（规格 §18） | 结果 | 状态 |
|---|---|---|
| P0-1 Source Role Gap Matrix（runtime 推导） | 106 行矩阵 + 端点探测（45 端点）可复现 | ✅ COMPLETE |
| P0-2 US Federal 源闭包 | critical **9/9 (100%)**、mandatory **12/12 (100%)** | ✅ COMPLETE |
| P0-3 EU 跨境/标准闭包 | critical 6/8 (75%)、mandatory 7/9 (77.8%)；STANDARDS/OECD 到达口径上限 | ⚠️ PARTIAL |
| P0-4 | Legal Identity Hardening | EU 74.3%→**85.8%**（目标 ≥95% ✗）；US 10.2%→**59.2%**（FR 语料子集 12.5%→**82.5%**，目标 ≥90% ✗） | ⚠️ PARTIAL |
| P0-5 instrument_type 精度 | 0.786 → **1.0（14/14）**（目标 ≥0.95） | ✅ COMPLETE |
| P0-6 A1 Gold Set 补齐 | **a1_verified_count = 0 → INSUFFICIENT_A1_GOLDSET**（绝不人工凑样）；新增 2 个 hard B | ⚠️ INSUFFICIENT（如实） |
| P0-7 Legal Family P0 缺口 | **P0 unresolved = 0**（4 root 完整度全 1.0，官方 Cellar 关系） | ✅ COMPLETE |
| P0-8 LIVE Discovery Rounds ×3（≥3 类独立路线） | **4 类路线 × 6 轮**（US 3 + EU 3）真实执行、真实落盘；**未收敛**（如实） | ⚠️ 执行完成 / 未收敛 |

**Saturation（四 scope 独立）**：EU_SUPRANATIONAL **PARTIAL 6/9** ｜ EU_MEMBER_STATES **PARTIAL 6/9** ｜
US_FEDERAL **PARTIAL 7/9** ｜ US_STATES **PARTIAL 6/9** —— **无任何 scope 达 SATURATED**。

**黑粉六线**：全球 **6/6 COVERED**；EU 5 COVERED + 1 PARTIAL（危废定性）；US 6/6 COVERED。

**Headline**：US 联邦体系已闭合（法典/公报/裁定/指令/标准元数据五层）；EU 超国家层到口径上限（标准层为官方引用而非标准库）；
A1 真实栖息地确认为「EU 成员国 + US 州级」深度层 —— 这是 Phase 4B-2 的直接输入。

---

## 2. Source Universe Before → After

### 2.1 Source Role Gap Matrix（runtime 推导，`outputs/audit/source_role_gap_matrix.json`）

| Scope | 指标 | Step 1 探测后（Before） | 本阶段结束（After） |
|---|---|---|---|
| EU_SUPRANATIONAL | mandatory | 4/9 (44.4%) | **7/9 (77.8%)** |
| EU_SUPRANATIONAL | critical | 4/8 (50.0%) | **6/8 (75.0%)** |
| US_FEDERAL | mandatory | 9/12 (75.0%) | **12/12 (100%)** |
| US_FEDERAL | critical | 6/9 (66.7%) | **9/9 (100%)** |
| EU_MEMBER_STATES | core | 4/27 (14.8%) | 4/27 (14.8%)（4B-2 范围） |
| US_STATES | core | 0/51 (0%) | 0/51 (0%)（4B-2 范围） |

> critical_blocked_roles = **0**（无任何 critical 角色被判死）；残余 blocked 均为 **端点级**（OECD 主站 403、ECHA 403、
> Legifrance CAPTCHA、ISO CAPTCHA、congress API_KEY、CalRecycle CAPTCHA 等）——角色按「实际可用的替代通道」评定。

### 2.2 端点探测（45 端点 → `source_probe_results.json`）

ACCESSIBLE 36 ｜ PARTIAL 1 ｜ BLOCKED 8。失败分类采用 17+1 taxonomy：
`NO_RESULTS ≠ SOURCE_FAILURE`；`HTTP 403/500 ≠ paywalled_known`；SPA 端点单独记 `SPA_JS_RENDERED`。

### 2.3 源别名对账（逻辑源名 → 真实 source_id）

| 逻辑源 | Before | After |
|---|---|---|
| EURLEX_NIM | 0 | **396** |
| CUSTOMS_TRADE | 0 | **586** |
| MEMBER_STATE_LEG | 134 | **530** |

### 2.4 语料总量

全库 **6,892** 条（FR 3,409 ｜ EUR-Lex battery_reg 541 ｜ EUR-Lex keyword 132 ｜ NIM 27 国全部有记录 ｜ NIM-CZ 39 等）
＋本轮 LIVE 轮次新增落盘 **52** 条（US 30 = 25+1+4；EU 22 = 19+0+3）。

---

## 3. New Source Connectors（官方源 · 获取方式 · 样本量 · 失败模式）

| Connector | 官方源 / 域名 | 获取方式 | 样本 | 失败模式（已处理） | 状态 |
|---|---|---|---|---|---|
| `app/connectors/ecfr.py` | ecfr.gov（官方 API，无 Key） | `versioner/v1/titles.json` + `search/v1/results` + `full/{date}/title-N.xml` | **20 个 Part 验证入库** | ① 请求日期 > title 最新发布日期 → 404 → 新增 `latest_issue_date()`；② 无 `Accept` 头 406 → 已明确 | ✅ ACCESSIBLE |
| `app/connectors/govinfo.py`（USC） | uscode.house.gov 超时 → 改走 govinfo | `wssearch/rb/uscode` 枚举 + `content/pkg/USCODE-*` 正文 | **2 个 Title/Chapter（116+47 段）** | ① uscode.house.gov TIMEOUT（记 SOURCE_FAILURE 并换官方替代通道）；② govinfo 伪 404（200 + "Page Not Found"）显式识别 | ✅ ACCESSIBLE |
| `app/connectors/govinfo.py`（PLAW） | govinfo | `content/pkg/PLAW-*` + 官方边缘注记解析 | **2 部（PL 117-58 IIJA / PL 117-169 IRA）** | bulkdata 目录为 SPA 外壳 → 改走已知路径 | ✅ ACCESSIBLE |
| `app/connectors/cbp_cross.py` | rulings.cbp.gov（CBP CROSS） | `/api/search?term=…`（官方 JSON） | **10 条裁定**（+12 条 FR CBP/BIS 机构文书） | 模糊检索含无关主题 → 主题过滤 | ✅ ACCESSIBLE |
| Basel（`crossborder.py`） | basel.int | HTML 页 + PDF 直链 | **3 条（+轮次新增 8 条）** | 部分路径 SPA；PDF 解析有限 | ✅ ACCESSIBLE（文本级） |
| OECD（`crossborder.py`） | legalinstruments.oecd.org | 子域可 200，但**实测 JS 渲染** | 0（不可抽取） | `SPA_JS_RENDERED` → 角色 **PARTIAL**（不判死：主站 403 仅记端点级） | ⚠️ PARTIAL（口径上限） |
| Standards（`crossborder.py`） | CEN 门户（500/SPA）、ISO（403 CAPTCHA） | **metadata-only + EU 官方引用路径** | 2 条元数据 | 五概念分离：`metadata_available=true` / `fulltext_available=false` / `open_access_status` / `metadata_source_type=EU_OFFICIAL_REFERENCE` / `endpoint_status` | ⚠️ **ceiling=PARTIAL**（规则锁定：官方引用 ≠ 标准库接入） |
| FR 身份通道（`identity_us.py`） | federalregister.gov | `/api/v1/documents/{id}.json` | **120 条富化**（overlay 累计 135 文档） | 无（0 failed） | ✅ ACCESSIBLE |

---

## 4. Legal Identity Before / After

| 指标 | Before | After | 目标 | 状态 |
|---|---|---|---|---|
| US FR 语料子集完整度 | 12.5% | **82.5%**（Δ+70.0%） | ≥90% | ⚠️ 未达 |
| US_FEDERAL 全体（含 CBP/CFR/USC 文档） | 10.2%（Phase 4A 口径） | **59.2%** | ≥90% | ⚠️ 未达（未富化类文档暂无 celex 等价键） |
| EU_SUPRANATIONAL | 74.3%（Phase 4A 口径） | **85.8%** | ≥95% | ⚠️ 未达（改善来自家族成员 CELEX 回采 + 轮次新增文档） |

机制：**overlay 增量合并**（原始 evidence 零改动）→ `citation / RIN / docket / cfr_references / type / effective_on`
（FR 官方元数据）；ambiguous = 0；needs_human_review = 4；Rule→administrative_rule、Proposed Rule→proposal；
Notice 等宽泛类型不猜（交由 Step 8 metadata-first 判定）。

---

## 5. FR → CFR → USC 真实关系链（`fr_cfr_links.json` / `us_legal_links.json`）

| 关系 | 链接数 | 说明 |
|---|---|---|
| FR → CFR（codified_in） | **184 条** / 67 个唯一 Part | 其中 **34 条命中 20 个经 eCFR 官方验证的 Part**（matched 18.5%；未匹配的 Part 尚未纳入采集清单） |
| CFR → USC（AUTHORIZED_BY） | **33 条** | 来源：eCFR `<AUTH>` 权威注记（官方正文授权条款），如 `CFR:49:171 → USC:49:5101` |
| PL → USC（AMENDS） | **80 条** | 来源：govinfo 官方边缘注记（`NOTE: NN USC sss`），如 `PL:117-58（IIJA）→ USC:23:101` 等 |

**真实案例（电池链条）**：`PL 117-58（IIJA，含电池材料条款）` → USC 修订注记 → CFR 实施条例（40 CFR 260/261/273、
49 CFR 171–173 已验证）→ FR 现行文书（含 2026 年 PHMSA/BIS/EPA 行动）——每一跳均有**官方源头证据**（AUTH 注记 / NOTE 注记）。

> 诚实备注：18.5% 的 matched 比例受「只采集 20 个 Part」限制，不是关系错误；全量 Part 枚举列入 4B-2 P1。

---

## 6. Legal Family Closure（`legal_family_official.json`）

| Root | 官方关系（Cellar SPARQL） | 完整度 |
|---|---|---|
| `32023R1542`（电池条例） | AMENDS 3 ｜ CORRIGENDUM_OF 14 ｜ RELATED_PROPOSAL 6 ｜ CONSOLIDATED 24 | 1.0 |
| `32000L0053`（ELV 指令） | AMENDS 16 ｜ CORRIGENDUM_OF 3 ｜ REPEALS 1 ｜ REPLACED_BY 1 ｜ TRANSPOSES 200（接口上限）｜ CONSOLIDATED 36 | 1.0 |
| `32024R1157`（WSR 跨境废物） | AMENDS 2 ｜ CORRIGENDUM_OF 5 ｜ RELATED_PROPOSAL 2 ｜ CONSOLIDATED 13 | 1.0 |
| `32006L0066`（电池指令） | AMENDS 5 ｜ CORRIGENDUM_OF 4 ｜ REPEALS 1 ｜ RELATED_PROPOSAL 6 ｜ TRANSPOSES 200（接口上限）｜ CONSOLIDATED 14 | 1.0 |

7 种官方谓词 + `absent_official` 语义 → **P0 unresolved = 0**。AI 不推断关系，全部来自官方端点。

---

## 7. Instrument Accuracy（0.786 → 1.0）

| 指标 | Before | After |
|---|---|---|
| accuracy | 0.786 | **1.0（14/14）**，目标 0.95 ✅ |
| mismatch 原因码（5 类） | 混装 | 0（TITLE_INSUFFICIENT / NIM_METADATA_INSUFFICIENT / UNKNOWN_DOCUMENT_CLASS / RULE_MAPPING_ERROR / SOURCE_METADATA_MISSING 全为 0） |

关键修复（全部经真实对照发现）：① CELEX 类型位分辨不出 delegated/implementing → CELEX 降为回退层；
② `Commission Notice … Regulation (EU) 2023/1542` 误判条例 → guidance 优先级前移；③ NIM 母语文种规则
（vyhláška/Verordnung/décret/real decreto/besluit）；④ 结构化官方形状（40 CFR Part=regulation、U.S.C. Title=statute、
PLAW=statute、CBP Ruling=official_guidance，测试锁定「裁定不得判 regulation」）。

**Gold Set 唯一一处修正**（附官方依据）：捷克部令 `standard/partially_binding → administrative_rule/binding`。
binding force 判定链 = 规则信号 + matched 证据可复核，**AI 不单独裁定**。

---

## 8. Gold Set（24 案例；holdout 9）

| 分类 | 数量 | 备注 |
|---|---|---|
| A1 | **0** | → `INSUFFICIENT_A1_GOLDSET`（见下） |
| A2 | 12 | 含 bm_wsr_main / bm_wsr_delegated（黑粉主链） |
| B | 6 | 新增 hard_b_rcra_hazardous_waste（40 CFR Part 261）、hard_b_hazmat_shippers（49 CFR Part 173，holdout=true） |
| C | 2 | bg_espr / bg_critical_minerals_list |
| D | 4 | 负例（FEOC / DDR / OSHA / BCI 文章） |

验收：**cases 24/24，P = R = F1 = 1.0；b_recall = 1.0**。

**A1 状态如实**：三路线搜证（EUR-Lex 关键词 / FR 引号短语 26 候选 / 自有语料 3202 条标题扫描 16 命中）→
**a1_verified_count = 0**。原因区分：
- **A 真实语料稀少**：EU 层面 EV 牵引电池专项立法极少（核心为横向体系 → A2 类）；BEV 贸易救济对象是整车，不得降格充数；
- **B 源宇宙尚未闭合**：US 州级 0/51（多州有 EV 电池专项法）、EU 成员国深采未启动 —— **这正是 A1 型文书的真实栖息地**。

**坚决未做**：为凑 ≥5 而人工添加样本。

---

## 9. LIVE Discovery Rounds（真实运行，4 类独立路线）

路线：`A official_enumeration`（FR 机构枚举 / EUR-Lex CELEX 年段）｜`B native_fulltext_search`（FR 短语 / EUR-Lex 关键词）｜
`C legal_relation_expansion`（官方家族关系 CELEX 回采）｜`D open_web_gap_discovery`（CROSS API / Basel 出版物）。

指标口径（规格强制）：`raw_result_count / unique_candidate_count / accepted_count / new_unique_accepted_count /
duplicate_accepted_count / rejected_count` 全量记录；**SG8 主判据 = accepted_novelty_rate**（`new/(new+dup)`）；
`raw_yield` 仅检索效率，**不得单独证明饱和**；失败轮不作收敛证据。

### US_FEDERAL（3 轮）

| 轮 | raw | uniq | accepted | new | dup | rejected | novelty | raw_yield | failures | persisted |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 238 | 160 | 54 | **25** | 29 | 106 | **0.463** | 0.105 | 1 | 25 |
| R2 | 256 | 174 | 34 | **1** | 33 | 140 | **0.0294** | 0.0039 | 0 | 1 |
| R3 | 195 | 137 | 30 | **4** | 26 | 107 | **0.1333** | 0.0205 | 2 | 4 |

失败明细：R1/R3 的 `us_federal_register` 机构枚举出现瞬态 `ConnectError`（网络级，非源级封禁）。

### EU_SUPRANATIONAL（3 轮）

| 轮 | raw | uniq | accepted | new | dup | rejected | novelty | raw_yield | failures | persisted |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 52 | 59 | 19 | **19** | 0 | 40 | **1.0** | 0.3654 | 0 | 19 |
| R2 | 50 | 57 | 19 | **0** | 19 | 38 | **0.0** | 0.0 | 0 | 0 |
| R3 | 56 | 63 | 20 | **3** | 17 | 43 | **0.15** | 0.0536 | 0 | 3 |

> EU 轮次结构：R1 = A 11 new（CELEX 年段新法规）+ D 8 new（Basel 官方出版物）；R2 = 19 条 accepted **全部为已知文档**
> （novelty 0.0，零新增）；R3 = A 通道年段推进又发现 **3 条新 CELEX**（novelty 回升 0.15）。B 通道 R1 raw=0（请求成功、解析成功、
> 0 命中 → NO_RESULTS，不记失败；R3 命中 1 条但为已知文档）；C 通道 15 条家族文档全部 D 类（横向工具文书，不充数）。

### 收敛判定（如实）

`converged = False`（threshold 2% × 连续 2 轮）。US：R2 一度逼近（2.94%），但 R3 换词表后回升至 13.3% 且含失败轮；
EU：R2 归零（0.0）后 R3 因 CELEX 年段推进又回升至 15% —— 两侧均为 **streak=0，未收敛，不宣称饱和**。
结论与 A1 结论一致：真实栖息地（成员国/州级）尚未接入，已接入源宇宙的边缘仍在扩展。

**本轮修复的设计缺口**：原轮次不落盘新文档 → 每轮重复计「新发现」、novelty 永不收敛；已改为
`outputs/round_*.jsonl` 持久化并入语料（US 30 + EU 19 条已落盘）。

---

## 10. Black Mass Coverage（六线矩阵，`black_mass_coverage.json`）

| 线路 | 全球 | EU | US |
|---|---|---|---|
| waste_status（废物定性） | ✅ 38 文档 / 36 强证据 | ✅ | ✅ |
| hazardous（危废属性） | ✅ 238 / 71 | ⚠️ **PARTIAL**（1 文档 / 0 强证据） | ✅ |
| transport（运输） | ✅ 329 / 74 | ✅ | ✅ |
| transboundary（跨境转移） | ✅ 21 / 21 | ✅ | ✅（1 条强证据，偏薄） |
| customs（海关） | ✅ 342 / 20 | ✅ | ✅ |
| end_of_waste（废物终点） | ✅ 53 / 23 | ✅ | ✅ |

**全球 6/6 COVERED ｜ EU 5 COVERED + 1 PARTIAL ｜ US 6/6 COVERED**。
EU 危废线 PARTIAL：EU 侧文本多用「waste batteries」表述，危废属性条款（Annex/HP 代码）锚点未命中 →
**如实记 PARTIAL**（补锚词入 4B-2 P2，不强行升级为 COVERED）。

---

## 11. Saturation（四 scope 独立评价，`scope_saturation.json`）

| Scope | 等级 | 通过 | SG1 源宇宙 | SG5 身份 | SG6 家族 | SG7 路线 | SG8 新颖率 |
|---|---|---|---|---|---|---|---|
| EU_SUPRANATIONAL | **PARTIAL** | 6/9 | ✗ 77.8%/75.0% | ✗ 85.8% | ✓ P0=0 | ✓ 4 | ✗ 0.15（R2=0 后 R3 回升；未连续 2 轮 <2%） |
| EU_MEMBER_STATES | **PARTIAL** | 6/9 | ✗ 4/27 (14.8%) | ✗ 85.8%（区域口径） | ✓ | ✓ | 无轮次数据 |
| US_FEDERAL | **PARTIAL** | 7/9 | ✓ 100%/100% | ✗ 59.2% | ✓ P0=0 | ✓ 4 | ✗ 0.1333（未达连续 2 轮 <2%） |
| US_STATES | **PARTIAL** | 6/9 | ✗ 0/51 | ✗ 59.2%（区域口径） | ✓ | ✓ | 无轮次数据 |

**无 scope 达 SATURATED**。禁止把 US Federal 当作 "United States complete"（口径已固化进代码）。

---

## 12. Remaining P0 / P1 / P2

**P0（阻断「饱和」宣称）**
1. **A1 = 0 → INSUFFICIENT_A1_GOLDSET**（真实语料稀少 + 源宇宙未闭合，双原因并存）；
2. EU critical 6/8：STANDARDS（**规则上限 PARTIAL**）、OECD（SPA 不可抽取）——不因官方引用可查而冒充 COMPLETE；
3. 轮次未收敛（US novelty 0.1333 / EU 0.15，均含回升轮），SG8 未过；
4. US/EU 身份未达各自目标（59.2% / 85.8%）。

**P1**
5. EU_MEMBER_STATES 4/27 (14.8%)、US_STATES 0/51 —— 4B-2 主体；
6. FR→CFR matched 18.5%（仅采集 20 Part）；
7. EU 轮次 B 通道（EUR-Lex 关键词）R1 0 结果 —— 通道稳定性观察；
8. FR 富化 4 条 needs_human_review 未决。

**P2**
9. EU 危废锚词扩展；10. CROSS 裁定扩容；11. Basel PDF 解析增强；12. 轮次词表持续轮换。

---

## 13. Test Results

- `py -m pytest tests/phase4b1 tests/policy -q` → **179 passed**（Phase 4A 46 + 4B-1 133）
- 旧脚本回归：`test_portal_judge.py` 21/21 ｜ `test_browser_challenge.py` 10/10 ｜ `test_channel_dedupe.py` 5/5 ｜ `test_convergence_gates.py` 4/4
- 新增测试文件（本步）：`test_live_round_schema.py` / `test_novel_rate_live.py` / `test_scope_level_saturation.py` / `test_black_mass_coverage.py`
- 测试环境注意：本机 `%TEMP%` 权限缺陷 → 测试统一使用 `outputs/` 下临时目录（不改变测试语义）。

---

## 14. Changed Files（全程 83 个）

app/ 24 ｜ tests/ 28 ｜ scripts/ 16 ｜ sources/ 5 ｜ docs/ 10

关键新增：`app/policy/{source_access,source_probe,identity_us,backfill,cfr,us_code,us_trade,crossborder,family_official,instrument_audit,rounds,scope_saturation,black_mass}.py`；
`app/connectors/{ecfr,govinfo,cbp_cross}.py`；
`scripts/{probe_source_endpoints,audit_source_roles,enrich_us_identity,collect_ecfr_parts,collect_us_code_plaw,collect_us_trade_sources,collect_eu_crossborder_sources,refresh_legal_family,audit_instrument_accuracy,audit_legal_links,search_a1_candidates,run_discovery_round,audit_scope_saturation,audit_black_mass_coverage}.py`；
`sources/{source-endpoints,source-role-aliases}.yaml` + registry/instrument-types/goldset 更新。

---

## 15. Commits（Step 0–10，共 12 个）

```
1d0e69d（基线·Phase 4A）
+f2cde47 Step 0 计划 ｜ 3a23db6 Step 1 矩阵+探测 ｜ 5680ca5 Step 2 身份+别名
+6cc12d8 Step 3 eCFR ｜ aec195a Step 4 USC/PL ｜ f0fed8a Step 5 CBP/BIS
+c412497 Step 6 Basel/OECD/标准 ｜ ffc34ee Step 7 家族关闭 ｜ f8bfc0b Step 8 精度 1.0
+bba4b31 Step 9 A1 搜证 ｜ <Step10a> 轮次/scope/黑粉工程 ｜ <本提交> Step 10 收尾+报告
```

---

## 16. Recommendation for Phase 4B-2

**结论：NOT READY for Saturated；READY for 4B-2（目标明确）。**

1. **EU 27 成员国 Source Onboarding（P0）**：NIM 已有 27 国记录但 role 大多 PARTIAL（4/27 CONNECTED）→
   各国立法门户/公报深采 → 直击 A1 栖息地；
2. **US 50 州（P0）**：0/51 → 州级 EV 电池专项法（CA/NY/WA 等先行）；
3. **接入后继续轮次**：预期 novelty 先升后降，重测 SG8 收敛；
4. **Identity**：为 USC/PL/CBP/CFR 文档建立 celex 等价键，US 59.2% → ≥90%；
5. **FR→CFR 全量 Part 枚举**，matched 18.5% 向上；
6. **Standards 维持 PARTIAL 口径**：走官方引用链，不伪建标准库；
7. **A1**：仅当成员国/州级深采后仍找不到正例，才可下「真实稀缺」终结论。

---

*本报告全部数字来自本阶段真实运行产物（`outputs/audit/*.json`、`outputs/discovery_rounds/*.json`、语料 jsonl 与提交记录），
未做任何手工修饰；PARTIAL / INSUFFICIENT 均如实保留。*
