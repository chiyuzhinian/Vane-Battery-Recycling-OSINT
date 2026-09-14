# Phase 4B-2B0 — Pilot Coverage Closure & Channel Adaptation 最终报告

> 生成时间：2026-09-14 ｜ 分支：`phase4b2a` ｜ 范围：SE / FI / US-CA / US-WA 四个 Pilot
> 纪律：不降门槛、不凑数、PARTIAL/INSUFFICIENT/NOT_READY 如实；不改 4B-1/2A 历史产物。

---

## 一、Before → After 覆盖

| 管辖地 | 契约覆盖 | critical 角色 | routes | identity（专线） | 状态 |
|---|---|---|---|---|---|
| SE | 2/7 → **3/7** | 100% | B,C（不足 3） | 100% | SOURCE_PLAN_CONVERGED |
| FI | 2/7 → **2/7** | 100% | C（不足 3） | 100% | SOURCE_PLAN_CONVERGED |
| US-CA | 5/8 → **5/8** | 100% | A,C（不足 3） | 100% | SOURCE_PLAN_CONVERGED |
| US-WA | 2/8 → **6/8** | 100% | A,C,D ✓ | 100% | **JURISDICTION_CONVERGENCE_ELIGIBLE** |

- SE：新增 `se_sfst`（官方公报，SFS 事实）+ `se_naturvardsverket`（ENV 指南，PARTIAL）→ 3/7（critical 100% 早已达成）。
- FI：契约 2/7（真实状态——`fi_finlex` gazette + 既有法源；进一步角色未在本阶段新增）。
- US-CA：保持 5/8；Step 7 新增 **SB 615 全文**（首个真实 A1）。
- US-WA：WAC 章（STATE_STATUTES）＋ Ecology（WASTE_PROGRAM）＋ Bills（STATE_LEGISLATURE 强化）→ **6/8 且全闸门通过**。

其余已采管辖地（维持）：DE 1/7 · NL 2/7 · ES 2/7 · FR 3/7 · PL 1/7 · US-KY 1/8 · US-MN 1/8。

## 二、7 通道攻坚决局

| 通道 | 结局 | 方法/证据 |
|---|---|---|
| PL | **ADAPTED** | ISAP Distil 被阻 → 官方替代 **Sejm ELI API**（api.sejm.gov.pl）：元数据+全文+实施法案族；3/3 样本 proof（2009/666 全文 129K）；**未绕过访问控制** |
| BE | BLOCKED_SITE_LEVEL | ejustice 全路径同障（含 ELI/loi_a1/change_lg；~507B 壳）；建议后续换网络环境或等官方接口 |
| EE | BLOCKED_SPA_SHELL | RT 全路径同障（akt/eli/avaandmed；51763B 壳）；未发现公开数据接口（api 404） |
| US-CO | PARTIAL_ENTRY_ONLY | leg.colorado.gov/bills 可达（92KB）；检索为 JS；battery 专条存在性未确认（HB22-1355 为包装/印刷品 PRP）→ 待电池立法或 CRS 通道 |
| US-GA | BLOCKED_SPA_AND_AUTH | legis.ga.gov/laws 1.5KB SPA 壳；api/legislation 401 |
| US-KY | **ADAPTED** | KRS 目录 269 条；电池专条未定（KRS 未见 battery 专章）→ 以真实条文样本验证通道（3/3 样本） |
| US-MN | **ADAPTED** | 搜索为 JS → `cite` 直链模式；电池专条未定位（216B/15A.30xx 404）→ 样本由 115A 章提供（3/3 样本） |

**通道适配 3/7（PL/KY/MN）——低于 Scale-Out Gate 要求的 ≥5。**

## 三、Domain Scope Guard（5 级）

| 级别 | 计数 |
|---|---|
| CORE_EV_TRACTION | 12 |
| HORIZONTAL_APPLIES_TO_EV | 306 |
| SUPPORTING_REGULATION | 77 |
| GENERAL_BATTERY_BACKGROUND | 426 |
| OUT_OF_SCOPE | 1466 |
| non_policy_excluded | 1030 |

- 约束矩阵：GENERAL + A1/A2/B → **降 C**；OUT_OF_SCOPE + A1/A2 → **降 D**（B 保留——eCFR 40 CFR 261/173 实测判例）；SUPPORTING + A1/A2 → B。
- 实证：FR/DR/DE 便携电池条目（A2→C）；NIM 通道豁免 OUT_OF_SCOPE 罚但 GENERAL 保留。
- 护栏重写 58 条；`test_general_battery_not_core.py` 锁定"泛电池不得 A1/A2"。

## 四、Identity Hardening

**专线口径（dedicated，剔除 discovery-layer）：**

| 管辖地 | before | after | new | historical | discovery 排除 |
|---|---|---|---|---|---|
| SE | 100% | **100%** | 100% | 100% | 15 |
| FI | 100% | **100%** | 100% | 100% | 27 |
| US-CA | 100% | **100%** | 100% | 100% | 8 |
| US-WA | 100% | **100%** | 100% | 100% | 0 |
| DE | 0% | **100%** | — | 100% | 5 |
| NL | 0% | **100%** | — | 100% | 21 |
| ES | 0% | **100%** | — | 100% | 5 |
| FR | 0% | **73.3%** | — | 73.3% | 16 |

