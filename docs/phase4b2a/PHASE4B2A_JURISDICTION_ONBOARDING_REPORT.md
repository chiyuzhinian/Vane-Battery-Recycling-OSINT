# Phase 4B-2A —— Jurisdiction Onboarding Framework 最终报告

> 分支：`phase4b2a` ｜ 日期：2026-09-13 ｜ 纪律：不改 4B-1 历史 · 不降阈值 ·
> 条数仅描述性统计 · PARTIAL/INVALID/BLOCKED 一律如实
> 证据：`outputs/audit/*`（矩阵 / 轮次 / 收敛 / 重标记 / proofs / 失败）

---

## 1. 摘要

本阶段交付**可复制的管辖地接入框架**（Onboarding Contract → Source Proof →
Connector → Search Plan → 轮次协议 → 覆盖矩阵），并以 4 个管辖地（SE / FI /
US-CA / US-WA）完成**端到端实证**：

- 协议修正（Search Plan Versioning + MODE 分离 + FULL/PARTIAL/INVALID +
  双指标 + 高价值护栏）全部落地并测试锁定；
- 4 份管辖地级 plan **全部收敛**（MODE B 各 2 轮 FULL、零新增，streak=2）；
- 13 轮 MODE A 发现 + 8 轮 MODE B 验证，**25 篇新文书真实入库**；
- 覆盖矩阵扩展：36 管辖地 ｜ ACTIVE 6 ｜ COLLECTED 25 ｜ BLOCKED 1（PL）；
  主题覆盖格 21（原 15）；
- 通道受阻事实如实：PL（反爬）/ BE（登录壳）/ EE（SPA 壳）/
  CO·GA·KY·MN（未适配）—— 不判死、归因入档，列入 4B-2B 前置。

**Phase 4B-2B：READY（框架批量化）** —— 附条件：先解决 7 个受阻试点通道。

---

## 2. 为什么 Phase 4B-1 没有收敛（问 1）与哪些轮不能连续计算（问 2）

### 2.1 证据链（问 1）

Phase 4B-1 联邦轮 R1–R3 的"饱和"被坐实为**实验设计缺陷**：

- 三轮使用**三套不同词组**（R1 短语 / R2 换词 / R3 再换词）——每轮换了搜索空间
  却计入同一 streak；
- R3 私下扩张 CELEX 年段（`32026R/32026L`）——搜索空间在轮间变化；
- 失败轮（FR 瞬态 ConnectError）被当成"无新增"解释——违反
  "NO_RESULTS ≠ SOURCE_FAILURE"。

### 2.2 历史重标记（问 2）

`outputs/audit/convergence_recheck.json`（只读重标记，含 6 文件 sha256 承诺）：

| 轮次 | 重标记 | 原因 |
|---|---|---|
| EU_SUPRANATIONAL R1 / R2 / R3 | **FULL** | 三轮无失败且词表一致（EU 侧） |
| US_FEDERAL R1 | PARTIAL | critical 端点 FR 瞬态降级（重试未恢复） |
| US_FEDERAL R2 | FULL | 无失败 |
| US_FEDERAL R3 | PARTIAL | 同上（瞬态） |
| summary | 6 轮：FULL 4 · PARTIAL 2 · INVALID 0 | **eligible_for_streak = 0** |

**全部 6 轮为 legacy（无 plan 绑定）→ 无论评级均不参与新协议 streak**。

---

## 3. 新 Search Plan Versioning 如何解决（问 3）

| 机制 | 实现 | 测试锁定 |
|---|---|---|
| plan_id + plan_hash | sha256 覆盖 11+3 类语义字段；created_at/notes 不参与 | `test_search_plan_hash.py` |
| 搜索空间变化 → reset | 跨 hash 轮次自动截断，新 plan streak 从 0 重开 | `test_convergence_reset.py` |
| MODE A/B 分离 | `discovery_expansion`（扩张，不入 SG8）/ `convergence_validation`（冻结；改 routes 直接拒绝） | `test_mode_separation.py` |
| round_validity | critical 失败且零成功 → INVALID；有失败 → PARTIAL（中断 streak 不计数）；否则 FULL | `test_round_validity.py` |
| 双指标 | raw_yield（效率）+ accepted_novelty_rate（主判据）；每轮 new_A1..D + new_high_risk_B | `test_class_level_novelty.py` |
| 高价值护栏 | 证据轮出现 new_A1 / 高风险 new_B / 持续 new_A2 → 不得判收敛 | 同上 |
| 多管辖地并行 | streak 仅在**同 plan_hash 轮次子集**内判定（互不截断） | `test_jurisdiction_round.py` |

