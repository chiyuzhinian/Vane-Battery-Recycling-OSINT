# Phase 4B-2A — Jurisdiction Onboarding Framework · 执行计划

> 阶段名：**Phase 4B-2A**（正式）｜ 模式：**Plan / Audit 先行，未写一行业务代码**
> 基线：Phase 4B-1 最终提交 `1de0747`（CONDITIONAL PASS；HEAD 干净）
> 输入证据：`docs/phase4b1/PHASE4B1_CORE_SOURCE_CLOSURE_REPORT.md` + `outputs/audit/*`（矩阵 / 轮次 / 饱和 / 黑粉）
> 边界重申：**不修改 Phase 4B-1 的任何历史结果**（`outputs/discovery_rounds/*.json`、报告、矩阵文件一律只读）；
> 不重写既有 connector（DE/NL/ES/FR 专线、eur_lex、us_*、basel 通道全部复用）；
> 不重设计 relevance / acceptance / review overlay / feedback / raw evidence 架构。
> 本阶段只做：**协议修正 → 契约建立 → 参考管辖地映射 → pilot 接入 → 覆盖矩阵 → LIVE 验证**。

---

## 0. Inspect 回执（已读文件 + 已做真实探测）

### 0.1 已读（本阶段直接接触面全量点名）

| 类别 | 文件 | 关键结论（对本阶段的影响） |
|---|---|---|
| 报告 | `docs/phase4b1/PHASE4B1_CORE_SOURCE_CLOSURE_REPORT.md` | EU/US 轮次未收敛的真实原因（query taxonomy 换词 / CELEX 年段扩张）→ 本阶段 §2 协议修正的直接动因 |
| 轮次 | `app/policy/rounds.py` | `convergence_status()` 现状：仅看 `source_failures==0` + `accepted_novelty_rate<2%`；**无 plan 绑定、无 mode、无 validity、无 class 级计数** → 扩展点明确 |
| 轮次 | `scripts/run_discovery_round.py` | `QUERY_SETS` 按轮号换词（R1/R2/R3 完全不同词组）→ **同一 streak 内搜索空间实际每轮都在漂移**（协议缺陷坐实）；轮次 JSON 无 plan 字段 |
| 饱和 | `app/policy/scope_saturation.py` | `scope_novelty()` 读 `discovery_rounds.json` 的 `convergence`；scope 枚举 4 个 → 需支持 jurisdiction 级 scope |
| 饱和 | `app/policy/saturation.py` | `THRESHOLDS`（SG1 95/100、SG5 99、SG8 0.02×2 轮）→ SG8 需接新协议字段 |
| 矩阵 | `scripts/audit_source_roles.py` | 角色行由 registry + probe + alias 反推；`_SUB_NATIONAL_ROLES` 已防联邦口径混入 → jurisdiction 级扩展开关在此 |
| 注册 | `sources/jurisdiction-registry.yaml` | EU_27（27 国，4 国 CONNECTED）+ US_STATES（51 州，仅 CA PARTIAL）；`role_schema` 已存在但**未与 contract 统一** |
| 端点 | `sources/source-endpoints.yaml` | 24 个 role 定义（含 MEMBER_STATE_LEGISLATION 4 国端点）；结构 = role → endpoints(capabilities/probe) → 可直接作为 onboarding 的子结构 |
| 配置 | `app/policy/config.py` | Pydantic fail-fast 模式（Topic/SourceRole/Endpoint/RoleEndpoints/Alias…）→ 新 contract 沿用同一纪律 |
| 连接器 | `app/connectors/{gesetze_de,bwb_nl,boe_es,dila_fr}.py` | DE/NL/ES/FR 专线已存在 → **只做 adapter/registry 集成，不重写** |
| 采集器 | `app/policy/source_universe.py` | `has_collector()` 按前缀（`de_/nl_/es_/fr_/us_/int_/eu_nim_/browser_`）自动识别 → 新 jurisdiction source 命名沿用前缀约定即可被识别 |
| 黑粉 | `app/policy/black_mass.py` | `build_coverage(records, region=)` 仅支持 global/EU/US → 扩展 jurisdiction 参数 |
| 身份 | `app/policy/backfill.py` | `region_of()` 仅 EU/US/OTHER；US 前缀会把所有 `us_*`（含未来州级）吞进 "US" → 需新增 `jurisdiction_of()` |
| 环境 | `.venv\Scripts\python.exe`（3.12.10）+ `py` 双可用 | 测试/脚本命令两套环境均需可跑 |
| 测试 | `tests/phase4b1/`（22 文件 133 条）+ `tests/policy/`（46 条）= **179 passed** | 新测试放 `tests/phase4b2a/`，同 pytest 风格 |

### 0.2 Plan Mode 真实探测（2026-09-13，只读 GET，44 端点，产物 `outputs/audit/jurisdiction_pilot_probe.json`）

**EU 成员国候选（22 国官方源首页）**——HTTP 200 共 19/22：

