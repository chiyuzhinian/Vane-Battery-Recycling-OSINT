# Phase 4A — Policy Corpus Acceptance & Saturation 最终报告

> 日期：2026-09-12 ｜ 判定：**CONDITIONAL PASS**（交付物验收通过；语料**未饱和**，P0 blocker 见 §11）
> 审计文档：`docs/phase4a/00_CURRENT_STATE_AUDIT.md`

---

## 1. Executive Summary

**做了什么**：在现有采集/判定/审核/反馈体系上，**增量**建成五层验收体系
`Source Universe → Policy Acceptance → Legal Family → Gold Set → Saturation Gate`：

| 层 | 产物 | 状态 |
|---|---|---|
| 主题本体 T01–T14 | `sources/regulatory-topics.yaml` | ✅ 14 主题全配置 |
| 验收分类 A1/A2/B/C/D | `sources/policy-acceptance-rules.yaml` + `app/policy/acceptance.py` | ✅ Gold Set 22/22 |
| 文书类型/约束力 | `sources/instrument-types.yaml` + `instruments.py` | ✅ 14 类型 + 4 判例锚点 |
| 管辖区源宇宙 | `sources/jurisdiction-registry.yaml` + `source_universe.py` | ✅ EU/27国/US联邦/50州 schema |
| 法律身份/家族图 | `legal_identity.py` / `legal_graph.py` | ✅ 电池法家族 100% |
| Gold Set | `sources/policy-goldset.yaml` + `goldset.py` | ✅ **P=1.0 R=1.0**（22 例含 6 holdout） |
| 饱和门 SG1–SG9 | `saturation.py` | ✅ 真实输出 EU=WEAK 4/9、US=WEAK 3/9 |
| 配置单一真源 | `app/policy/config.py`（Pydantic fail-fast） | ✅ 测试锁定 |
| 4 个 Audit CLI + backfill | scripts/ | ✅ 全部可运行 |

**没做什么**（规格 §18 约定）：未扩日本/韩国/加拿大；未重写前端/Vane；未大批量加关键词；
未删除旧规则；未伪造饱和（真实结果 WEAK）。

**能否宣称 Saturated**：**不能**。EU=WEAK（4/9）、US=WEAK（3/9）。

---

## 2. Repository Audit（原问题 → 修改）

| 原问题（00_CURRENT_STATE_AUDIT 查实） | 本阶段修改 |
|---|---|
| `search-boundary.yaml` **无任何运行时消费者**（纯文档） | 追加 `policy_v2` 段（三层时间/语言模型）+ `config.py` 加载 |
| policy 36 个月窗口 / languages=[zh,en] / 固定 source×topic 网格 | v2 模型取代（**旧段保留**，迁移未完不删） |
| 词表多份维护（relevance.py 硬编码 vs YAML） | 新体系全部 YAML→Pydantic；旧判定器保留（不破坏），衔接点在 `acceptance.py` |
| `relevant=True` 混装（binding/guidance/advisory/info 不分） | 新增 `instrument_type` + `binding_force` + `legal_status` + `acceptance_class`（overlay） |
| 无 Source Role 模型（"URL 存在=完成"） | `jurisdiction-registry.yaml` 角色矩阵 + 状态机 + 数据反推降级 |
| 文档身份靠 meta ad-hoc | `legal_identity.py` 独立解析 + 缺失字段报告 |

---

## 3. Architecture Changes

```
Source Universe          jurisdiction-registry.yaml → source_universe.py
(管辖区×角色状态机)        状态: NOT_ONBOARDED→…→COMPLETE｜BLOCKED
        ↓
Discovery                现有采集器不动（CELEX/NIM/FR/browser）
        ↓
Identity                 legal_identity.py（canonical_id/issuer/status/…）
        ↓
Acceptance               acceptance.py（A1/A2/B/C/D；B 需条款证据；AI 仅辅助）
        ↓
Legal Family             legal_graph.py（8 种关系；P0 家族扩张检查）
        ↓
Gold Set                 goldset.py（P/R/F1 + holdout 纪律）
        ↓
Gap Audit                audit_policy_universe / audit_legal_family CLI
        ↓
Saturation               saturation.py（SG1–SG9 联合门；exit code 无绿灯）
```

## 4. New Data Model（overlay 增量字段，**不改原始 evidence**）

