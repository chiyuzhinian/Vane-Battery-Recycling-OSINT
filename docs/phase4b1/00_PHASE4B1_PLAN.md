# Phase 4B-1 — Core Source Closure & Legal Identity Hardening · 执行计划

> 阶段名：**Phase 4B-1**（正式）｜ 模式：Plan / Audit 先行，未写一行业务代码
> 输入：Phase 4A 交付（commit `1d0e69d`，EU=WEAK 4/9，US=WEAK 3/9）
> 边界重申：**不重写** relevance 架构 / review overlay / feedback engine / raw evidence /
> 现有 collectors / saturation 框架 / frontend / Vane。本阶段只做「补源 → 验证 → 建身份 → 建关系 → 重跑验收」。

---

## 0. Inspect 回执（已读文件 + 已做探测）

### 0.1 已读（按要求全量）

| 类别 | 文件 | 关键结论 |
|---|---|---|
| 审计 | `docs/phase4a/00_CURRENT_STATE_AUDIT.md` | 7 问全答：配置漂移坐实（`search-boundary.yaml` 无运行时消费者）；`relevant=True` 混装；身份靠 meta ad-hoc |
| 报告 | `docs/phase4a/PHASE4A_POLICY_ACCEPTANCE_SATURATION_REPORT.md` | P0 blocker 四项；P1：instrument 精度 0.786、A1 无正例、BIS/CBP/eCFR/USC 未接入 |
| 配置 | `sources/jurisdiction-registry.yaml` | EU 12 角色（3/11 覆盖）、US 16 角色（7/16）、27 国、51 州；**无 critical 标志、无 official_domain、无 access_method 字段** |
| 配置 | `sources/regulatory-topics.yaml` | T01–T14 完整；P0 主题 = T01/T02/T03/T05/T06/T07/T08/T09/T10/T13 |
| 配置 | `sources/instrument-types.yaml` | 14 类型 + priority + 4 判例锚点 |
| 配置 | `sources/policy-acceptance-rules.yaml` | A1 对象含 `EV_TRACT[ION]_BATTERY | BLACK_MASS`（A1 规则已就绪但无正例） |
| 配置 | `sources/policy-goldset.yaml` | 22 案例：A1=0、A2=10、B=5、C=2、D=4、边界 1；holdout=6 |
| 代码 | `app/policy/{config,instruments,acceptance,source_universe,legal_identity,legal_graph,goldset,saturation}.py` | 见 §0.3 复用清单 |
| 代码 | `app/connectors/`（13 个） | `eur_lex.py` **已有 SPARQL / 标题锚点 / CELEX 批取 / 全文抓取**；`us_federal.py` 仅收集 8 个字段（缺 `cfr_references`/`RIN`/`citation`/`action`） |
| 脚本 | `scripts/`（60+） | `audit_policy_universe/saturation/legal_family`、`backfill_policy_metadata`、`collect_member_states_nim`、`discover_eu_acts`、`collect_eu_gaps` 可复用 |
| 测试 | `tests/policy/`（8 文件 46 条） | 全部 pytest 风格，新增测试用同风格 |

### 0.2 真实源可达性探测（2026-09-12 实测，未写入任何文件）

| 目标 | URL | 结果 | 结论 |
|---|---|---|---|
| eCFR 版本目录 | `ecfr.gov/api/versioner/v1/titles.json` | **200** ✅ | eCFR 可行（无需 key） |
| eCFR 检索 | `/api/search/v1/search?...` | 404 ❌ | 路径错误 |
| eCFR 检索（正确） | `/api/search/v1/results?query=…` | **200** ✅ | 全文/关键词检索可行 |
| eCFR 全文 XML | `/api/versioner/v1/full/…/title-40.xml?part=273` | 406 ⚠️ | 需 `Accept` 头，实施时验证 |
| FR 单文档（身份富化） | `/api/v1/documents/2019-03812.json` | **200** ✅ | **身份富化主通道**（含 cfr_references/RIN/action） |
| uscode.house.gov | `/download/download.shtml` | 超时 ❌ | 记 `SOURCE_FAILURE:TIMEOUT`，改走 govinfo |
| govinfo PLAW | `/bulkdata/PLAW` | 200（SPA 外壳）⚠️ | 真实清单路径待定，需样本验证 |
| govinfo 检索后端 | `/wssearch/rb/plaw` | 200 ⚠️ | 可用性待样本验证 |
| CBP CROSS | `rulings.cbp.gov/` / `/search?term=battery` | **200** ✅ | 需 HTML 行解析 + 3–10 真实裁定样本 |
| BIS EAR | `bis.doc.gov/.../export-administration-regulations-ear` | **200** ✅ | 可行 |
| Basel 技术导则 | `basel.int/...DevelopmentofTechnicalGuidelines...` | **200** ✅ | 可行 |
| Basel 文件直链 | `basel.int/Portals/4/download.aspx?...pdf` | **200**（971KB）✅ | PDF 可下载（解析能力待评估） |
| OECD 法律文书 | `legalinstruments.oecd.org/en/instruments` | **200** ✅ | 走此子域 |
| OECD 主站 | `oecd.org/env/waste/` | 403 ❌ | 记 `SOURCE_FAILURE:HTTP_403` |
| CEN 标准门户 | `standards.cencenelec.eu/...f?p=205:…` | 500 ❌（两种 URL） | 标准层改走官方 references 路径 |
| ISO 标准页 | `iso.org/standard/65694.html` | 403 ❌ | bot 防护；`metadata_only` 替代，不得伪造 |
| EU Cellar SPARQL | `publications.europa.eu/webapi/rdf/sparql` | **200** ✅ | **家族关系官方验证可行**（`eur_lex.fetch_relations` 已具备） |