**实测演示**：SE/FI/US-CA/US-WA 各自 2 轮 MODE B FULL + 零新增 → converged
（strict 视图 `plan_convergence`，见 §11）。

---

## 4. Onboarding Contract（框架核心）

- **15 份契约**：DE / NL / ES / FR / SE / PL / BE / FI / EE +
  US-CA / CO / GA / KY / MN / WA；校验 0 错误（`jurisdiction_contracts.json`）。
- 标准角色：EU 成员国 **7 个** mandatory、
  US 州 **8 个** mandatory；每角色必须"有通道或显式 gap"。
- 三条铁律（测试锁定）：**NIM = discovery layer ≠ national corpus**；
  **Federal ≠ State law**；Mandatory 角色全覆盖才可宣称 source 完整。
- 合同覆盖现状（**如实**）：

| 管辖地 | 覆盖 | 管辖地 | 覆盖 |
|---|---|---|---|
| DE | 1/7 | US-CA | 4/8（Step 8 回填 leginfo 2 角色） |
| NL | 2/7 | US-WA | 2/8（Step 8 回填 RCW 2 角色） |
| ES | 2/7 | US-CO / GA / KY / MN | 0/8 |
| FR | 3/7 | SE / FI | 1/7（Step 8 回填：立法库通道已通） |
| PL / BE / EE | 0/7 | — | — |

> 覆盖分母=契约 mandatory 角色；条数与覆盖无关（纪律）。
> Step 8 回填仅限"有真实采集证据"的角色（ACCESSIBLE→CONNECTED）。

---

## 5. Pilot 选择（问 4）

`jurisdiction_priority_score`（8 维加权：EPR 立法/黑粉关联/数据可达/语言成本/
联邦复杂度/回收产能/邻国协同/回溯深度）→ `jurisdiction_priority.{json,csv}`：

- **EU 新增 pilot**：SE 0.790 ｜ PL 0.700 ｜ BE 0.680 ｜ FI 0.660 ｜
  EE（stretch，reserve 顺位）
- **US 州 pilot**：CA 0.780 ｜ GA 0.635 ｜ CO 0.595 ｜ KY 0.595 ｜
  MN 0.585 ｜ WA 0.575
- **参考管辖地**（只做映射，不重写 connector）：DE / NL / ES / FR
- reserve：IT / SK / CZ / DK；HU / AT（access<0.5）；US AZ/IN/SC/ME；
  MI/IL/NY（403/超时）

---

## 6. Source Universe 与真实 Probe（问 5、问 6）

### 6.1 Probe 矩阵（两轮探测，真实 HTTP）

42 个探针（EU 成员国 + US 州）：**200 = 30** ｜ SPA 壳 = 2 ｜ 5xx = 1 ｜
4xx = 3 ｜ 网络错误 = 8（本环境间歇）。

| 管辖地 | 入口 | 结果 |
|---|---|---|
| SE | rkrattsbaser.gov.se | ✅ 200（检索 `?fritext=` 真实可用：22 hits） |
| FI | finlex.fi | ✅ 200（直链全文；检索为客户端渲染 ❌） |
| PL | isap.sejm.gov.pl | ⛔ Distil「Pardon Our Interruption」（UA/curl 均阻） |
| BE | ejustice.just.fgov.be | ⛔ 登录壳（5.5KB 空页） |
| EE | riigiteataja.ee | ⚠️ SPA 壳（忽略查询参数） |
| US-CA | leginfo.legislature.ca.gov | ✅ 200（section 直链；无检索端点） |
| US-WA | app.leg.wa.gov | ✅ 200（章节直链；search.do 404） |
| US-CO / GA / KY / MN | 各官方入口 | ⚠️ 200 但未写连接器（4B-2B 适配） |