| 候选 | 状态 | 读取特征 | 备注 |
|---|---|---|---|
| SE-SFST（rkrattsbaser.gov.se） | ✅ 200 | 服务端渲染，瑞典语 | 可解析 |
| DK-RETSINFO | ✅ 200 | 服务端渲染 | 可解析 |
| FI-FINLEX | ✅ 200 | 大 HTML | 可解析 |
| IT-NORMATTIVA | ✅ 200 | 服务端渲染 | 可解析 |
| BE-EJUSTICE | ✅ 200 | 经典 CGI | 三语注记 |
| IE-STATUTEBOOK | ✅ 200 | 服务端渲染，英语 | 可解析 |
| HR-NARODNE（NN 检索） | ✅ 200 | 586KB 经典 ASP.NET | 可解析 |
| LV-LIKUMI | ✅ 200 | 服务端渲染 | 可解析 |
| EE-RIIGITEATAJA | ✅ 200 | 服务端渲染 | 官方 API 已知可用 |
| GR-ET | ✅ 200 | 204KB，希腊语 | 可解析 |
| MT-LEGISLATION | ✅ 200 | 马耳他语/英语 | 可解析 |
| SI-PISRS | ✅ 200 | 斯洛文尼亚语 | 可解析 |
| CY-CYLAW | ✅ 200 | windows-1253 编码 | 编码多样性样本 |
| RO-MONITOR | ✅ 200 | 453KB | 公报型 |
| LT-ESEIMAS | ✅ 200 | 210B shell | 需深页验证 |
| BG-DV | ✅ 200 | 1.6KB shell | 需深页验证 |
| LU-LEGILUX / SK-SLOVLEX / PT-DRE | ⚠️ 200 但 SPA shell | JS 渲染可疑 | 与 OECD 同类挑战 |
| AT-RIS | ⚠️ 503 "Security Check" | bot 防护 | 需重试/浏览器 |
| PL-ISAP | ⚠️ 404（路径需修正） | — | 波兰 = 电池产业重镇，**保留为高价值备选** |
| HU-NJT | ❌ RemoteProtocolError | — | 匈牙利 = CATL/Samsung 基地，**保留为高价值备选** |

**US 州候选（16 立法 + 6 环保署）**——HTTP 200 共 14/22：

| 候选 | 状态 | 备注 |
|---|---|---|
| CA-LEGINFO | ✅ 200（163KB） | 加州立法全文站 |
| CO-LEG | ✅ 200 | 电池 EPR 信号州 |
| ME-LEG | ✅ 200 | 电池 EPR 法州 |
| MN-REVISOR / MN-PCA | ✅ 200 / ✅ 200 | 电池 EPR 法州（立法+环保署双通道） |
| WA-RCW / WA-ECOLOGY | ✅ 200 / ✅ 200 | 电池管理法州（立法+环保署双通道） |
| AZ-LEG | ✅ 200 | 结构多样性 |
| GA-LEG | ⚠️ 200 SPA shell | JS 渲染挑战样本 |
| NY-SENATE / NY-DEC | ⚠️ 403 Cloudflare "Just a moment" | 浏览器通道候选 |
| NV-LEG | ⚠️ 403 Cloudflare | — |
| CA-CALRECYCLE | ⚠️ 403 Cloudflare（Phase 4B-1 已知） | 已有浏览器通道 `browser_calrecycle` |
| MI-EGLE | ⚠️ 403 Access Denied | MI = 电池法+回收产业双重信号 → **hard case 保留** |
| MI-LEG / IL-ILGA / MA / NJ / PA / OH / TX | ❌ ConnectTimeout/Error（**本环境网络限制，非源死亡**） | 需重试/浏览器；IL 有电池法信号 → 保留备选 |

> 纪律：以上 ❌/⚠️ **不得记为源不可用**——Step 3 将对候选做带重试的二轮探测；仍失败者按
> failure taxonomy 记录到该 jurisdiction 的 **blocked_endpoints（端点级）**，角色存活按替代通道判定（Phase 4B-1 口径延续）。

---

## 1. 目标与非目标

### 1.1 本阶段真正目标（用户裁定）

建立一个**可复制的 Jurisdiction Onboarding Framework**，使未来增加任何国家/州（Germany / Poland / California / Michigan …）
**不需要重新设计采集系统**，标准流程固定为：

```
Jurisdiction Registry → Official Source Mapping → Source Proof → Real Samples → Connector
→ Legal Identity → Acceptance → Legal Family → Gold Cases → LIVE Discovery
→ Coverage Audit → Convergence → Saturation
```

### 1.2 成功标准（**不是** 27 国/50 州全 SATURATED）

1. **Onboarding Framework 被真实验证**：不同语言、不同数据结构、不同国家/州可用同一流程接入；
2. **Convergence Protocol 修复**：搜索空间变化不再污染连续轮次（§2）；
3. **Pilot 得到可信 coverage**：每个 pilot 产出 source proof + 覆盖矩阵 + 可解释的 convergence 状态。

### 1.3 非目标

- ❌ EU 27 全覆盖、US 51 州全覆盖（那是 4B-2B，需本阶段 READY 才启动）；
- ❌ 追求政策条数、追求全部 SATURATED；
- ❌ 为 PASS 修改 Phase 4B-1 历史结果或降低任何阈值。

---

## 2. 第一优先级：Convergence 实验协议修正（Search Plan Versioning）

### 2.1 问题坐实（Phase 4B-1 真实数据）

| 现象 | 证据 | 结论 |
|---|---|---|
| EU R3 扩大 CELEX 年段 | R3 新增 3 条 CELEX（novelty 0.15 回升） | 搜索空间变化被计入同一 streak |
| US R3 更换 query taxonomy | `QUERY_SETS` R1/R2/R3 词组完全不同；R3 novelty 0.1333 回升 | 同上 |
| 瞬态 ConnectError | US R1 1 次 / R3 2 次（FR agency 枚举） | 网络故障被当作"无新增"，且失败轮直接 break streak（规则粗糙） |

### 2.2 Search Plan 模型（新增）