> 探测即「Source proof」第一步。上述 ❌ 一律按 §15 记 **SOURCE_FAILURE**，不得记 0 结果。

### 0.3 直接复用（不重写）

`eur_lex.fetch_relations`（SPARQL 家族关系）· `eur_lex.fetch_celex_batch`（按 CELEX 批采）·
`eur_lex.find_acts_by_title`（锚点）· `us_federal`（FR 通道）· `collect_member_states_nim`（NIM）·
`acceptance.classify_record`（分类计数）· `goldset.evaluate`（验收）· `legal_identity.resolve_identity`（身份基座）·
`feedback.FeedbackEngine`（novel_rate 状态格式：`state["history"][].novel_rate`）·
`authenticity.check_url`（源级真伪）· `review_decisions.jsonl`（人工判据）。

---

## 1. 优先级总表

### P0（阻断验收，本阶段必须做）

| # | 事项 | 产物 | 验收目标（§18） |
|---|---|---|---|
| P0-1 | Source Role Gap Matrix（runtime 得出，禁止人工猜） | `outputs/audit/source_role_gap_matrix.{json,csv}` + `scripts/audit_source_roles.py` | 矩阵完整、状态可复现 |
| P0-2 | US Federal 源闭包：eCFR / U.S. Code / Public Law / CBP / BIS | 4 个新 connector + `FR→CFR→USC→PL` 关系 | US_FEDERAL critical roles = 100% |
| P0-3 | EU 跨境/标准闭包：Basel / OECD / Standards(metadata) | 3 个新 connector（标准为 metadata-only） | EU_SUPRANATIONAL critical roles = 100% |
| P0-4 | Legal Identity Hardening（US 不能只有 title+URL） | 身份富化通道 + before/after 度量 | US_FEDERAL ≥90%；EU_supra ≥95% |
| P0-5 | instrument_type 精度修复 | `outputs/audit/instrument_mismatches.json` + metadata-first 判定 | ≥0.95（真实不足则 PARTIAL） |
| P0-6 | A1 Gold Set 补齐 + hard B / hard D | `sources/policy-goldset.yaml` 扩充 | A1 ≥5（holdout ≥2） |
| P0-7 | Legal Family P0 缺口关闭（ELV / 2006-66） | 更新 `outputs/audit/legal_family_status.json`（带官方证据） | P0 unresolved = 0（或官方缺席证明） |
| P0-8 | LIVE Discovery Rounds ×3（≥3 类独立 route） | `outputs/discovery_rounds/*.json` + 索引 | 3 轮真实数据、novel_rate 真实计算 |

### P1（支撑 P0，必须交付但不独立设卡）

| # | 事项 | 产物 |
|---|---|---|
| P1-1 | backfill 扩展（`--region/--source-role/--only-missing/--limit`，默认 dry-run，before/after） | `scripts/backfill_policy_metadata.py` 升级 |
| P1-2 | scope-level saturation（4 个 scope 独立评价） | `saturation.py` 扩展 + CLI `--scope` |
| P1-3 | Black Mass 六线覆盖矩阵 | `outputs/audit/black_mass_coverage.json` + `app/policy/black_mass.py` |
| P1-4 | Source Failure 分类学（≠ 0 结果） | `app/policy/source_probe.py` + 全链路接入 |

### P2（本期只登记不实现）

`EU 27 国深度采集`（4B-2）· `US 50 州+DC`（4B-2）· `CEN/ISO 重试与替代通道研究` ·
`ECHA 深挖` · `TARIC 关税层` · `NIM 逐国存活验证` · `报告自动生成管线`。

---

## 2. P0-1 Source Role Gap Matrix —— 设计

### 2.1 数据来源（状态不得靠人工猜）

