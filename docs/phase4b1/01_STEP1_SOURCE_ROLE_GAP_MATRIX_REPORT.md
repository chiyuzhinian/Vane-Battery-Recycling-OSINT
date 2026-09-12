# Phase 4B-1 · Step 1 报告 —— Source Role Gap Matrix & Endpoint Probe

> 日期：2026-09-12 ｜ 状态：**Step 1 完成，等待验收后进入 Step 2（US Federal connector）**
> 本步骤只回答一个问题：**Source Universe 中每个 Source Role 当前到底真的可用、部分可用、阻塞，还是没接入？**
> 纪律：宁可输出 PARTIAL / BLOCKED / NOT_ONBOARDED，不为了覆盖率把角色标绿。

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| 端点注册表 | `sources/source-endpoints.yaml` | ✅ 12 角色组、45 端点（EU 超国家 10 + US 联邦 12 + 成员国通道 + 州级 1） |
| 探测结果 | `outputs/audit/source_probe_results.json` | ✅ 45 端点真实探测（本地产物，可复跑） |
| Gap Matrix | `outputs/audit/source_role_gap_matrix.json` + `.csv` | ✅ 106 行（含成员/州级行） |
| failure taxonomy | `app/policy/source_access.py` | ✅ 17 失败类型 + NO_RESULTS（非失败） |
| 探测器 | `app/policy/source_probe.py` + `scripts/probe_source_endpoints.py` | ✅ 重试 1 次；失败分类落盘 |
| 矩阵 CLI | `scripts/audit_source_roles.py` | ✅ 状态推导 + scope 覆盖汇总 |
| 测试 | `tests/phase4b1/`（3 文件 32 条） | ✅ **78 passed**（本步骤 32 + Phase 4A 46） |

复现命令：
```
py scripts/probe_source_endpoints.py
py scripts/audit_source_roles.py --json
py -m pytest tests/phase4b1 tests/policy -q
```

---

## 2. 端点探测真实结果（2026-09-12）

**45 端点：ACCESSIBLE 36 ／ PARTIAL 1 ／ BLOCKED 8**

| 角色 | 端点 | 状态 | HTTP | 失败类型 | 说明 |
|---|---|---|---|---|---|
| BASEL | basel_document_download | PARTIAL | 200 | UNSUPPORTED_FORMAT | PDF 可下载（官方），本阶段无解析器 → **fulltext_available=false**（不得假装拿到全文） |
| ENVIRONMENT_AGENCY | echa_home | **BLOCKED** | 403 | HTTP_403 | bot 拦截；角色经浏览器通道仍有 31 条入库（见 §4） |
| MEMBER_STATE_LEGISLATION | fr_legifrance | **BLOCKED** | 403 | CAPTCHA | Legifrance 反爬；FR 仍有 DILA 专线通道 |
| OECD | oecd_main_waste | **BLOCKED** | 403 | CAPTCHA | 主站不可达；legalinstruments 子域 **ACCESSIBLE**（官方替代通道） |
| PUBLIC_LAW | congress_api | **BLOCKED** | 403 | **API_KEY_REQUIRED** | congress.gov 需 Key；govinfo 两通道可达（官方替代） |
| STANDARDS | iso_catalogue | **BLOCKED** | 403 | CAPTCHA | bot 拦截（≠ 付费墙，见 §5） |
| STATE_ENVIRONMENT_AGENCY | calrecycle_home | **BLOCKED** | 403 | CAPTCHA | 直连被阻；浏览器通道已有 41 条数据 |
| US_CODE | govinfo_bulk_uscode | **BLOCKED** | 404 | HTTP_404 | bulkdata 路径待 Step 4 固定样本验证 |
| US_CODE | uscode_house | **BLOCKED** | — | TIMEOUT | 官方站超时（PowerShell/httpx 双工具复现） |

可达的关键端点（36）包括：EUR-Lex 主库/NIM/OJ、Cellar SPARQL、ECFR（titles/search/full-xml 三通道）、FR API（列表+单文档）、govinfo wssearch（PLAW/USC）、CROSS、BIS EAR、Basel 技术导则、CEN/CENELEC 主站+门户、EU 调和标准引用页、JRC 仓库、OECD legalinstruments、四个成员国立法/公报通道等。

**两处真实假阳性（已修复 + 测试锁定，详见 §5）**。修复后未发现新的假阳性。

---

## 3. Gap Matrix（真实状态，未粉饰）