**每一轮 LIVE discovery 必须绑定 `search_plan_id` + `search_plan_hash`。**

```
SearchPlan（sources/search-plans/{plan_id}.yaml，Pydantic fail-fast）
  plan_id                 如 EU_SUPRA_PLAN_V1 / US_FED_PLAN_V1 / DE_PLAN_V1 / US-CA_PLAN_V1
  jurisdiction            绑定的 jurisdiction_id
  scope                   EU_SUPRANATIONAL / EU_MEMBER_STATES / US_FEDERAL / US_STATES / jurisdiction 级
  source_roles[]          参与角色（冻结列表）
  source_endpoints[]      参与端点（冻结列表；含 critical 标注）
  query_taxonomy_version  如 qt-v1（查询词表随 plan 冻结，见下）
  query_set{}             冻结的实际词表（FR terms / 当地语言 terms / CELEX 段 / CROSS terms …）
  language_set[]          语言集合（如 [de, en]）
  time_window             {from: 2024-01-01, to: 2026-12-31}（冻结）
  year_segments[]         如 ["32024R","32025R","32026R"]（冻结）
  discovery_routes[]      [A,B,C,D] 冻结
  acceptance_rule_version 取自 policy-acceptance-rules.yaml version
  dedupe_rule_version     DEDUPE_RULE_VERSION 常量（evidence_id + celex 双键，文档化）
```

**hash 算法**：对上述全部字段做规范化 JSON（sort_keys、去空白）→ **sha256** → `plan_hash`。
hash **不含** `created_at` / 备注等非语义字段（避免伪变化）。

### 2.3 搜索空间变化 → 强制 RESET

以下任意变化必须产生**新 plan_id/plan_hash**，并把 `convergence_reset = true` 记入轮次索引：

```
新增关键词簇 ｜ 新增 source role ｜ 新增 jurisdiction ｜ 新增 language
｜ 扩大 year range ｜ 新增 legal-family route ｜ 新增 API/connector
｜ 修改 acceptance rules ｜ 修改 dedupe rules
```

实现层强制：`run_discovery_round.py --plan {plan_id}` 装载 plan → 运行时计算 hash → 写入轮次 JSON；
`convergence_status()` **只接受同 hash 的轮次**组成 streak，混 plan 的轮次自动截断并标 `reset=true`。

### 2.4 两种 LIVE 模式（语义分离）

| 模式 | 目的 | 是否计入 streak |
|---|---|---|
| **MODE A — DISCOVERY_EXPANSION** | 扩源/扩词/扩语言/扩年份/扩法律家族（允许大发现） | ❌ **不参与**（仅记录、支撑 source proof） |
| **MODE B — CONVERGENCE_VALIDATION** | 冻结 universe 下验证边际新颖度 | ✅ 唯一可用于 SG8 |

MODE B 前置条件（全部满足才可启动）：source universe frozen + query taxonomy frozen + language frozen +
time range frozen + routes frozen + acceptance frozen + dedupe frozen（即：plan_hash 冻结）。

### 2.5 指标与轮次级字段（双指标 + class 级计数）

```
raw_yield             = new_unique_accepted / raw_result_count        （检索效率，不得单独证明饱和）
accepted_novelty_rate = new_unique_accepted / (new + duplicate_accepted)   （SG8 主判据）

每轮新增独立记录：
  new_A1 / new_A2 / new_B / new_C / new_D
  new_high_risk_B      （B 中命中 T01/T02/T05/T10/T13 者，按 acceptance topic 输出）
```

**高价值新颖度护栏**：即使 `accepted_novelty_rate` 很低，只要最近有效轮仍有 `new_A1 > 0`
或 `new_high_risk_B > 0`，**不得宣布 SATURATED**（convergence_status 输出 `blocked_by_high_value` 字段，
SG8 判 pass 时必须同时检查）。

### 2.6 Round Validity（失败轮判定细化）

```
FULL    所有 critical Source Roles 正常完成（瞬态失败已重试成功 → 仍 FULL，记 transient_failures）
PARTIAL 非 critical 端点失败，但 critical Roles 全部完成（可用于局部分析；
        ★ 是否计入 scope convergence：**不计入**，保守口径，写死并测试锁定）
INVALID 任意 critical Source Role：timeout / connect error / 403 / parser failure / schema failure
        且重试后仍未完成 → 本轮未完成 → **不得计入 streak**（也不得解释为"没有新增结果"）
```

重试策略：每个端点内置重试 1 次（退避 2s）；**重试成功记 `transient_failures`（不判无效）**。
critical 角色清单 = plan 内标注（来自 endpoints registry 的 critical 集合 ∩ plan.source_roles）。

### 2.7 历史轮次的处理（不改历史）

- 新增只读审计：`scripts/audit_convergence_protocol.py` → `outputs/audit/convergence_recheck.json`；
- 对 Phase 4B-1 的 6 个轮次（US R1–R3 / EU R1–R3）按新规则**独立重新标记**：
  `legacy_plan=true`（无 plan 绑定）、`mode=legacy`、按失败明细给 validity 评级（US R1/R3 = PARTIAL：非 critical 端点级瞬态失败；
  critical Role `FEDERAL_REGISTER` 本体完成）——**并注明：无论评级如何，legacy 轮次均不参与新协议 streak**；
- `outputs/discovery_rounds/*.json` **零修改**；报告零修改。

---

## 3. Jurisdiction Onboarding Contract（统一数据契约）

### 3.1 载体