| 字段 | 推导来源 |
|---|---|
| `jurisdiction` / `source_role` / `mandatory` | `jurisdiction-registry.yaml`（`expected=true` → mandatory） |
| `critical` | **注册表新增字段**（本阶段显式标注，见 §2.3） |
| `source_name` / `official_domain` | **新增** `sources/source-endpoints.yaml`（role → 官方域名 + access_method + capabilities + probe_url） |
| `configured` | 注册表 `sources[]` 非空（且 source_id 能解析到 connector/通道） |
| `reachable` | **live probe**（`--live` 时真实 HTTP；否则 `UNVERIFIED`，不冒充） |
| `collector_available` | 代码侧注册表（source_id → 连接器/浏览器通道/NIM 解析器） |
| `enumeration_available` / `fulltext_available` / `metadata_available` | endpoints 声明的能力 ∩ 实测证据（rounds 中该能力真实被使用过） |
| `last_checked` | probe 时间戳（真实） |
| `status` | 状态机 `NOT_ONBOARDED → DISCOVERED → ACCESSIBLE → CONNECTED → PARTIAL → COMPLETE ｜ BLOCKED`，且**数据反推降级**（配置了源但零数据 → PARTIAL；probe 403/超时 → BLOCKED） |
| `block_reason` | probe 失败分类（§15 taxonomy）或注册表 `gap_reason` |
| `evidence_count` | 库内该 source_id 实际记录数（runtime 统计） |

**硬约束**：`URL 存在 ≠ COMPLETE`；BLOCKED 行必须携带真实失败证据（status_code / exception 摘要）。

### 2.2 critical 定义（本阶段固定，写入注册表）

- **EU_SUPRANATIONAL critical**：`EURLEX_PRIMARY`、`EURLEX_DELEGATED_IMPLEMENTING`、`EU_OFFICIAL_JOURNAL`、
  `CUSTOMS_TRADE`、`BASEL`、`OECD`、`STANDARDS`、`ENVIRONMENT_AGENCY`。
  （`TRANSPORT_AUTHORITY` expected=false 不参与；`MEMBER_STATE_*` 归 EU_MEMBER_STATES scope）
- **US_FEDERAL critical**：`FEDERAL_REGISTER`、`CFR_ECFR`、`US_CODE`、`PUBLIC_LAW`、`AGENCY_RULES`、`BIS`、`CBP`、`EPA`、`PHMSA`。
  （`DOE/IRS/STATE_DEPARTMENT` 经 FR 已 CONNECTED，不设卡；`STATE_*` 归 US_STATES scope）

### 2.3 角色矩阵总表（Current Role → 策略）

**EU（超国家）**

| Current Role | Current Status | Required Source | Existing Connector | Need New Connector? | Identity Strategy | Validation Strategy |
|---|---|---|---|---|---|---|
| EU_OFFICIAL_JOURNAL | CONNECTED | OJ（与 EUR-Lex 同库） | `eur_lex` | 否 | CELEX + OJ 引用 | OJ 引用号抽检 3–10 |
| EURLEX_PRIMARY ★ | COMPLETE | EUR-Lex 主库 | `eur_lex` | 否（增强 type 过滤） | CELEX | 锚点扫描回归 + goldset |
| EURLEX_DELEGATED_IMPLEMENTING ★ | CONNECTED | EUR-Lex 授权/实施法案 | `eur_lex` + SPARQL | 否 | CELEX + act_type | 新样本：增补/实施/更正各 ≥3 |
| EURLEX_NIM | CONNECTED | NIM 索引 27 国 | `collect_member_states_nim` | 否 | `NIM:{id}` + base directive | 抽检 + 用户已验捷克 |
| MEMBER_STATE_LEGISLATION | PARTIAL | （4B-2 扩） | DE/NL/ES/FR 专线 | 否（本阶段冻结） | NIM / 国别 id | 冻结，不回归恶化 |
| MEMBER_STATE_OFFICIAL_GAZETTE | PARTIAL | （4B-2 扩） | BOE/BWB/DILA | 否（冻结） | — | 冻结 |
| ENVIRONMENT_AGENCY ★ | PARTIAL | ECHA 官方页（enforcement/REACH 交叉） | `browser.py`（ECHA 通道） | 可能需要（P1 增强） | ECHA 文书号 | 3–10 样本；失败记 SOURCE_FAILURE |
| TRANSPORT_AUTHORITY | NOT_ONBOARDED（expected=false） | — | — | 否 | — | 不参与覆盖 |
| CUSTOMS_TRADE ★ | CONNECTED | WSR 家族（TARIC 暂缓） | `eur_lex`（WSR 锚点） | 否 | CELEX | WSR 家族 1.0 保持 + 跨境六线证据 |
| STANDARDS ★ | NOT_ONBOARDED | CEN/ISO 元数据 + EU harmonised refs（OJ 实施决定/JRC） | 无 | **是**（`standards_ref.py`，metadata-only） | 标准号（EN/ISO）+ 发布方 | `open_access_status` 四值；CEN/ISO 直连失败记 BLOCKED 部分 |
| BASEL ★ | NOT_ONBOARDED | basel.int（实测 200） | 无 | **是**（`basel.py`） | 文件符号（UNEP/CHW.x/…）+ decision 号 | draft≠final≠binding 样本各 ≥3 |
| OECD ★ | NOT_ONBOARDED | legalinstruments.oecd.org（实测 200；主站 403） | 无 | **是**（`oecd.py`） | instrument 号（C(xxxx)nnn） | decision/binding/guidance/information 分辨 |