### 6.2 Source Proof（11 份，`source_proofs/*.json`）

| 管辖地 | 样本 | fulltext 能力 |
|---|---|---|
| SE | 3/3 | ✅（SFS 直链；导航裁剪后正文） |
| FI | 3/3 | ✅（`__next_f` Flight 节点解析：Jätelaki 2.9 万字符） |
| PL | 3/3 | ✅（直链可读；**检索被反爬**） |
| US-CA | 3/3 | ✅（AB 2440 全文/状态；PRC 条款） |
| US-WA | 1/1 | ✅（70A.555 专章 6.4 万字符） |
| BE / EE / CO / GA / KY / MN | 0 | ⛔（通道受限，如实） |

---

## 7. Connector 真实产出（问 7）

5 个新连接器 + 3 项质量修复，全部真实跑出政策文书：

| 连接器 | 来源 | 语料产出 | 关键修复 |
|---|---|---|---|
| `sfst_se` | SE SFST | 3→**25 条** | 导航裁剪（正文前置） |
| `finlex_fi` | FI Finlex | 3→**33 条** | React Flight `__next_f` 文本节点解析 |
| `pl_isap` | PL ISAP | 0（Distil 阻） | 失败入档 `ConnectorBlocked` |
| `leginfo_ca` | US-CA leginfo | 4→**13 条** | 导航裁剪（PRC §42451 → **B 级**） |
| `rcw_wa` | US-WA RCW | 2→**16 条** | 导航裁剪（70A.555 → C 级） |

- **身份集成**：`doc_key → canonical_id`（如 `SE:SFS:2008:834`）；新采集
  SE 40% / US-WA 100% / US-CA 38.5% / FI 18.2% 完整（低值因历史 NIM
  元数据混入，如实）。
- **失败计数口径**：整轮重试后成功 doc 不计失败；
  **SOURCE_FAILURE ≠ 0 结果**（失败持久化 `jurisdiction_collection_failures.json`，
  未决仅 PL×3；FI/US-CA/US-WA 历史失败已被成功记录解析）。
- **挑战页/JS 壳文本不进语料**（采集端 + 测试端双防线）。

---

## 8. Topic Matrix（问 8）

T01–T14 五态（COVERED/PARTIAL/MISSING/BLOCKED）· 主题覆盖格 **21**
（原 15；`jurisdiction_coverage.json`）：

| 管辖地 | COVERED 主题 | 强证据来源 |
|---|---|---|
| US | T04 / T05 / T07 / T09 / T10 / T11 / T12 / T13 / T14（9） | 联邦 B 级 30 条 |
| US-CA | T01 / T05 / T07 | PRC §42451（B）、AB 2440 |
| US-WA | T05 / T07 / T10 | RCW 70A.555（B×2） |
| FI | T01 / T03 / T07 | SDK 123/2015、1072/1993（B×2） |
| EU | T03 | 电池法 A2 |
| GLOBAL | T03 / T13 | Basel / OECD 元数据 |
| SE | （0 COVERED；T01 PARTIAL） | 检索+引用链发现（C 级 9） |
| 其余 COLLECTED 管辖地 | — | NIM 元数据 PARTIAL 如实 |

多语种词表（FI/PL/EE）已补齐（词形经测试修正）。

---

## 9. Black Mass 六线矩阵（问 9）

jurisdiction 级（`build_coverage(jurisdiction=…)`）：

| 管辖地 | 六线覆盖 | 说明 |
|---|---|---|
| US | 6/6 | 联邦黑粉线索完整 |
| EU | 5/6 | WSR/CRM 家族 |
| GLOBAL | 4/6 | Basel 线 |
| US-CA / US-WA | 2/6 | 州电池管理 + 回收计划线 |
| FI / NL / PL / 其余 | 1/6 | 基础线（危废/回收）如实 |
| SE / DE / ES / FR / 未采国家 | 0/6 | 无覆盖（不粉饰） |

---

## 10. Known / Unknown / Blocked 三态（问 10）

- **Known（可采）**：EU / US 联邦 / SE / FI / US-CA / US-WA —— 6 条通道族
  （HTML 直链 / 官方检索 / 引用链 / NIM / 浏览器 / API）。