```
sources/jurisdiction-onboarding/{JURISDICTION_ID}.yaml     ← 每管辖区一个契约文件（唯一真源）
app/policy/jurisdiction_onboarding.py                      ← Pydantic 强校验 + 装载 + 校验 + registry 映射
```

### 3.2 契约字段（最小完备集）

```
jurisdiction_id            DE / NL / ES / FR / BE / SE / IT / EE / CY / US-CA / US-CO / …
jurisdiction_name          名称（中英）
level                      supranational | member_state | federal | state
official_languages[]       如 [de] / [fr, nl, de] / [sv] / [en]
legal_system_type          civil_law | common_law | mixed（成员国/州多样性维度）

mandatory_source_roles[]   见 §4 标准角色集
optional_source_roles[]

official_channel_map:      # 角色 → 官方通道（可多个）
  MS_LEGISLATION_DATABASE: [{source_id, official_url, access_method}]
  MS_OFFICIAL_GAZETTE:     […]
  national_legislation:    […]
  environment_authority:   […]
  transport_authority:     […]
  customs_trade:           […]
  standards:               […]
  waste_authority:         […]
  (US 州：STATE_LEGISLATURE / STATE_STATUTES / STATE_ADMIN_CODE / STATE_REGISTER /
   STATE_ENVIRONMENT_AGENCY / STATE_WASTE_PROGRAM / STATE_BATTERY_EPR / STATE_TRANSPORT_HAZMAT
   / STATE_TAX_INCENTIVES / STATE_RECYCLING_PROGRAM)

collector_strategy         connector | browser | nim_discovery | manual_review 组合（每源声明）
identity_strategy          官方主键格式（如 "DE:GG:{abk}" / "US-CA:CCR:{title}:{section}"）+ 富化字段
status_strategy            状态字段来源（官方 metadata：in-force / amended / repealed）
legal_relation_strategy    NIM/家族/修订链 的映射方式（成员国用 EU 家族；州用州法修订链）
```

**校验规则（fail-fast）**：
1. `jurisdiction_id` 必须在 runtime registry 中存在（或由本契约注册）；
2. `mandatory_source_roles` 必须覆盖 §4 角色集（缺一个 → 装载报错，而不是静默降级）；
3. 每个 `official_channel_map` 条目必须能解析 `source_id` 前缀约定（`de_/nl_/pl_/us_ca_/…`）；
4. `optional_source_roles` 不得与 mandatory 重叠。

### 3.3 参考管辖地映射（不重写 connector）

DE / NL / ES / FR 的既有专线与 NIM 记录 → **写 4 份契约文件**（§3.1 路径），
`collector_strategy` 指向既有 connector（`gesetze_de/bwb_nl/boe_es/dila_fr`），
验证点：*旧 connector → 新 Source Role Framework 正常映射*（registry 反推矩阵不回归：DE/NL/ES/FR 仍 CONNECTED）。

### 3.4 记录级归属

新增 `app/policy/jurisdiction_map.py::jurisdiction_of(record)`：
`source_id 前缀 → jurisdiction_id`（`de_*→DE`、`us_ca_*→US-CA`、`eu_nim_pl_*→PL`），
其余回退 `backfill.region_of()`。**所有 jurisdiction 级矩阵（黑粉/主题/身份）都以此为切片口径。**

---

## 4. 标准 Source Roles

### 4.1 EU Member State（每国至少检查 7 项 + 2 项按需）

```
MS_LEGISLATION_DATABASE            国家立法数据库（官方）
MS_OFFICIAL_GAZETTE                官方公报
MS_ENVIRONMENT_MINISTRY_OR_AGENCY  环境部/环保署
MS_WASTE_REGULATOR                 废物监管机构
MS_TRANSPORT_OR_DANGEROUS_GOODS    运输/危货主管
MS_CUSTOMS_OR_TRADE                海关/贸易
MS_STANDARDS_METADATA              标准元数据（metadata-only 口径沿用 Phase 4B-1 五概念分离）
（按需）MS_EPR_AUTHORITY ｜ MS_ELV_AUTHORITY
```

### 4.2 US State（每州至少检查 8 项 + 2 项按需）

```
STATE_LEGISLATURE      州议会（法案）
STATE_STATUTES         州法典
STATE_ADMIN_CODE       州行政法规
STATE_REGISTER         州公报/登记
STATE_ENVIRONMENT_AGENCY 州环保署
STATE_WASTE_PROGRAM    州废物项目
STATE_BATTERY_EPR_OR_STEWARDSHIP 电池 EPR/管理法
STATE_TRANSPORT_HAZMAT 州危货运输
（按需）STATE_TAX_INCENTIVES ｜ STATE_RECYCLING_PROGRAM
```

### 4.3 两条代码级铁律（测试锁定）

1. **NIM = EU implementation discovery layer，不得替代 national law corpus**：NIM 记录只允许作发现线索
   （`discovery_layer=true`），不得计入 `MS_LEGISLATION_DATABASE` 的角色覆盖数；
2. **Federal Register / eCFR 不得替代 State law**：州级角色覆盖只能由州源证据支撑
   （现有 `_SUB_NATIONAL_ROLES` 防混入逻辑扩展为 jurisdiction 级断言）。

---

## 5. Pilot 选择（不拍脑袋，先评分）

### 5.1 jurisdiction_priority_score（输出 `outputs/audit/jurisdiction_priority.csv`）