**US（联邦）**

| Current Role | Current Status | Required Source | Existing Connector | Need New Connector? | Identity Strategy | Validation Strategy |
|---|---|---|---|---|---|---|
| PUBLIC_LAW | NOT_ONBOARDED | govinfo PLAW（congress.gov 403 → BLOCKED） | 无 | **是**（`govinfo.py`） | `PL:{congress}-{num}` + StAL citation | 3–10 真实公法样本（含电池相关） |
| US_CODE | NOT_ONBOARDED | govinfo USC（uscode.house.gov 超时→failure） | 无 | **是**（`govinfo.py`） | `USC:{title}:{section}` + source_credit | 3–10 样本（42/49 卷优先） |
| FEDERAL_REGISTER ★ | COMPLETE | FR API（无 key） | `us_federal` | 否（**扩 FIELDS**：cfr_references/RIN/citation/action/dates） | `FR:{document_number}` + citation | 富化前后对比；2019-03812 回归 |
| CFR_ECFR ★ | PARTIAL | eCFR API（实测 200） | 无 | **是**（`ecfr.py`） | `CFR:{title}:{part}[§{section}]` + authority/source/currentness | FR→CFR 链 ≥3 真实案例 |
| AGENCY_RULES ★ | CONNECTED | FR（20+ 机构） | `us_federal` | 否 | 同 FR | 保持 |
| EPA ★ | CONNECTED | FR + browser | `us_federal` | 否 | 同 FR | 保持 |
| PHMSA ★ | COMPLETE | FR + browser | `us_federal` | 否 | 同 FR | 判例回归（advisory vs rule） |
| DOE | CONNECTED | FR | `us_federal` | 否 | 同 FR | 保持 |
| IRS | CONNECTED | FR | `us_federal` | 否 | 同 FR | 保持 |
| BIS ★ | PARTIAL | bis.doc.gov EAR（200）+ FR(bis) | 无（FR 部分已有） | **是（轻）**（`bis.py` 或 FR agency 配置升级） | FR doc / EAR part | rule/notice/order/guidance 区分样本 |
| CBP ★ | NOT_ONBOARDED | CROSS（200）+ FR(cbp) | 无 | **是**（`cbp_cross.py`） | ruling 号（HQ/NY…） | 裁定/指引/通知区分；不得判 regulation |
| STATE_DEPARTMENT | CONNECTED | FR | `us_federal` | 否 | 同 FR | 保持 |
| STATE_*（4 角色） | 保持现状（4B-2） | — | — | 否 | — | 冻结 |

★ = critical。

---

## 3. P0-2 US Federal 闭包 —— 实施设计

**铁律**：每个源必须走完 `Source proof → 3–10 真实样本 → Identity 校验 → Parser → Collector → 回归`。

1. **eCFR（`app/connectors/ecfr.py`）**
   - 通道：`/api/search/v1/results`（已 200）+ `/api/versioner/v1/titles.json`（已 200）+
     `/structure/{date}/title-{n}.json` + `/full/{date}/title-{n}.xml?part=`（验证 `Accept` 头后启用）。
   - 目标字段：Title / Part / Section / **Authority** / **Source(citations)** / Currentness / FR citations。
   - 相关 CFR 优先：**49 CFR 171–180**（危货运输）、**40 CFR 260–273**（RCRA/危废）、
     19 CFR（海关）、10 CFR（DOE）、15 CFR 730–774（EAR）、40 CFR 98（GHG 报告）。
   - 关系：`FR document → codified_in → CFR Title/Part/Section`（由 FR `cfr_references` + eCFR 结构双向核验）。
2. **U.S. Code（`app/connectors/govinfo.py` 之一）**
   - 通道：govinfo（`content/pkg/USCODE-*` 直链模式，实施时先用 3–5 个真实 URL 固定样本）；
     `uscode.house.gov` 超时 → 记 `SOURCE_FAILURE:TIMEOUT`；congress.gov 403 → `BLOCKED(API_KEY_REQUIRED)`。
   - 字段：title_number / section / heading / text / source_credit / amendments / status / official_url。
3. **Public Law（`govinfo.py`）**
   - 通道：govinfo PLAW（清单路径待样本验证）；关系支持
     `AUTHORIZES` / `AMENDS` / `CODIFIED_AS`（PL→USC）/ `IMPLEMENTED_BY`（PL→FR/CFR）。
   - 官方证据来源优先级：eCFR `AUTH`/`SRC` 注记（含 `Pub. L. xx-xxx` 与 U.S.C. 引用）> govinfo 元数据 > 标题推测（**禁止**）。