- `build_identity_v2`：DE gesetze slug→`DE:GIW:{slug}`；NL bwb→`NL:BWB:{id}`；ES BOE→`ES:BOE:{id}`（derogada→repealed）；FR dila 无编号条目**如实留空**（不造默认值）。
- 口径：≥95%（new）与 ≥90%（combined）均以核心 5 字段（canonical_id/official_identifier/issuer/language/official_url）全有为准。

## 五、Topic Mapping

- 全语料 3317 条；缺口分解：占位无正文 1701 ｜ backfill 缺 1504 ｜ 抽取窗口差 445 ｜ 聚合差 552 ｜ 强证据无主题 5。
- EU 全文接入（7 部 + **EWC 32000D0532**）后：电池法 351K 字符 → 11 主题；EU 各 CELEX 分布覆盖 T01–T13。
- `effective_class` 现算回退 + overlay；全文口径 `extract_topics_full`；终点套域护栏。
- `audit_topic_mapping_consistency.py` → `topic_mapping_mismatches.json`（per_jurisdiction delta 供报告）。
- **P0 类（聚合盲区）已关闭**：45 个覆盖格无一因聚合口径丢主题；剩余缺口均为内容层（占位/未采），如实列出不做掩盖。

## 六、A1 Gold Set

- **首个真实 A1**：`us_ca_sb615_traction` — CA SB 615 "Vehicle traction batteries"（2025-2026），官方 billTextClient 全文（16.9K 字符），现算分类 **A1**、domain **CORE_EV_TRACTION**、主题 T04+T07。
- 状态：**Enrolled（2026-09-04 呈交州长，尚未签署）→ binding_force=proposal**（保守正确）。
- 验证：expected A1 → got A1（goldset evaluate OK；a1_recall=1.0）。
- A1 gold set 计数：**verified=1 ｜ holdout=0 ｜ 阈值 5 → status = INSUFFICIENT_A1_GOLDSET**（如实，不凑数）。

## 七、Black Mass 六线缺口

**EU 视图（全 COVERED，含最弱线补强）：**

| 线 | strong | 说明 |
|---|---|---|
| waste_status | 35 | — |
| hazardous | **1 → 2** | 补 **EWC 2000/532/EC（32000D0532）**；WFD 32008L0098 + EWC 双强证据 |
| transport | 35 | — |
| transboundary | 19 | WSR 2024/1157 族 |
| customs | 9 | — |
| end_of_waste | 23 | — |

**US 视图（联邦/州拆分——州不得重复计联邦）：**

| 线 | 联邦 | 州 | 备注 |
|---|---|---|---|
| waste_status | 2 | 0 | 仅联邦——州级待补 |
| hazardous | 70 | 6 | 独立并行，不合并计数 |
| transport | 42 | 3 | 同上 |
| transboundary | 1 | 0 | 仅联邦（州不管越境——天然） |
| customs | 11 | 0 | 仅联邦 |
| end_of_waste | 4 | 0 | 仅联邦 |

## 八、Source Plan vs Jurisdiction（三层强制分离）

- `SOURCE_PLAN_CONVERGED`（plan 搜索空间饱和）**≠** `JURISDICTION_CONVERGENCE_ELIGIBLE`（管辖地合格）。
- 8 管辖地评估：plan_converged **4**（SE/FI/US-CA/US-WA）｜ eligible **1**（US-WA）｜ near_saturated 0（恒 False 至 4B-2B 合并 SG）。
- US-WA 全闸门：critical 100% ✓ ｜ 6/8 ✓ ｜ routes A,C,D ✓ ｜ identity 100% ✓ ｜ 无未决 critical 失败 ✓。
- US_WA_PLAN_V2（D 路线新增）触发 reset——V1 streak 独立视图保留；V2 经 R1（discovery）+R2/R3（validation，零新增 streak=2）验证收敛。

## 九、Scale-Out Gate 与结论

| Gate 条件 | 现状 | 判定 |
|---|---|---|
| eligible 管辖地 ≥3 | 1（US-WA） | ❌ |
| 7 通道 ≥5 适配 | 3（PL/KY/MN） | ❌ |
| topic 无 P0 阻塞 | P0 已关闭 | ✓ |
| identity ≥90%（pilot+欧盟核心） | pilot 100% / DE-NL-ES 100% | ✓ |
| domain guard 测试通过 | 通过 | ✓ |
| A1 gold set 可解释 | 1 真实案例，INSUFFICIENT 如实 | ✓（诚实口径） |

### 结论

**PHASE 4B-2B FULL SCALE-OUT: NOT READY**

- 成立：单管辖地从 2/8 做到 6/8 且全闸门通过（US-WA）的完整路径已被证明——"一个国家真的能从 1/7 做到接近完整"已实证。
- 未达：eligible 1/3；通道适配 3/5；A1 gold set 1/5（如实 INSUFFICIENT）。
- 下一步建议（4B-2B）：① 将 SE/FI/US-CA 的 routes 提升至 ≥3（EU 侧需 NIM 通道就绪）；② BE/EE/GA 通道换网络环境或等官方接口；③ A1 案例继续累积（不降阈值）；④ SG 体系合并完成 near-saturation 判定。
