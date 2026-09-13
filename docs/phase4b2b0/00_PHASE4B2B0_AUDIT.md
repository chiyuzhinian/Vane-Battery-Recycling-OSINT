# Phase 4B-2B0 — Repository Audit（开发前审计）

> 生成：2026-09-13 ｜ 基线：Phase 4B-2A = CONDITIONAL PASS（分支 `phase4b2a` @ `6346f44`）
> 状态：**开发前审计**（本文件先于任何 2B0 代码变更）
> 结论一句话：2A 的协议层（plan / MODE / validity）扎实，但**聚合层与资格层存在
> 三处 P0 缺陷**——`plan_converged` 无管辖地资格闸门、历史记录分类聚合缺失
> （3156/3291 条未参与）、identity 分母混入 discovery 层——直接导致
> "1/7 角色覆盖的管辖地被称为 convergence-ready"。

---

## 0. 审计范围（Inspect First）

```
app/policy/jurisdiction_onboarding.py   ✅ 已读（覆盖率算法：channel.status ∈ CONNECTED/COMPLETE/PARTIAL）
app/policy/{acceptance,rounds,convergence_recheck,identity_jurisdiction,
            jurisdiction_coverage,black_mass,backfill,scope_saturation}.py  ✅ 已读
scripts/run_jurisdiction_round.py       ✅ 已读（Step 8 产物）
scripts/audit_jurisdiction_{coverage,convergence}.py  ✅ 已读
sources/jurisdiction-onboarding/（15 契约）  ✅ 抽样已读
sources/search-plans/（6 plan）          ✅ 已读
outputs/audit/（全套产物）               ✅ 实况探查（_audit_2b0.py）
```

数据实况：`load_records` 3291 条；overlay 120 行（全 US）；fr_identity_overlay 135 行。

---

## 1. Q1 —— plan_converged 是否可能被误解释为 jurisdiction converged？

**是。风险已坐实为系统级输出问题（P0-A1）。**

证据链：

1. `rounds.convergence_status(rounds, plan_hash=, mode_required="convergence_validation")`
   的判定输入**只有**：plan_hash 一致 / round_mode / round_validity /
   accepted_novelty_rate + 高价值护栏。**没有任何 Source Role coverage、
   identity、route diversity 条件**。
2. `scripts/audit_jurisdiction_convergence.py` 输出 `converged=True`，
   且 2A 最终报告 §11.2 写下"**可进入 convergence validation 的管辖地 =
   SE / FI / US-CA / US-WA**"——而四地的 mandatory 角色覆盖为
   **SE 1/7 ｜ FI 1/7 ｜ US-CA 4/8 ｜ US-WA 2/8**。
3. `discovery_rounds.json :: plan_convergence` 的键是 plan_hash、值含
   `converged: true`——下游（报告/面板/未来自动化）**没有任何字段提示
   "这只代表该 plan 的搜索空间收敛，不代表管辖地完整"**。

**结论**：当前系统在"plan 级收敛"与"管辖地级合格"之间**无闸门、无命名区分**。
2B0 必须引入三层状态（§二），并将 `jurisdiction_convergence.json` 的
`converged` 字段**降级更名为 plan 级语义**（或加 `layer` 标签），防止误读。

---

## 2. Q2 —— mandatory source coverage 是否进入 saturation eligibility？

**否。挂钩度为 0（P0-A5）。**

- 全库检索：`convergence_status` / `derive_validity` / `audit_jurisdiction_convergence`
  均无 `covered_roles` / `contract` / `mandatory` 输入。
- `scope_saturation.py`（4B-1）是 scope 级（EU_SUPRA / US_FED / MS / US_STATES），
  读 `source_role_gap_matrix.json` + `fr_identity_overlay` + `discovery_rounds`——
  **不知道** 2A 的 jurisdiction 契约（15 份）与 4 个 pilot plan 的存在；
  `SUB_NATIONAL_ROLES` 的存在证明它感知"州级 vs 联邦"边界，但不含 2A 产物。
- 即：**"角色覆盖 1/7 的 SE" 与 "角色覆盖 6/7 的假想管辖地" 在 eligibility 上完全等价**。

**结论**：需要新建 `JURISDICTION_CONVERGENCE_ELIGIBLE` 判定层，把
契约覆盖（critical 100% + EU≥5/7 / US≥6/8）、identity≥90%、
routes≥3、无 unresolved critical failure 作为**硬闸门**。