4. **CBP（`cbp_cross.py`）**
   - 通道：CROSS 检索页（200）→ 裁定详情；辅以 FR(cbp) 机构通道。
   - 身份：ruling 编号；`instrument_type ∈ {administrative_rule, official_guidance, advisory, information_page}`——
     裁定/ruling=guidance 或 ruling 类（按官方字段），**一律不得判 regulation**（无 rulemaking 记录时）。
   - 主题：black mass / battery waste / lithium materials 的海关归类与进出口。
5. **BIS**
   - 通道 A：FR(bis) 机构检索（已有 FR 基座，加机构配置即可）；
   - 通道 B：`bis.doc.gov` EAR 相关页（200）→ `rule / notice / order / guidance / information` 五分工。
   - 主题：贸易管制 / 出口管制 / 关键矿产 / 电池材料 / 黑粉。

**失败处理**：所有 403/超时/CAPTCHA/需 key 的情形 → §15 taxonomy + 矩阵 `BLOCKED` + 报告 §3 逐条列明。

---

## 4. P0-3 EU 跨境 / 标准闭包 —— 实施设计

1. **Basel（`app/connectors/basel.py`）**：basel.int（200）→ 技术导则/COP 决定/会议文件；
   字段：文件符号、**draft/final 状态**、发布日期、官方 URL、适用对象（电池废物/危废/越境转移/黑粉）。
   铁律：`draft technical guideline ≠ binding`（进 C 或 D，不得进 A 主库）。
2. **OECD（`app/connectors/oecd.py`）**：`legalinstruments.oecd.org`（200）→
   `binding decision / recommendation / guidance / information` 四值；主站 403 记 `SOURCE_FAILURE:HTTP_403`（报告披露）。
   主题：waste recovery、Green/Amber control、competent authorities。
3. **Standards（`app/connectors/standards_ref.py`，metadata-only）**：
   - 优先级：① EU 官方 references（OJ 实施决定/JRC 报告，走 EUR-Lex）→ ② CEN 元数据（当前 500，重试+记录）→ ③ ISO（403，记 failure）
   - 新增字段 `open_access_status ∈ {open_fulltext, official_metadata_only, paywalled_known, unavailable}`；
     登记项：标准号 / 标题 / 状态 / 出版方 / 范围 / 官方 URL。
   - **禁止**为 paywalled / metadata-only 标准生成条款证据；无条款证据 → 不得判 B。

---

## 5. P0-4 Legal Identity Hardening —— 设计

### 5.1 目标字段（US 联邦不再依赖 title+URL）

```
canonical_id / official_identifier / jurisdiction / issuer / instrument_type /
binding_force / publication_date / effective_date / legal_status / current_status /
authority / citation / language / source_role
```

### 5.2 分源身份策略

| 源 | 主键 | 富化字段（官方） |
|---|---|---|
| FR | `FR:{document_number}` | RIN（regulation_id_numbers）、agencies、cfr_references、action、type/subtype、citation(FR 卷/页)、docket_ids、effective_on、dates |
| eCFR | `CFR:{title}:{part}[§{section}]` | authority、source notes（含 `Pub. L.` 与 `U.S.C.` 引用）、currentness、FR 引文 |
| USC | `USC:{title}:{section}` | source_credit、amendments、status、official_url |
| PL | `PL:{congress}-{num}` | Statutes at Large citation、enactment date、title |
| NIM | `NIM:{id}` | base directive、国家、语文、类型 |
| Basel | 文件符号 | 状态（draft/final/adopted）、届会 |
| OECD | `C(OECD):{number}` | 类型（decision/recommendation） |
| Standards | `STD:{publisher}:{number}` | open_access_status、status |

### 5.3 执行路径

- FR 单文档 API（**已实测 200**）→ `scripts/backfill_policy_metadata.py` 扩展富化（默认 dry-run；overlay 增量；不改 raw）。
- FR→CFR：`cfr_references` 生成 `codified_in` 边；eCFR 侧结构核验组成（双源交叉）。
- CFR→USC/PL：解析 eCFR part XML 的 `AUTH`/`SRC` 注记 → `authorized_by`(USC) / `implemented_by`(PL)。
- 度量：before/after completeness（§12 输出）+ `identity_us.py` 单测。

---

## 6. P0-5 instrument_type 精度 —— 设计

1. 产物 `outputs/audit/instrument_mismatches.json`：逐案例
   `{case_id, expected, actual, matched_signal, source_id, reason_category}`。
2. 原因分类（固定枚举）：`TITLE_INSUFFICIENT` / `NIM_METADATA_INSUFFICIENT` /
   `UNKNOWN_DOCUMENT_CLASS` / `RULE_MAPPING_ERROR` / `SOURCE_METADATA_MISSING`。
3. 判定顺序升级（**metadata-first**）：
   ① 官方元数据（FR `type`：Rule/Proposed Rule/Notice；EUR-Lex act type；NIM 文书类型）
   → ② 规则（YAML patterns）
   → ③ AI 辅助（**仅建议 classification，不得单点决定 binding force**）。