```
EU_SUPRANATIONAL  mandatory 4/9 (44.4%)   critical 4/8 (50.0%)
US_FEDERAL        mandatory 9/12 (75.0%)  critical 6/9 (66.7%)
EU_MEMBER_STATES  行 4/27 (14.8%)         （DE/NL/ES/FR 连接；其余 PARTIAL = NIM 索引已入但非法律全集）
US_STATES         行 0/51 (0.0%)          （仅 CA 有浏览器通道数据；其余 NOT_ONBOARDED，属 4B-2）
critical_blocked_roles = 0（关键角色无一被判死；8 个失败全在端点级）
```

**为什么这些数字没有更高**：本步骤尚未写任何 collector（Step 3–6 才接入 eCFR/USC/PL/CBP/BASEL/OECD），
在途角色只能到 `ACCESSIBLE / PARTIAL`——这正是本步骤要暴露的真实起点。

### 3.1 逐关键角色：为什么是这个状态（规格要求的六问）

| 角色 | 状态 | 通过哪个端点 | 探测证据 | 能力 | 失败在哪 | 官方替代通道 |
|---|---|---|---|---|---|---|
| EURLEX_PRIMARY | **COMPLETE** | eurlex_celex_1542 + cellar_sparql | 200 + JSON{head,boolean} | metadata+fulltext | — | — |
| EURLEX_DELEGATED_IMPLEMENTING | CONNECTED | eurlex_celex_606 | 200 | metadata+fulltext | — | Cellar SPARQL 可枚举 |
| EU_OFFICIAL_JOURNAL | CONNECTED | eurlex_home | 200 | metadata+fulltext | — | OJ 与 EUR-Lex 同库 |
| CUSTOMS_TRADE | PARTIAL | eurlex_wsr_1157 | 200 | metadata+fulltext | 数据 0 条（source_id `eu_eurlex_waste_shipment` 无对应记录，需 Step 2 别名对账） | TARIC（P2） |
| ENVIRONMENT_AGENCY | **CONNECTED** | —（直连阻） | echa 403 HTTP_403 | 经浏览器通道 | echa_home | ✅ 浏览器通道（31 条） |
| STANDARDS | PARTIAL（ceiling） | cencenelec/portal + eu_harmonised_standards_ref + jrc | 200 | metadata（非全文） | iso_catalogue（403）；CEN 门户部分 500 历史 | ✅ EU 官方引用（OJ/JRC） |
| BASEL | ACCESSIBLE | basel_tech_guidelines ⚠ | 200 | metadata | PDF 无解析器（UNSUPPORTED_FORMAT） | Basel PDF 直链可下载（971KB） |
| OECD | PARTIAL | oecd_legalinstruments | 200 | metadata+fulltext | oecd_main_waste（403） | ✅ legalinstruments 子域 |
| FEDERAL_REGISTER | **COMPLETE** | fr_documents_api + fr_single_doc_api | 200 JSON | metadata+fulltext | — | — |
| CFR_ECFR | CONNECTED | ecfr_titles + ecfr_search + **ecfr_full_xml** | 200（三通道） | metadata+fulltext | — | 结构化采集待 Step 3 |
| US_CODE | PARTIAL | govinfo_wssearch_uscode | 200 JSON{books} | metadata | uscode_house TIMEOUT；bulk 404 | ✅ govinfo 两通道 |
| PUBLIC_LAW | PARTIAL | govinfo_wssearch_plaw + bulk | 200 | metadata | congress_api API_KEY_REQUIRED | ✅ govinfo |
| AGENCY_RULES/EPA/PHMSA/DOE/IRS/STATE_DEPT | CONNECTED/COMPLETE | FR 机构通道（8 个 probe） | 200 JSON | metadata+fulltext | — | — |
| BIS | CONNECTED | fr_agency_bis + bis_ear_page | 200 | metadata+fulltext | — | FR 机构通道 |
| CBP | ACCESSIBLE | cross_search + fr_agency_cbp | 200 | metadata | 无采集器（Step 5） | FR 机构通道（已有命中） |

★ 结论：**单端点失败没有杀掉任何一个关键角色**；8 个失败全部以 `blocked_endpoints` 形式保留在矩阵里（规格 §“一个入口坏了 ≠ 整个源不可用”）。

---

## 4. 状态推导规则（写死并可测）

`app/policy/source_access.derive_role_status`：