```
outputs/policy_metadata_overlay.jsonl   （backfill 产物，当前仅 dry-run）
  evidence_id, acceptance_class(A1|A2|B|C|D), acceptance_relevant,
  acceptance_confidence, topic_ids[], acceptance_reasons[], evidence_quotes[],
  acceptance_review, instrument_type, binding_force, legal_status,
  legal_identity{canonical_id, jurisdiction, issuer, official_identifier,
                 language, missing_fields[]}, backfill_version, backfilled_at
```

## 5. Acceptance Tests（真实案例）

| 分类 | 真实案例 | 结果 |
|---|---|---|
| A1 | （当前 Gold Set 无 A1 正例——ELV 按规格归 A2；A1 规则就绪待样本）| — |
| A2 | `32023R1542` 电池法、`32025R0606` 回收效率、`2018/849`、`2026/1738`、`52020PC0798`、捷克 NIM 电池令 | ✅ |
| B | PHMSA 安全通告（advisory）、`2019-03812` 联邦规则、`2024-09094` 清洁车辆抵免 | ✅ |
| C | ESPR（泛框架守护）、关键矿产清单（背景路由）| ✅ |
| D | DDR 科普页、OSHA 信息页、BCI 行业文章、FEOC（用户❌判例）| ✅ |

## 6. Gold Set Evaluation（LIVE 数据，22 案例 / 6 holdout）

```
precision=1.0  recall=1.0  F1=1.0
A2 recall=1.0  B recall=1.0  A1 recall=None（无 A1 案例）
FP rate=0.0    FN rate=0.0
instrument_type_accuracy=0.786  legal_status_accuracy=None（未设 expected_status）
INSUFFICIENT_GOLDSET=False（22≥20 且 22/22 匹配）
```
⚠️ 诚实标注：A1 无正例、instrument 精度 0.786 未达 0.98 目标（主要因占位标题记录
与 NIM 记录无类型信号）——**这是缺口，不是达标**。

## 7. EU Audit

| 维度 | 结果 |
|---|---|
| EU 主体源角色 | **3/11 (27.3%)**（经 EUR-Lex 主/授权/NIM 达 CONNECTED；标准/Basel/OECD/运输署未接入） |
| NIM | ✅ 27 国 566 条→396 落盘；角色状态 CONNECTED（但 NIM ≠ 法律全集） |
| 成员国逐国 | **4/78 角色 (5.1%)** CONNECTED（DE/NL/ES/FR）；其余 PARTIAL |
| 法律家族 | 电池法 **1.0**；WSR **1.0**；ELV **0.333**；2006/66 **0.333** |
| 家族缺口 | ELV: AMENDS/CORRIGENDUM_OF 未解决；2006/66: AMENDS/REPEALS 未解决 |
| 新颖度 | 无回合数据（feedback_state 空）|

## 8. US Audit

| 维度 | 结果 |
|---|---|
| US 联邦源角色 | **7/16 (43.8%)** CONNECTED（FR 完整；USC/PublicLaw/CBP/eCFR 结构化未接入）|
| Federal Register | ✅ COMPLETE（37 组合 + 边界短语 + `"black mass"` 精确短语）|
| CFR/eCFR | PARTIAL（FR 记录含 CFR 引用；eCFR 抓取未建）|
| US Code/Public Law | NOT_ONBOARDED（congress.gov 403 缺 Key）|
| 50 州+DC | schema 就绪；**50/51 NOT_ONBOARDED**（仅 CA=PARTIAL）|
| 新颖度 | 无回合数据 |

## 9. Black Mass Coverage 矩阵

| 环节 | 覆盖 | 载体 |
|---|---|---|
| waste status（废物定性） | ✅ 间接 | WSR 2024/1157 家族（31 条，家族完整度 1.0）|
| hazardous classification（危废定性） | ⚠️ 部分 | DE AVV/各国危废目录（NIM 层）|
| transport（运输） | ✅ | PHMSA 通告+规则、ADR/IATA 框架文档 |
| transboundary shipment（跨境转移） | ✅ | WSR + 授权法案 2024/2571/3230 + 修订 2026/1703 |
| trade/customs（贸易/海关） | ⚠️ 弱 | Section 232 调查、DPAS 指令（2026-16078）、DPA 裁定（2026-15859）；BIS/CBP 专项未建 |
| recovered material/end-of-waste（再生料/废物终结） | ❌ 未覆盖 | 欧盟 end-of-waste 标准（JRC）、ISO 标准未接入 |

## 10. Saturation Results（**真实结果，不粉饰**）