---

## 3. Q3 —— topic coverage 聚合是否正确读取 historical + new metadata？

**否。存在聚合层系统性缺失（P0-A2），是本次审计最重要的发现。**

机制分析：

1. `jurisdiction_coverage.topic_status()` 判定 strong 证据的条件是
   `meta.acceptance_class ∈ {A1, A2, B}`（行 76）；
2. 但 `load_records()`（backfill.py）只读 `outputs/*.jsonl` 原始快照，
   **不合并任何 overlay**；原始快照中 **3156/3291 条记录没有
   `acceptance_class` 字段**（它只在两类地方存在：新采集轮次 persist 时
   写入的 meta；以及 `policy_metadata_overlay.jsonl`）；
3. `policy_metadata_overlay.jsonl` **只有 120 行且全部是 US FR 记录**
   （backfill 当时只覆盖 US 联邦）——**对 EU / SE / FI / CA / WA 零覆盖**；
4. overlay 的**唯一消费者是写端脚本本身**（+ 无关的 scope_saturation 读
   fr_identity_overlay）——**没有任何聚合模块合并它**。

**后果（已在 2A 产物中可见）**：

- EU 240 条记录的 acceptance 分布显示为 `{'?': 221, 'C': 16, 'A2': 3}`
  → strong 仅 3 条 → topic matrix 中 EU **只有 T03 COVERED**；
- 而 EU 语料实际包含：Battery Regulation（2023/1542）、WSR（2024/1157）、
  recycling efficiency（2025/606）、recycled content、traceability、
  black mass、ELV（2000/53）——**理论上应覆盖多个 T01–T14**；
- 同理所有 `COLLECTED` 管辖地的 topic 矩阵（PARTIAL 居多）均**被低估**。

**结论**：修复方向不是写死 topic，而是建立**统一聚合装载器**：
`effective_class(record)`——meta 有则用，否则**运行时调用当前分类器
`classify_record` 现算**（纯逻辑、无网络、与 review-rejudge 同一先例），
并让 coverage / black_mass / topic audit 共用。overlay 合并作为补充
（US FR 120 条的分类版本比现算更早，需明确版本口径）。

---

## 4. Q4 —— identity completeness 为什么 SE/FI/CA 偏低？

**主因是统计分母口径，不是 parser/mapping 失败（P0-A3）。**

`identity_completeness(records, jid)` 的 rows = `jurisdiction_of(r) == jid`
的**全部**记录。而 jurisdiction 桶里混着三类本质无身份的记录：

| 组成（以 SE 25 条为例） | 条数 | 有 identity？ | 说明 |
|---|---|---|---|
| NIM 元数据（eu_nim_se） | 15 | ❌ 设计如此 | discovery layer，只有标题+公报引用 |
| 旧连接器（se_sfst 3 条） | 3 | ✅ | doc_key/language 齐全 |
| Step 8 新采集（runner） | 7 | ✅ | meta 含 doc_key/language |

→ 10/25 = **40%**（分子是全部"真采集"记录，分母被 NIM 稀释）。

同构验证：FI 18.2% = 6/33（3 旧 + 3 新；27 NIM 稀释）；
US-CA 38.5% = 5/13（4 旧 leginfo + 1 新；8 条人 browser/NIM 类稀释）。

**另有两个次级因素**：

- `fr_identity_overlay.jsonl`（135 行，US FR 身份富化）**没有任何读取方**
  （grep 只命中 scope_saturation 的一个无关引用）——US 联邦的历史身份
  富化结果未回流；
- 历史专线记录（DE/NL/ES/FR）的 identity 字段同样缺失，
  参考管辖地也无法度量真实完整度。

**结论**：2B0 需要 (a) **分区口径**：`dedicated corpus`（专线采集）
与 `discovery layer`（NIM）分列，目标值只对前者（≥95%/≥90%）；
(b) 合并 `fr_identity_overlay`；(c) 为历史专线记录构建 identity
（从既有 meta 的官方编号字段，规则化，不猜）。**禁止默认值凑数**。

---

## 5. Q5 —— consumer/general battery 是否可能污染 EV traction battery corpus？

**是。NIM 默认 A2 通道是主要污染面（P1-A4）。**

证据：