```
无端点声明           → 沿用注册表 + 数据反推（Phase 4A 兼容）
全部端点 BLOCKED     → BLOCKED
   ⤷ 例外：有替代采集通道且 evidence>0 → CONNECTED（block_reason 标注直连被阻）
有可用端点+采集器+数据 → CONNECTED（声明 COMPLETE 且无 blocked → COMPLETE）
有可用端点+采集器+零数据 → PARTIAL
有可用端点+无采集器   → PARTIAL（有 blocked 端点）｜ ACCESSIBLE（无）
status_ceiling 生效   → 封顶（STANDARDS = PARTIAL）
```

矩阵列（规格 §3 要求的 16 列全部产出 + 4 列扩展）：
`jurisdiction / scope / source_role / mandatory / critical / source_name / official_domain / configured / reachable / collector_available / enumeration_available / fulltext_available / metadata_available / last_checked / status / block_reason / evidence_count / declared_status / usable_endpoints / blocked_endpoints`

---

## 5. Failure taxonomy 与两个真实假阳性（已修复并测试锁定）

### 5.1 taxonomy（17 + 1）

```
HTTP_403 / HTTP_404 / HTTP_429 / HTTP_5XX / HTTP_OTHER_4XX
TIMEOUT / DNS_FAILURE / TLS_FAILURE / CONNECTION_ERROR
CAPTCHA / API_KEY_REQUIRED / AUTH_REQUIRED / ROBOTS_RESTRICTED
PAYWALL_CONFIRMED / PARSER_FAILURE / SCHEMA_DRIFT / UNSUPPORTED_FORMAT
NO_RESULTS（= 请求成功 + 解析成功 + 确实 0 条 → **不是失败**）
```

### 5.2 修复的两个真实缺陷（探测跑出来的，不是猜的）

1. **EUR-Lex/Basel/JRC 被误判付费墙**：原规则用裸词 `eur` / `price` + 语境 `standard` ——
   `eur` 命中 “EUR-Lex”、`standard` 命中法律正文。
   → 改为**强证据**：订阅/购买短语，或（价格数字 + 购物车/结算语境）。
   回归测试：`test_official_free_page_is_not_paywall_false_positive`。
2. **BIS EAR 页被误判付费墙**：罚款金额 `$250,000` + 新闻订阅 “Subscribe” 命中旧语境词。
   → 从价格语境里移除 `subscribe`；回归测试：`test_price_plus_newsletter_is_not_paywall`。
3. **200 页面 CAPTCHA 过敏感**：普通页面里的 recaptcha 脚本引用被当挑战页。
   → 200 路径启用**严格挑战标记**（“solve the captcha / checking your browser / enable javascript and cookies to continue” …）；
   4xx 路径保持宽松。回归测试：`test_200_page_challenge_requires_strict_markers`。

### 5.3 Standards 五概念分离（用户口径落地）

```
metadata_available / fulltext_available / open_access_status / metadata_source_type / endpoint_status
open_access_status ∈ {open_fulltext, official_metadata_only, paywalled_known, unavailable}
metadata_source_type ∈ {OFFICIAL_PUBLISHER, EU_OFFICIAL_REFERENCE, JRC_REFERENCE, OTHER_OFFICIAL_REFERENCE}
```
- **HTTP 403/500 ≠ paywalled_known**：ISO 403 只记 `endpoint_status=BLOCKED + failure_type=HTTP_403`（测试锁定）。
- **EU 官方引用 ≠ 标准库接入**：STANDARDS 角色 `status_ceiling: PARTIAL`（测试锁定：有采集器+数据也不得 COMPLETE）。
- Basel 官方 PDF：`reachable=true` 但 `fulltext_available=false`（UNSUPPORTED_FORMAT）——可引用、可登记，**不生成条款证据**。

---

## 6. 强制修正：SG8 Novel Rate 口径（审计 + 新指标，暂不覆盖旧引擎）

### 6.1 现有收敛定义（`app/core/feedback.py`，测试 `tests/test_convergence_gates.py`，**不覆盖**）

```
rate = round_novel / round_raw        # 本轮边际新发现率（管道内 candidate 级，分母非搜索原始结果）
闸门①：round_raw < MIN_RAW_FOR_CONVERGENCE(30) → 不计入收敛计数
闸门②：round_raw == 0 → 疑似源故障，绝不判收敛
阈值：NOVEL_RATE_CONVERGENCE = 0.02 ｜ 连续 CONVERGENCE_STREAK = 2 轮 → 自然收敛
```

### 6.2 Phase 4B-1 LIVE round 指标（规格 §10-11 + 用户修正）

每轮必须同时记录：
`raw_result_count / unique_candidate_count / accepted_count / new_unique_accepted_count / duplicate_accepted_count / rejected_count`