- **Unknown（未适配但可达）**：US-CO / GA / KY / MN（probe 200）+
  EU reserve（IT / SK / CZ / DK 等）—— 4B-2B 适配对象。
- **Blocked（端点级，含归因）**：
  - PL ISAP：Distil 反爬（浏览器通道或官方 API 为候选出路）；
  - BE ejustice：登录壳（需 change_lg 会话或替代入口）；
  - EE Riigi Teataja：SPA 壳（XML/API 待探）；
  - MI / IL / NY（4B-1 遗留 403/超时）；
  - OECD（SPA）、CEN/ISO（bot 拦截）—— 4B-1 已如实记录，维持。
- **替代通道结论**：受阻 ≠ 判死；每例给出候选通道（浏览器/API/会话），
  列入 4B-2B 前置。

---

## 11. 轮次执行与收敛（问 11）

### 11.1 MODE A（discovery_expansion，13 轮，不入 SG8）

| 管辖地 | 轮次 | 新入库 | 引用链衰减 |
|---|---|---|---|
| SE | R1–R3 | 7（C×7） | C 引用 11 个无效文号（负结果） |
| FI | R1–R3 | 3（B×2+C×1） | R2 起 0 |
| US-CA | R1–R3 | 1（C×1） | 42451/42452 已入库（eid 对齐） |
| US-WA | R1–R4 | 14（B×2+C×12） | R1→R2→R3 发现 11→2→1（衰减序列） |

**25 篇新文书入库**（`outputs/round_*.jsonl`，身份/分类完整）；
`DocNotFound`（不存在文号/section）与真实失败分离为负结果。

### 11.2 MODE B（convergence_validation，8 轮）→ 收敛清单（问 11 判据）

| 计划 | 轮次 | streak | converged | 证据轮 |
|---|---|---|---|---|
| SE_PLAN_V1 | R4–R5 | **2** | ✅ | SE-R4 / SE-R5 |
| FI_PLAN_V1 | R4–R5 | **2** | ✅ | FI-R4 / FI-R5 |
| US_CA_PLAN_V1 | R4–R5 | **2** | ✅ | US-CA-R4 / R5 |
| US_WA_PLAN_V1 | R5–R6 | **2** | ✅ | US-WA-R5 / R6 |

全部 FULL、accepted_novelty_rate=0.0、new_high_risk_B=0（无高价值阻断）——
判定依据 `outputs/audit/jurisdiction_convergence.json`（strict 视图：
plan_hash 一致 + MODE B + FULL + novelty<阈值）。
**可进入 convergence validation 的管辖地 = 上述 4 个。**

---

## 12. 覆盖矩阵汇总

```
36 管辖地 ｜ ACTIVE 6 ｜ COLLECTED 25 ｜ BLOCKED 1 ｜ 主题覆盖格 21
ACTIVE：EU · GLOBAL · US · FI · US-CA · US-WA
BLOCKED：PL（NIM 元数据 + Distil 未决失败×3）
```

`outputs/audit/jurisdiction_coverage.{json,csv}`（16 列，含身份/A-B-C-D/
主题/黑粉/失败/proof）。

---

## 13. 纪律执行说明

- **不改 4B-1 历史**：轮次 JSON 零修改，sha256 承诺（6 文件）被测试锁定；
- **不降阈值 / 不换词造收敛**：词表变更只能新 plan（hash 测试锁定四份 plan）；
- **条数仅描述统计**：覆盖分母=契约 mandatory 角色；A1 goldset 无专属案例 →
  `gold_recall = not_available`（如实，不凑数）；
- **失败与负结果双轨**：SOURCE_FAILURE（重试后仍失败）≠ DocNotFound（不存在
  = 负结果）；两者分别入档；
- **R1 老口径注记**：SE-R1/US-CA-R1 记录早于 not_found 口径修正，其"失败"
  实为不存在文号/section（R2+ 全部 FULL 已证）。

---

## 14. Phase 4B-2B 评估（问 12）

**判定：READY（框架批量化）——附前置条件。**

理由（正）：

1. 全链路（契约→proof→connector→plan→轮次→矩阵）在同框架下对 **4 类通道
   形态**（HTML 直链 / 官方检索 / 引用链 / NIM 元数据）全部实证；