| 维度 | 权重 | 数据来源 |
|---|---|---|
| battery_recycling_business_relevance | 25% | 电池产能/回收产业存在（已知事实，逐条注明） |
| EV_market_relevance | 15% | EV 保有/销量量级 |
| recycling_industry_presence | 10% | 回收/精炼设施存在 |
| known_policy_signal | 20% | 已知 EPR/电池法/黑粉政策信号（registry note + 人工核） |
| source_gap_risk | 10% | 现有覆盖缺口（矩阵） |
| official_source_accessibility | 10% | **真实探测**（§0.2 + Step 3 带重试二轮） |
| legal_system_diversity | 5% | civil/common/mixed、语言族、联邦-大区结构 |
| existing_connector_reuse | 5% | 可复用既有 connector 数量 |

**选择原则**：业务价值高 **+** 结构/语言/数据形态互不相同 **+** 可验证；**不是**挑最容易的。

### 5.2 Pilot 锁定（Step 3 实测评分产出，`jurisdiction_priority.csv`）

**评分口径**：8 维加权（battery 0.25 / EV 0.15 / recycling 0.10 / policy 0.20 /
gap-risk 0.10 / accessibility 0.10 / diversity 0.05 / reuse 0.05）；
约束：accessibility < 0.5 → 只能 RESERVE；US 州至少 2 个 policy_signal ≥ 4（A1 栖息地）。

**真实二轮带重试探测（2026-09-13）**：EU 21/22 达 200（PL 修正 URL 后 200）；
US 9/20 达 200（MI/IL/TN/TX/OH/OR/VT 本环境超时；NV/NY/NC 403 Cloudflare）；
HU 重试后仍 RemoteProtocolError、AT 503 → 均按**端点级**记录（不判死源）。

| 组 | 锁定 Pilot | 依据（分数/多样性/可达性） |
|---|---|---|
| EU 参考（4） | **DE / NL / ES / FR** | 既有专线；契约映射验证对象（不参与新选） |
| EU 新增（4） | **SE**（0.790；Nordic+生产者责任成熟）｜**PL**（0.700；LGES/Umicore 产业重镇，立法库可达）｜**BE**（0.680；三语+联邦/大区双层+Umicore 黑粉精炼）｜**FI**（0.660；电池材料+Fortum 回收） | 语言 [sv, pl, fr/nl/de, fi]、结构 [单一制/大区双层/官方 API]、编码互不相同 |
| EU stretch（1） | **EE**（diversity 1.0；Uralic+数字政府 API 最强） | 框架泛化压力测试 |
| EU 备选（RESERVE） | IT / SK / CZ / DK ｜ **HU / AT**（access<0.5：HU 协议错误、AT 503 → 需先修复通道） | 保持登记，通道修复后升格 |
| US 州（6） | **CA**（0.780；AB 2440+CalRecycle）｜**GA**（0.635；SK On/Hyundai 集群，SPA 挑战）｜**CO**（0.595；电池 EPR 法）｜**KY**（0.595；BlueOval SK）｜**MN**（0.585；EPR 法+MPCA 双通道）｜**WA**（0.575；政策活跃+RCW/Ecology 双通道） | 4 个 policy≥4（CA/CO/MN/WA）；制造带（GA/KY）与法规型州并重 |
| US 备选（RESERVE） | AZ / IN / SC / ME ｜ **MI / IL / NY**（access<0.5：403/超时 → 浏览器通道课题） | ME 保留（EPR 法州，通道可用待 Step 4 复核） |

---

## 6. Source Proof 工作流（禁止先写完整 collector）

每个新 jurisdiction 的每个 source 必须走完：

```
Source Mapping → endpoint probe（真实 HTTP）→ 3–10 真实文书样本
→ 确认 document identity → 确认 status metadata → 确认全文能力
→ 确认搜索/枚举能力 → 才允许开发 connector
```

**source_proof 产物**：`outputs/audit/source_proofs/{jurisdiction_id}.json`，逐 source 记录：

```
official_owner / official_domain / source_role / access_method
search_available / enumeration_available / metadata_available / fulltext_available
language / sample_urls[]（≥3 真实 URL）/ known_limitations[]
probe: {status, content_type, bytes, failure_type?}
verified_at（真实时间戳）
```

工具：扩展 `scripts/probe_source_endpoints.py` 支持 `--jurisdiction` 与 `--samples N`
（抓正文存 proof 引用，不入主库）；**样本不得伪造**：抓不到就记 failure（`NO_RESULTS ≠ SOURCE_FAILURE` 口径延续）。

---

## 7. 覆盖矩阵（取代"条数覆盖"）

### 7.1 每 jurisdiction 输出（`app/policy/jurisdiction_coverage.py` → `outputs/audit/jurisdiction_coverage.{json,csv}`）

```
Source Coverage     mandatory/critical 角色覆盖（矩阵口径，非条数）
Legal Identity      identity completeness（该 jurisdiction 记录切片）
Acceptance          A1/A2/B/C/D 分布（A1 另列 candidate pool）
Legal Family        家族闭合度（EU MS：NIM/家族映射；US 州：州法修订链；N/A 显式声明）
Gold Recall         该辖区相关 gold 案例 recall（数据不足则 INSUFFICIENT，如实）
Discovery Routes    独立路线数（A/B/C/D）
Novelty             accepted_novelty_rate + raw_yield（按 plan 分组）
Failures            INVALID/PARTIAL 轮次 + blocked_endpoints（端点级）
Saturation          SG 判定（jurisdiction 级 scope）
```

**文档数量仅作 descriptive statistic**：条数不得出现在覆盖率分子/分母。

### 7.2 Topic Matrix（T01–T14 真正启用）