```
raw_yield             = new_unique_accepted / raw_result_count          → 检索效率（**不得单独证明饱和**）
accepted_novelty_rate = new_unique_accepted / (new_unique_accepted + duplicate_accepted)
                        → 真正有价值语料是否还在增长（**SG8 主判据**）
```

理由（用户示例）：宽泛检索 raw=1000、新接受=5 → raw_yield 0.5% 看似“已收敛”，
但该轮相关语料共 10 条、其中 5 条全新 → 实际新增率 50%，**远未饱和**。raw 噪声不得稀释 SG8。

### 6.3 最终口径（唯一定义，Step 10 实现并测试）

- **SG8 主判据** = `accepted_novelty_rate` 连续 ≥2 轮 < 2%（且该轮无 source failure）。
- `raw_yield` 仅作 Discovery Efficiency 报告项。
- 与旧引擎关系：`feedback.py` 继续服务源×关键词调权（其 rate 分母是已过滤候选，不是搜索原始结果）；
  live-round 指标服务**语料级饱和判定**。二者不冲突、不互相替代；报告并列展示。
- 落地文件：`scripts/run_discovery_round.py`（Step 10）、`tests/phase4b1/test_novel_rate_live.py`。

---

## 7. 测试结果

```
tests/phase4b1（本步骤新增 32 条）
  test_failure_taxonomy.py     : 状态码/正文信号/JSON 结构/NO_RESULTS/付费墙/挑战页 14 条
  test_source_role_status.py   : 状态推导 9 条（含 OECD 模型、替代通道模型、ceiling）
  test_endpoints_config.py     : 配置 fail-fast 9 条（角色存在性/critical 端点/Standards 语义）
tests/policy（Phase 4A 46 条）  : 全部通过，未修改任何旧断言
合计：78 passed / 0 failed
```

---

## 8. 已知偏差与 Step 2+ 对账项（不隐藏）

1. **source_id 别名对账**：`eu_nim` / `eu_eurlex_waste_shipment` 在 registry 中作为角色源，但库内真实
   source_id 是 `eu_nim_xx` / `eur_lex` 系列 → 部分角色 `evidence_count` 偏低（EURLEX_NIM=0、CUSTOMS_TRADE=0）。
   Step 2/3 增加 source_id↔role 别名映射后重刷矩阵（**不影响本报告结论的真实性**：状态由可达性优先判定）。
2. **CFR_ECFR 计数的保守性**：当前 evidence_count 来自 FR 记录的 CFR 引用；
   结构化 eCFR 记录在 Step 3 落盘后该数字才会体现真实结构化语料。
3. **govinfo bulkdata 路径**：`/bulkdata/USCODE` 404（PLAW 200 SPA 外壳）→ Step 4 以固定样本确定真实文件路径。
4. **CEN 门户历史 500**：本次探测 `standards.cencenelec.eu` 200，但深层 f?p= 页面曾 500；
   Step 6 固定 3–10 真实标准样本后再判定其可用层级。

---

## 9. 变更文件

```
新增  sources/source-endpoints.yaml
修改  sources/jurisdiction-registry.yaml        （critical 标记 ×17 角色）
修改  app/policy/config.py                      （Endpoint 模型 + load_endpoints + critical 字段）
新增  app/policy/source_access.py               （taxonomy + Standards 模型 + 角色状态推导）
新增  app/policy/source_probe.py                （HTTP 探测，重试 1 次）
修改  app/policy/source_universe.py             （has_collector / evidence_counts 公开接口，向后兼容）
新增  scripts/probe_source_endpoints.py
新增  scripts/audit_source_roles.py
新增  tests/phase4b1/{test_failure_taxonomy,test_source_role_status,test_endpoints_config}.py
新增  docs/phase4b1/01_STEP1_SOURCE_ROLE_GAP_MATRIX_REPORT.md（本文件）
产物  outputs/audit/{source_probe_results.json,source_role_gap_matrix.json,source_role_gap_matrix.csv}
      （outputs/ 被 .gitignore 忽略：产物可复跑生成，报告进 docs/）
```

---

## 10. 下一步（Step 2，待放行）

1. FR 身份富化（单文档 API 已实测 200）：RIN / cfr_references / action / citation / dates → overlay（默认 dry-run）
2. backfill 扩展参数（`--region / --source-role / --only-missing / --limit` + before/after）
3. source_id↔role 别名对账（§8.1）并重刷矩阵
4. 完成后出 Step 2 报告，再进入 Step 3（eCFR connector）。