2. 4/4 pilot 收敛（streak=2、MODE B 零新增）——**接入模式可复用例证成立**；
3. 每新管辖地只需"填表"（契约 + plan + connector 三件套），框架不变。

前置条件（负，如实）：

1. **7 个受阻试点通道**需先解决（PL 反爬 / BE 登录壳 / EE SPA /
   CO·GA·KY·MN 适配）——批量铺开前建议先做"通道适配冲刺"；
2. 契约角色覆盖普遍偏低（0–3/7–8），2B 需按角色补齐采集面；
3. 多语种词表与身份模式需随管辖地扩展（当前 sv/fi/pl/ee 已备）。

---

## 15. 交付物与复现

| 类别 | 产物 |
|---|---|
| 框架 | `sources/jurisdiction-onboarding/*.yaml`（15）· `app/policy/jurisdiction_onboarding.py` |
| 计划 | `sources/search-plans/{SE,FI,US_CA,US_WA}_PLAN_V1.yaml`（hash 锁定） |
| 运行 | `scripts/run_jurisdiction_round.py` · `audit_jurisdiction_{coverage,convergence,priority}.py` |
| 审计 | `outputs/audit/`（矩阵/收敛/重标记/proofs/失败/优先级） |
| 语料 | 新增 25 篇（SE 7 · FI 3 · US-CA 1 · US-WA 14） |
| 测试 | 278 passed（phase4b2a 106 条新增量级）+ 旧脚本 21/10/5/4 全绿 |

---

## 16. 十二问对照

| # | 问题 | 答复位置 |
|---|---|---|
| 1 | 4B-1 为什么没收敛 | §2.1（换词 + 扩年段 + 失败误读） |
| 2 | 哪些 Round 不能连续计算 | §2.2（全 6 轮 legacy → eligible 0） |
| 3 | Versioning 如何解决 | §3（机制表 + 实测） |
| 4 | Pilot 选择 | §5（8 维评分 + 名单） |
| 5 | 每管辖地 Source Universe | §6.2 + `source_proofs/*.json` |
| 6 | 哪些 source 真实 probe | §6.1（42 探针：200×30 / SPA×2 / 5xx×1 / 4xx×3 / err×8） |
| 7 | 哪些 connector 真实跑出政策 | §7（5 connector + 25 篇入库 + 质量修复） |
| 8 | T01–T14 覆盖 | §8（21 覆盖格） |
| 9 | 黑粉六线覆盖 | §9（US 6/6 … SE 0/6） |
| 10 | Known / Unknown / Blocked | §10（含替代通道结论） |
| 11 | 哪些可进 convergence validation | §11.2（4 个，streak=2） |
| 12 | 4B-2B 是否 Ready | §14（READY + 前置条件） |

---

## 17. 终端摘要

```
PHASE 4B-2A RESULT
Search Plan Versioning: PASS（hash 覆盖 14 类语义字段；4 plan 冻结锁定）
Convergence Protocol:   PASS（legacy 排除 / MODE 分离 / validity / 高价值护栏）
EU Reference Jurisdictions: DE 1/7 · NL 2/7 · ES 2/7 · FR 3/7（映射一致，未重写）
New EU Pilots:      SE ✅收敛（7 新）· FI ✅收敛（3 新）· PL ⛔反爬 · BE ⛔登录壳 · EE ⚠️SPA
US State Pilots:    US-CA ✅收敛（1 新）· US-WA ✅收敛（14 新）· CO/GA/KY/MN 待适配
Source Proof:       11/11 complete（5 通 · 6 受限，样本 3/3·3/3·3/3·3/3·1/1）
Topic Matrix:       36/36 generated（覆盖格 21）
Black Mass Matrix:  36/36 generated（US 6/6 · EU 5/6 · WA·CA 2/6）
Convergence-ready jurisdictions: SE · FI · US-CA · US-WA（streak=2 · MODE B 零新增）
P0 blockers:        PL Distil 反爬 · BE 登录壳 · EE SPA · CO/GA/KY/MN 未适配
                    （端点级归因，非判死；替代通道已列）
Phase 4B-2B:        READY（框架批量化；前置：7 受阻通道优先适配）
```