`app/policy/topic_matrix.py` → 每 jurisdiction 输出 T01–T14 状态：

```
COVERED / PARTIAL / MISSING / BLOCKED / NOT_APPLICABLE
```

口径：基于 `regulatory-topics.yaml` 的 include_patterns 对该 jurisdiction 语料切片命中
＋ 强证据（A/B 类）判定；`NOT_APPLICABLE` 需注明理由（如联邦层无该主题）。

### 7.3 Black Mass 六线（jurisdiction 级）

扩展 `black_mass.build_coverage(records, jurisdiction=…)`：六线独立评估不变；
**支持 clause-level B relevance**（标题无 "black mass" 不得判无关——按正文条款命中 T 主题 + 条款证据）。

---

## 8. A1 Gold Set 原则（延续 4B-1，不降定义）

- A1 **不是数量任务**：随成员国/州级深采自然积累；
- 真实发现「明确针对 EV battery / traction battery / end-of-life vehicle battery / EV battery recycling / repurposing」的官方文书
  → 进入 **candidate pool**（`outputs/audit/a1_candidates.json` 机制复用）；
- **人工确认后**才可入 Gold Set；
- 若最终 A1 < 5 → 继续 `INSUFFICIENT_A1_GOLDSET`（**不得降低 A1 定义**）。

---

## 9. LIVE 测试协议（每 pilot）

```
阶段一：MODE A（DISCOVERY_EXPANSION）
  · 逐轮扩源/扩词/扩语言/扩年段（记录 reset 事件）
  · 直到：source universe stable 且 query taxonomy stable 且 legal-family expansion stable
    （stable 判据：连续 1 轮无新增 source/role/language/route；新增文档全部落在既有源）
阶段二：冻结 → 写入 plan 注册表（search_plan_hash 固定）
阶段三：MODE B（CONVERGENCE_VALIDATION）≥2 个连续有效轮次
  · 有效 = round_validity FULL 且 plan_hash 一致
  · 收敛 = 连续 ≥2 轮 accepted_novelty_rate < 2% 且无 high-value novelty（§2.5 护栏）
  · 不满足 → 如实 NOT_CONVERGED（禁止换词造"新一轮收敛"）
```

轮次索引扩展：`outputs/audit/discovery_rounds.json` 增设 `plan_id/plan_hash/mode/validity/transient_failures/reset`
（**历史条目保持原样**，新轮次带新字段；reader 向后兼容）。

---

## 10. Step 划分（每步：交付物 + 测试 + 真实运行 + 独立提交）

| Step | 内容 | 关键交付物 | 提交线 |
|---|---|---|---|
| **0** | 本计划 | `docs/phase4b2a/00_PHASE4B2A_PLAN.md` | ✅ 本文件 |
| **1** | Search Plan Versioning 引擎 + 协议回填 | `sources/search-plans/*.yaml`、`app/policy/search_plan.py`、`rounds.py` 扩展（plan_hash/mode/validity/class 计数/高价值护栏）、`run_discovery_round.py --plan/--mode`、`scripts/audit_convergence_protocol.py`（历史轮次只读重标记） | 全部本地可测，无网依赖 |
| **2** | Onboarding Contract + 参考管辖地映射 | `sources/jurisdiction-onboarding/{DE,NL,ES,FR}.yaml`、`app/policy/jurisdiction_onboarding.py`、`app/policy/jurisdiction_map.py`（jurisdiction_of） | 映射后矩阵不回归（DE/NL/ES/FR 仍 CONNECTED） |
| **3** | Priority 评分 + Pilot 锁定 | `scripts/audit_jurisdiction_priority.py` → `outputs/audit/jurisdiction_priority.csv`；带重试二轮探测；pilot 名单冻结（本文件更新 §5.2 实选） | 评分可复现 |
| **4** | Source Mapping + Source Proof（逐 pilot） | 每 pilot 的契约补全（official_channel_map）+ `scripts/probe_source_endpoints.py --jurisdiction --samples` + `outputs/audit/source_proofs/*.json`（真实 3–10 样本） | 每 pilot 一批提交 |
| **5** | Connector 开发（复用模式，小步） | `app/connectors/` 新连接器（每源一个提交）+ `scripts/collect_jurisdiction_sources.py`；母语解析；NIM 仅作 discovery | 每源：3–10 真实样本入库证据 |
| **6** | Identity + Acceptance + Topics 集成 | 每 pilot 官方主键格式、status metadata 解析、T01–T14 标签、`scripts/audit_jurisdiction_identity.py` | 身份完整度可量化 |
| **7** | Coverage Matrix 工具 | `app/policy/jurisdiction_coverage.py` + `topic_matrix.py` + black_mass jurisdiction 扩展 + 2 个 CLI | 每 pilot 矩阵可生成 |
| **8** | LIVE MODE A（逐 pilot） | 扩张轮次真实运行 → stable 判定 → plan hash 冻结（`outputs/audit/search_plan_registry.json`） | 每 pilot 提交轮次结果 |
| **9** | LIVE MODE B（逐 pilot） | ≥2 连续有效轮次 → convergence 状态（或如实 NOT_READY + 原因） | 收敛证据提交 |
| **10** | 最终报告 + 终端摘要 | `docs/phase4b2a/PHASE4B2A_JURISDICTION_ONBOARDING_REPORT.md`（回答 §12 的 12 问）+ 终端摘要（§12.3 格式） | 收尾提交 |

---

## 11. 验收目标（转译用户 §20）