4. `detect_instrument(title, text, meta=None)` 向后兼容（旧调用不改）。
5. 目标 ≥0.95；真实不足 → PARTIAL + 原因表，**禁止**写死标题或 URL 硬编码。
6. 已知待处理：NIM 记录（捷克令等）当前缺类型信号；若官方案卷类型可用则修正（goldset 期望同步修正并附理由）。

---

## 7. P0-6 Gold Set 扩充 —— 设计

新增（每条必须写：**为何加入 / 来源 / expected_class 为何成立**）：

| 类型 | 数量要求 | 来源与纪律 |
|---|---|---|
| A1 正例 | ≥5（holdout ≥2） | 仅真实文书：EU 针对 EV 电池的授权/实施法案（如碳足迹/SOH 类）+ 成员国 EV 电池专项令 + US/州级 EV 电池专条（经 live 发现验证） |
| hard B | ≥2 | 标题**无** battery，但正文条款直接约束电池回收（危废/运输/海关/许可） |
| hard D | ≥2 | 「看似高度相关」但不得进主库（科普/信息页/行业文章/纯程序性文书） |

- holdout 纪律不变：开发规则时不得引用 holdout 内容。
- 若真实可达源不足 5 条 A1 → **PARTIAL 如实输出**，不造假。
- 修改 Gold Set 必须在报告 §8 附变更说明（逐条）。

---

## 8. P0-7 Legal Family 关闭 —— 设计

1. 官方证据源：**Cellar SPARQL（已实测 200）** + EUR-Lex 页面关系。
2. 对 4 个 P0 root 逐 relation 输出：
   `root / relation / expected / found / official_evidence(URI|CELEX) / status ∈ {resolved, absent_official, not_checked}`。
3. 具体要求：
   - `32000L0053`(ELV)：`AMENDS`（真实修订法，如 2005/437/EC 等，经 SPARQL 确认后采集入库）、
     `CORRIGENDUM_OF`（SPARQL/页面为准：有则采集，**官方确无**则记 `absent_official` 并从 expected 移除，附证据 URL）；
   - `32006L0066`：`REPEALS`（自 2023/1542 的官方关系）、`AMENDS`（2008/103/EC、2013/56/EU 等经确认后采集）。
4. 新成员一律走既有采集通道入库（保持 raw 不可变 + 判定链）。
5. 目标 `P0 unresolved = 0`（= resolved 或 absent_official 且有证据）。

---

## 9. P0-8 LIVE Discovery Rounds —— 设计

### 9.1 轮次记录 schema（`outputs/discovery_rounds/round_{scope}_{n}_{ts}.json`）

```json
{
  "schema_version": "phase4b1.v1",
  "round_id": "EU_SUPRANATIONAL-2026-09-13-01",
  "scope_level": "SUPRANATIONAL",
  "started_at": "...", "ended_at": "...",
  "source_roles": ["EURLEX_PRIMARY", "..."],
  "routes": [
    {"id": "A", "name": "official_enumeration",
     "queries": ["..."], "raw_found": 0, "new_unique_documents": 0,
     "accepted": {"A1": 0, "A2": 0, "B": 0, "C": 0, "D": 0},
     "duplicates": 0,
     "source_failures": [{"source": "...", "failure_kind": "HTTP_403", "note": "..."}]}
  ],
  "totals": {"raw_found": 0, "new_unique_documents": 0, "new_unique_accepted": 0,
             "duplicates": 0, "source_failures": 0},
  "novel_rate": 0.0,
  "notes": "..."
}
```

### 9.2 四条独立 route（同一 API 换关键词不算独立）

| Route | 执行器（复用） | 说明 |
|---|---|---|
| A 官方枚举 | FR 机构枚举 · eCFR parts/structure · govinfo PLAW 清单 · EUR-Lex CELEX 批扫 · NIM 索引 | 结构化清单，不依赖关键词 |
| B 母语全文检索 | FR `conditions[term]`（**引号短语**）· eCFR search API · EUR-Lex keyword（EN/FR/DE） | 检索词按母语真值语言模型配置 |
| C 法律关系扩张 | **Cellar SPARQL**（`eur_lex.fetch_relations`）→ 按 CELEX 回采新文书 | 从 P0 root 出发找修订/废除/增补/更正 |
| D 开放网缺口发现 | Basel/OECD/CBP CROSS/BIS/标准 references 的官方页抓取 + 发现清单 | 付费墙/403 → SOURCE_FAILURE |

### 9.3 计算与纪律

- `novel_rate = new_unique_accepted_documents / max(1, raw_found)`（**分子=新且被接受**，非原始搜索结果）。
- 去重基准：库内既有 `evidence_id` 集合 + 本轮内去重；`duplicates` 单列。
- 收敛：连续 ≥2 轮 `novel_rate < 2%`；**含 source_failure 的轮次不得作为收敛证据**。
- 执行：`scripts/run_discovery_round.py --scope EU_SUPRANATIONAL|US_FEDERAL --round N --routes A,B,C,D`（有界限额，实际联网）。
- 每轮结束自动：分类计数（`acceptance.classify_record`）→ 追加 `outputs/audit/discovery_rounds.json` 索引 → 写 `feedback_state` 兼容的轮次记录（避免与现有引擎冲突：只追加 `history` 风格只读汇总或独立文件）。
- SG8 读取升级：saturation 的 `_novelty_stats` 改为读**本阶段 rounds 索引**（回退兼容 `feedback_state.history`）。