```
EU = WEAK  (4/9)      └ 通过: SG2 源健康 / SG3 召回 / SG4 精度 / SG7 路线×4
                       未过: SG1(27.3%) SG5(74.3%) SG6(4) SG8(无数据) SG9(4)
US = WEAK  (3/9)      └ 通过: SG2 / SG3 / SG4
                       未过: SG1(43.8%) SG5(10.2%) SG6(4) SG7(2条路线) SG8 SG9
```
**why**：EU 短板在“角色级来源接入”（标准/Basel/OECD）与身份完整率；
US 短板在“州级与联邦法典源”（USC/eCFR/CBP）未接入 + 身份体系缺失（无 celex 等价物）。

## 11. Remaining Gaps

**P0 blocker**（阻断饱和宣言）：
1. **SG1 源宇宙覆盖**：EU 27.3% / US 43.8% / 成员国角色 5.1%（58 个期望角色未接入）
2. **SG5 身份完整性**：EU 74.3% / US 10.2%（美国记录缺官方标识体系）
3. **SG6/SG9 法律家族**：4 项未解决（ELV 2 / 2006/66 2）
4. **SG8 新颖度**：无收集回合数据（convergence 引擎未在本阶段跑）

**P1 important**：instrument 精度 0.786（占位标题/NIM 记录无类型信号）；
A1 无 Gold Set 正例；黑粉 trade/customs 专项（BIS/CBP）未建；eCFR/USC 未接入。

**P2 enhancement**：end-of-waste/再生料标准层；backfill overlay 尚未 --apply；
成员国公报逐国存活验证。

## 12. Regression Results

```
pytest tests/policy  → 46 passed
tests/test_portal_judge.py     → 21/21
relevance_browser 自检          → 20/20
tests/test_channel_dedupe.py   → 5/5
```
回归风险覆盖：§16 清单 12 项全部有断言（含 0 results≠saturated、blocked≠covered、
NIM≠complete、FR≠complete、老法规不排除、proposal≠effective、guidance≠binding、
C 不进主库、无字面词仍可 B、母语不误杀、家族未解决阻断、单通道不足）。

## 13. Changed Files

```
sources/regulatory-topics.yaml          新增（T01-T14）
sources/policy-acceptance-rules.yaml    新增（A1/A2/B/C/D + background_routes）
sources/instrument-types.yaml           新增（14 类型 + binding + 判例锚点）
sources/jurisdiction-registry.yaml      新增（EU/27/US/50州 角色矩阵）
sources/policy-goldset.yaml             新增（22 案例，6 holdout）
sources/search-boundary.yaml            修改（追加 policy_v2 段）
app/policy/{__init__,config,instruments,acceptance,source_universe,
            legal_identity,legal_graph,goldset,saturation}.py   新增（9 个）
scripts/audit_policy_universe.py        新增
scripts/evaluate_policy_goldset.py      新增
scripts/audit_legal_family.py           新增
scripts/audit_policy_saturation.py      新增
scripts/backfill_policy_metadata.py     新增
tests/policy/{test_acceptance,test_instrument_types,test_source_universe,
              test_legal_identity,test_legal_graph,test_goldset,
              test_saturation,test_config_single_source}.py     新增（8 个）
docs/phase4a/00_CURRENT_STATE_AUDIT.md  新增
docs/phase4a/PHASE4A_POLICY_ACCEPTANCE_SATURATION_REPORT.md  本文件
outputs/audit/legal_family_status.json  新增（家族审计产物）
```
**未改动**：outputs/*.jsonl 原始快照、review_decisions、现有 6 个脚本式测试、collectors。

## 14. Commits

本阶段提交：见 `git log`（commit message 前缀 `Phase 4A`）。

## 15. Next Recommended Phase

按真实缺口（非预设全球扩张）：
**Phase 4B 候选 A（建议优先）— Source Onboarding**：USC/eCFR、成员国公报、标准（CEN/ISO）、
Basel/OECD 的角色级接入 → 直击 SG1/SG5/SG6。
**候选 B — Identity Backfill**：美国记录官方标识体系（FR doc→CFR/U.S.C. 关联）+ overlay apply。
**候选 C — Black Mass Trade Line**：BIS/CBP/232 专项。
（先做 A/B，SG8 需在下一轮真实采集后自然产生。）

---
*本报告全部数字可由 §12 测试与 §19 命令复现；MOCK/FIXTURE 与 LIVE 结果已在各节标注。*