| # | 验收项 | 判定 |
|---|---|---|
| 1 | Search Plan Versioning | COMPLETE（hash 覆盖全部规定字段 + 混 plan 截断 + 测试锁定） |
| 2 | Discovery Expansion / Convergence Validation 分离 | COMPLETE（MODE A 不入 SG8，测试锁定） |
| 3 | critical failure invalidation | COMPLETE（FULL/PARTIAL/INVALID + 重试语义 + 历史重标记产物） |
| 4 | EU 参考管辖地 DE/NL/ES/FR | 全部进入统一 onboarding framework（映射不回归） |
| 5 | 新增 EU pilot | ≥2（目标 4：BE/SE/IT/EE；stretch CY；备选 PL/HU 视探测） |
| 6 | US State pilot | ≥5（目标 6：CA/CO/ME/MN/WA/MI） |
| 7 | 每个 pilot source proof | COMPLETE（每源 3–10 真实样本 + 能力矩阵 + limitations） |
| 8 | 每个 pilot T01–T14 matrix | 可生成（5 态枚举） |
| 9 | 每个 pilot black mass 6-line matrix | 可生成（clause-level B 支持） |
| 10 | 每个 pilot identity completeness | 可量化（官方主键 + 富化字段） |
| 11 | 每个 pilot convergence status | 可解释（plan/mode/validity/novelty/护栏四要素齐备） |

**未尽（明确不做）**：27 国/51 州全覆盖、全 SATURATED、A1 数量凑数。

---

## 12. 最终报告与终端摘要

### 12.1 报告路径

```
docs/phase4b2a/PHASE4B2A_JURISDICTION_ONBOARDING_REPORT.md
```

### 12.2 报告必须回答（用户 §22，逐问对应章节）

1. Phase 4B-1 为什么没有收敛？→ §2.1 证据链
2. 哪些 Round 因 search universe 变化不能连续计算？→ `convergence_recheck.json` 摘要表
3. 新 Search Plan Versioning 如何解决？→ §2.2–2.6 + 实测轮次演示
4. 哪些 jurisdiction 被选为 pilot，为什么？→ §5 评分表 + 锁定名单
5. 每个 jurisdiction 的 Source Universe 是什么？→ `source_proofs/*.json` 汇总
6. 哪些 source 已经真实 probe？→ probe 矩阵（含 ❌/⚠️ 与重试结论）
7. 哪些 connector 真正跑出了真实政策？→ 每源样本数 + 入库 evidence 数（≠"URL 存在"）
8. T01–T14 哪些有覆盖？→ topic matrix
9. Black Mass 六线哪些覆盖？→ 六线矩阵（jurisdiction 级）
10. 哪些是 Known / Unknown / Blocked？→ 三态清单（blocked = 端点级 + 替代通道结论）
11. 哪些 jurisdiction 可以进入 convergence validation？→ stable 判据通过清单
12. Phase 4B-2B 是否 Ready？→ 结论（Ready 才可 27 国/51 州全覆盖）

### 12.3 终端摘要格式（用户 §23）

```
PHASE 4B-2A RESULT
Search Plan Versioning: PASS / FAIL
Convergence Protocol:   PASS / FAIL
EU Reference Jurisdictions: DE / NL / ES / FR → 各自状态
New EU Pilots:      …
US State Pilots:    …
Source Proof:       x/x complete
Topic Matrix:       x/x generated
Black Mass Matrix:  x/x generated
Convergence-ready jurisdictions: …
P0 blockers:        …
Phase 4B-2B:        READY / NOT READY
```

---

## 13. 禁止事项（用户开发原则 + 4B-1 纪律延续）

```
❌ 不追求国家数量——先证明接入模式可复用
❌ 不追求政策条数——追求 Source Universe 覆盖
❌ 不通过换词制造"新一轮收敛"——搜索空间变化必须 reset
❌ 不把网络失败当无结果（NO_RESULTS ≠ SOURCE_FAILURE）
❌ 不把 Federal complete 当 United States complete
❌ 不把 NIM complete 当 Member State complete
❌ 不为 PASS 修改 4B-1 历史或降低阈值；真实结果 PARTIAL/INVALID/NOT_READY 一律如实输出
❌ AI 不单独裁定 binding force；不为 metadata-only 标准生成条款证据
```

---

## 14. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 部分候选站点本环境超时/403（MI/IL/MA/NJ/PA/OH/TX/NY…） | 带重试二轮探测 + 浏览器通道策略（复用 `browser.py`）；仍失败按端点级 blocked 记录，**不判死 jurisdiction** |
| SPA 站点（GA/LU/SK/PT/AT）抽取困难 | 沿用 `SPA_JS_RENDERED` 口径 + 只取可见官方元数据/直链 PDF（metadata-only 允许） |
| 母语解析质量（希腊语/马耳他语/克罗地亚语） | 样本驱动开发（3–10 条真实文书先验）；解析不确定 → 降级 C 类背景语料，不伪造条款证据 |
| pilot 收敛慢（2 个有效轮可能不够） | 如实 NOT_READY + 原因清单；不换词造收敛 |
| 契约过度设计 | 契约字段最小完备（§3.2）；每个新 jurisdiction 只允许"填表"，不允许"改框架"（框架变更必须回到本计划评审） |
| 4B-1 参考专线回归 | Step 2 出口检查：DE/NL/ES/FR 矩阵状态与 Phase 4B-1 完全一致（快照比对） |

---

## 15. 测试计划（`tests/phase4b2a/`，预计 +40~60 条）