---

## 10. P1 支撑项设计

1. **backfill 扩展**：新增 `--region`、`--source-role`、`--only-missing`、`--limit`；输出
   `before completeness / after completeness / failed / ambiguous / human review required`；仍默认 dry-run + overlay。
2. **scope-level saturation**：
   - 新函数 `evaluate_scope_saturation(scope)`，scope ∈ {`EU_SUPRANATIONAL`, `EU_MEMBER_STATES`, `US_FEDERAL`, `US_STATES`}；
   - 现有 `evaluate_saturation(region)` 保留（兼容 46 条旧测试）；
   - SG1 按 scope 过滤角色；SG5 按 scope 过滤记录；输出禁止把 US Federal 标为 "United States complete"。
3. **Black Mass 六线矩阵**（`app/policy/black_mass.py` + `scripts/audit_black_mass_coverage.py` →
   `outputs/audit/black_mass_coverage.json`）：六线 × {region, source_role, documents[], best_evidence, status, gap}；
   status ∈ {COVERED, PARTIAL, MISSING, BLOCKED}。六线：废物定性 / 危废定性 / 运输 / 越境转移 / 海关贸易 / 再生料-废物终结。
4. **Failure taxonomy**（`app/policy/source_probe.py`）：
   `HTTP_403_BLOCKED · HTTP_429_RATE_LIMIT · CAPTCHA_CHALLENGE · API_KEY_REQUIRED · TIMEOUT ·
   DNS_ERROR · TLS_ERROR · PARSER_FAILURE · ROBOTS_RESTRICTION · PAYWALL · UNSUPPORTED_FILE`；
   提供 `classify_failure(...)` 与 `is_source_failure()`；纯 `zero_results` 单独类型 `ZERO_RESULTS`（≠失败）。

---

## 11. 测试计划（`tests/phase4b1/`，14 文件）

| 文件 | 覆盖 |
|---|---|
| `test_ecfr_identity.py` | CFR canonical id、authority/source/currentness 解析 |
| `test_fr_cfr_link.py` | FR→CFR `codified_in`（真实样本 2019-03812 等） |
| `test_usc_identity.py` | `USC:{title}:{section}` 与字段完整性 |
| `test_public_law_relation.py` | `AUTHORIZES/AMENDS/CODIFIED_AS/IMPLEMENTED_BY` 四关系 |
| `test_cbp_instrument_type.py` | CBP 裁定不得判 regulation |
| `test_bis_instrument_type.py` | BIS rule/notice/order/guidance 区分 |
| `test_basel_status.py` | draft ≠ final ≠ binding |
| `test_oecd_status.py` | decision/binding vs guidance/information |
| `test_standard_access_status.py` | 四值枚举 + paywalled 不得 fulltext + 无条款证据→非 B |
| `test_identity_backfill.py` | 新参数 + before/after + dry-run 默认 + raw 不动 |
| `test_live_round_schema.py` | round schema 完整性 + **failure ≠ 0 结果** |
| `test_novel_rate_live.py` | novel_rate 公式 + ≥2 轮收敛 + failure 轮不算 |
| `test_scope_level_saturation.py` | 4 scope 独立 + 禁止把 FEDERAL 当 US complete |
| `test_black_mass_coverage.py` | 六线存在 + status 枚举 + 每线有证据或 gap 理由 |

**回归保留**：Phase 4A 46 条 + 旧 21/21 + 20/20 + 5/5 全绿（不修改其断言）。

---

## 12. 交付物清单（文件级）

```
新增 sources/source-endpoints.yaml
修改 sources/jurisdiction-registry.yaml        （critical 标志 + 状态/端点/block_reason 校准）
修改 sources/policy-goldset.yaml               （A1 ≥5 含 holdout ≥2 + hard B/D）

新增 app/connectors/ecfr.py / govinfo.py / cbp_cross.py / bis.py / basel.py / oecd.py / standards_ref.py
修改 app/connectors/us_federal.py              （FIELDS 扩展为身份富化字段；行为向后兼容）

新增 app/policy/source_probe.py                （failure taxonomy + probe）
新增 app/policy/identity_us.py                 （FR/eCFR/USC/PL 身份与关系）
新增 app/policy/black_mass.py                  （六线矩阵）
修改 app/policy/instruments.py                 （metadata-first，兼容旧调用）
修改 app/policy/legal_graph.py                 （官方证据字段 + US 关系 + absent_official）
修改 app/policy/saturation.py                  （scope_level + SG8 读 rounds）
修改 app/policy/source_universe.py             （消费 endpoints + critical + probe 状态）

新增 scripts/audit_source_roles.py             （P0-1 矩阵 JSON+CSV）
新增 scripts/run_discovery_round.py            （P0-8）
新增 scripts/audit_black_mass_coverage.py      （P1-3）
修改 scripts/backfill_policy_metadata.py       （P1-1 参数与度量）
修改 scripts/audit_policy_saturation.py        （--scope）

新增 tests/phase4b1/（14 个文件）
新增 docs/phase4b1/00_PHASE4B1_PLAN.md（本文件）
后置 docs/phase4b1/PHASE4B1_CORE_SOURCE_CLOSURE_REPORT.md（16 节）

产物 outputs/audit/source_role_gap_matrix.{json,csv} / instrument_mismatches.json /
     legal_family_status.json（更新）/ black_mass_coverage.json / discovery_rounds.json（+目录）
     outputs/policy_metadata_overlay.jsonl（--apply 后，增量）
```