1. `acceptance.classify_record` 对 `sid.startswith("eu_nim_") and relevant`
   的记录**直接返回 A2**（对象=电池体系成员），不检查域；
2. 实况抽查（A1/A2/B 记录中含泛消费电池词）：

| evidence_id | 类 | 命中词 | 标题 |
|---|---|---|---|
| `eu_52025XC00214` | A2 | portable | Commission Notice — 电池法指南（核心，正常） |
| `nim_165360` | A2 | portable | FR 2009 便携电池收集条件 arrêté |
| `nim_156723/158455/218377/223655` | A2 | paristo | FI「paristoista ja akuista」电池与蓄电池法令（泛） |

3. `_A1_OBJECT` 已有 traction/vehicle/EV/motive battery 标题门槛（A1 层面
   防护正确），但 **A2/B/C 与 NIM 通道缺 domain 维度**——泛便携文书与
   EV 核心文书同为 A2，无法区分"直接适用于 EV"与"背景"。

**结论**：按规格 §五新增正交字段 `domain_scope`（5 级），并与
A1/A2/B/C/D 做**约束矩阵**（GENERAL_BATTERY_BACKGROUND 不得 A1/A2；
OUT_OF_SCOPE → D；CORE_EV_TRACTION 才可 A1）。NIM 泛电池 → 降 C
（background）或保留 A2 但 domain_scope=GENERAL_BATTERY_BACKGROUND 且
**不计入 EV 强证据**（由约束矩阵决定）。

---

## 6. 缺陷清单与 2B0 修复映射

| ID | 级别 | 缺陷 | 2B0 修复（规格节） |
|---|---|---|---|
| A1 | **P0** | plan_converged 无管辖地资格闸门（1/7 称 ready） | §二 三层状态 + §十一 gate |
| A2 | **P0** | 聚合层不合并 overlay / 不现算分类（3156 条盲区） | §八 topic audit + 统一装载器 |
| A3 | **P0** | identity 分母混 discovery 层；overlay 无消费者 | §七 identity hardening |
| A4 | P1 | 泛消费电池污染（NIM 默认 A2） | §五 domain guard |
| A5 | P1 | source role coverage 与 eligibility 0 挂钩 | §二 / §十一 |
| A6 | P1 | EU topic matrix 单主题假象 | §八 consistency audit |
| A7 | P2 | route diversity 未建模 | §十 + eligibility |
| A8 | P2 | Black Mass EU 缺线未指明；州/联邦混淆风险 | §九 |
| A9 | P2 | A1 goldset 缺口（保持 INSUFFICIENT_A1_GOLDSET） | §六 |

---

## 7. 兼容性红线（延续 2A 纪律）

```
❌ 不改 4B-1/4B-2A 历史产物（convergence_recheck.json sha256 承诺继续锁定）
❌ 不改冻结 plan（SE/FI/US_CA/US_WA_PLAN_V1 hash 测试锁定；新空间 → V2）
❌ 不降 eligibility 门槛凑 READY
❌ 不用默认值提高 identity completeness（只从官方编号/元数据构造）
⚠️ 分类现算：以当前规则版本（tests 锁定）重判历史记录——与
   "review feedback → 重判" 同先例；报告中注明重判版本与影响面
✅ 一切新聚合走统一装载器（load_effective_records），禁止各模块自行读取
```

---

## 8. 2B0 执行序（本审计放行后）

```
Step 1  三层收敛状态 + JURISDICTION_CONVERGENCE_ELIGIBLE 判定（含测试）
Step 2  Identity hardening（分区口径 + overlay 合并 + 历史专线身份）
Step 3  Topic Mapping Consistency Audit（脚本 + 产物）
Step 4  Domain Relevance Guard（5 级 scope + 约束矩阵 + NIM 修正）
Step 5  7 通道攻坚（PL/BE/EE/CO/GA/KY/MN，Proof 先行）
Step 6  Pilot 角色 Closure（SE/FI/CA/WA 补角色通道，Proof 先行）
Step 7  A1 Gold Set 真实补充评估（不足则保持 INSUFFICIENT）
Step 8  Black Mass 缺口明确化 + Route diversity
Step 9  8 测试文件 + 全量回归
Step 10 Scale-Out Gate + 最终报告 + 终端摘要
```

---

*下一步：Step 1（三层收敛状态模型），每步测试先行、独立提交。*