| 文件 | 锁定内容 |
|---|---|
| `test_search_plan_hash.py` | hash 覆盖 11 类字段；任一字段变化 → hash 变化；非语义字段不参与；plan 文件缺失/非法 → fail-fast |
| `test_convergence_reset.py` | 混 plan 轮次自动截断 + reset 标记；新 plan 从 streak=0 重开 |
| `test_round_validity.py` | critical 失败 → INVALID；非 critical 失败 → PARTIAL（不计 streak）；瞬态重试成功 → FULL + transient 记录 |
| `test_mode_separation.py` | MODE A 轮次不参与 SG8；MODE B 前置未冻结 → 拒绝运行 |
| `test_class_level_novelty.py` | new_A1..D 计数正确；high-value 护栏（最近有效轮 new_A1>0 → 不得 SATURATED） |
| `test_jurisdiction_contract.py` | 契约 fail-fast（role 缺项/ID 非法/重叠）；DE/NL/ES/FR 映射产物与 registry 一致 |
| `test_jurisdiction_roles.py` | EU MS 7+2 / US State 8+2 角色集完整；NIM≠corpus、FR≠State law 两条铁律 |
| `test_jurisdiction_map.py` | source_id 前缀 → jurisdiction 归属正确；us_* 联邦不被州级吞掉 |
| `test_topic_matrix.py` | T01–T14 五态枚举；NOT_APPLICABLE 需理由；无强证据不得 COVERED |
| `test_black_mass_jurisdiction.py` | jurisdiction 级六线；clause-level B（标题无关正文命中）；MISSING≠BLOCKED |
| `test_coverage_matrix.py` | 9 指标产物 schema；条数不进入覆盖分子/分母 |
| `test_convergence_recheck.py` | 历史轮次只读重标记正确；**历史 JSON 文件哈希不变**（防篡改断言） |

回归门槛：现有 179 条必须保持全绿（新旧协议向后兼容）。

---

## 16. 执行顺序与提交粒度

```
Step 1（协议）→ Step 2（契约+参考映射）→ Step 3（评分+Pilot 锁定）
→ Step 4（Source Proof）→ Step 5（Connector，逐源小步）→ Step 6（Identity/Acceptance/Topics）
→ Step 7（矩阵工具）→ Step 8（MODE A）→ Step 9（MODE B）→ Step 10（报告）
每步：独立测试 + 真实运行证据 + 独立提交；报告数字全部取自真实产物。
```

**当前状态：Step 0 完成（本文件）——等待放行后从 Step 1 开始，逐步推进。**

---

## 17. 执行回填（Step 7 / Step 8，2026-09-13）

### Step 7：管辖地覆盖矩阵工具

- `app/policy/jurisdiction_coverage.py` + `scripts/audit_jurisdiction_coverage.py`
  → `outputs/audit/jurisdiction_coverage.{json,csv}`
- 五态主题矩阵（T01–T14：COVERED/PARTIAL/MISSING/BLOCKED）、层级
  （ACTIVE/COLLECTED/BLOCKED/REFERENCE/NOT_ONBOARDED）、失败解析
  （同一 doc 成功记录出现 → 未决失败清零）、黑粉 jurisdiction 级。
- Step 8 语料增长后重跑：US-WA 升 ACTIVE（16 条 · B2）、US-CA 13 条 · B1、
  SE 25 条（身份 40%）、PL 保持 BLOCKED（NIM + Distil 未决失败 3）。

### Step 8：MODE A 发现轮（管辖地级）

- 端点注册表新增 4 角色（`SE/FI/US_CA/US_WA_*_LEGISLATION`）+ 端点经
  真实探测（探针记录 `outputs/_probe_step8*.py`）。
- 4 份管辖地级 plan 冻结（hash 已测试锁定）：`SE/FI/US_CA/US_WA_PLAN_V1`。
- `scripts/run_jurisdiction_round.py`：A 枚举 / B 检索 / C 引用扩展 / D 缺口；
  `DocNotFound` 与真实失败分离；引用抽取仅用**自有记录**（NIM 摘要为噪声源）；
  `not_found` 逐轮入档。
- 实跑 13 轮（2026-09-13）：

| 管辖地 | 轮次 | 新入选 | validity | 备注 |
|---|---|---|---|---|
| SE | R1–R3 | 7（C×7） | R1 PARTIAL※/R2·R3 FULL | fritext 检索（3 词）；C 引用种子 |
| FI | R1–R3 | 3（B×2+C×1） | FULL | 检索=客户端渲染（B 如实缺席）；引用链 R1 后饱和 |
| US-CA | R1–R3 | 1（C×1） | R1 PARTIAL※/R2·R3 FULL | 42451/42452 已入库（eid 对齐）；42453 新 |
| US-WA | R1–R4 | 14（B×2+C×12） | R1·R2 PARTIAL※/R3·R4 FULL | 引用链两级扩张后饱和 |

※ R1 记录早于 `not_found` 口径修正：其中"失败"实为**不存在文号/section**
（SE 3、US-CA 2），R2+ 已按负结果如实分离；12 个 R2+ 轮 validity 全 FULL。
所有轮 `round_mode=discovery_expansion`（MODE A，不入 SG8 streak），
plan_hash 与 plan 文件一致，索引见 `outputs/audit/discovery_rounds.json`。

- 引用链观察：SE C 引用 11 个不存在文号（负结果）；WA 引用链 R1→R2→R3
  依次发现 11→2→1 篇（衰减序列）；FI R2 起 0 新增。**四地均进入相对稳定态**。