---

## 13. 验收标准（§18 原文固化，不得降低）

```
EU_SUPRANATIONAL critical source roles = 100%
US_FEDERAL critical source roles = 100%
P0 legal family unresolved = 0
A1 Gold Set >= 5 且 holdout >= 2
instrument_type_accuracy >= 0.95
US Federal identity completeness >= 90%
EU supranational identity completeness >= 95%
LIVE discovery rounds >= 3
independent discovery routes >= 3
source failure != zero-result
Black Mass 6-line coverage 可量化
```

达不成 → 如实输出 **PARTIAL**；`status_from()` 判定继续保持「0 结果/失败 ≠ SATURATED」不变式。

---

## 14. 实施顺序（每步含验证出口，不合格不进下一步）

| Step | 内容 | 出口验证 |
|---|---|---|
| 0 | 本计划（已完成） | 用户确认后进入编码 |
| 1 | P0-1 矩阵 + endpoints 配置 + failure taxonomy + probe | 矩阵可复现；BLOCKED 有真实失败证据 |
| 2 | P0-4 FR 身份富化（单文档 API）+ backfill 扩展 | US 身份率第一跳；overlay dry-run 报告 |
| 3 | P0-2 eCFR 连接器 + FR→CFR 链 | ≥3 真实 FR→CFR 案例 + 单测 |
| 4 | P0-2 USC + PL（govinfo 路径验证→连接器） | 7–10 真实样本入库 + 四关系单测 |
| 5 | P0-2 CBP + BIS | instrument 区分样本 + 单测 |
| 6 | P0-3 Basel + OECD + Standards(metadata) | draft/binding 区分；open_access_status 四值 |
| 7 | P0-7 家族关闭（SPARQL 证据） | unresolved=0 或 absent_official + 证据 |
| 8 | P0-5 instrument 精度修复 | mismatches.json + 目标 ≥0.95 |
| 9 | P0-6 Gold Set 扩充（与 live 发现绑定） | A1 ≥5 / holdout ≥2 / hard 案例验证 |
| 10 | P0-8 LIVE 轮次 ×3 → scope 饱和 → 黑粉矩阵 → 报告 + 终端摘要 | §19/§20 输出 |

---

## 15. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 新连接器误伤旧判定链 | 新源只**新增**记录；全部走现有 `classify_record`；不触碰旧通道 |
| FR FIELDS 扩展改变既有行为 | 只加字段读取；`fetch()` 签名不变；回归 21/20/5 全绿 |
| govinfo/CROSS 结构不稳定 | 每个源固定 3–10 真实样本进测试夹具；解析失败→`PARSER_FAILURE` 而非 0 结果 |
| 标准层不可达（CEN 500 / ISO 403） | metadata-only + 官方 references 兜底；诚实记 BLOCKED 局部 |
| A1 真实样本不足 | PARTIAL 如实输出（不造假、不写死标题） |
| 轮次网络失败 | 失败轮标记 `source_failures>0` → 不作收敛证据；补跑 |
| overlay 写入 | 默认 dry-run；`--apply` 保留旧行合并；raw evidence 永不改写 |

---

## 16. 待用户确认（不阻塞 Step 1，可在实施中答复）

1. **标准层口径**：CEN 门户 500 / ISO 403 现状下，STANDARDS 角色以「官方 metadata + EU 官方 references（OJ 实施决定/JRC）」认定 `metadata_available=true`，全文一律标记 `paywalled_known / official_metadata_only` —— 是否符合「核心标准 metadata」预期？
2. **A1 样本源**：若 live 发现确认 A1 真实文书 <5 条，将如实 PARTIAL（不禁忌从成员国/州级找 EV 电池专条，但仍不启动 27 国/50 州**全面**采集）。
3. **OECD 主站 403**：本阶段仅用 legalinstruments 子域（可达），主站内容记 BLOCKED —— 是否接受？

---

*本计划为 Phase 4B-1 的唯一施工蓝图；一切实现严格按 §14 顺序与 §13 标准执行，真实结果优先。*
