# Phase 4A — 当前状态审计（00_CURRENT_STATE_AUDIT）

> 生成时间：2026-09-12 ｜ 状态：**开发前审计**（本文件先于一切代码变更）
> 结论一句话：系统具备完整的"采集→判定→审核→反馈"工程能力，
> 但**缺少验收层**：无 Source Universe、无正式分类（A1/A2/B/C/D）、
> 无归属类型（instrument/binding）、无法律家族图、无 Gold Set、无饱和门。

---

## 1. 当前真实实现（Inspect First 结果）

### 1.1 已存在能力清单（**不可破坏**）

| 能力 | 实现位置 | 状态 |
|---|---|---|
| EU EUR-Lex 精确跟踪 / 锚点发现 / 关键词发现 | `app/connectors/eur_lex.py` + `scripts/discover_eu_acts.py` / `collect_eol_policies.py` | ✅ |
| 成员国 NIM 统一索引（27 国） | `scripts/collect_member_states_nim.py` | ✅ 396 条 |
| 成员国专线（DE/NL/ES/FR） | `app/connectors/{gesetze_de,bwb_nl,boe_es,dila_fr,datafair}.py` | ✅ |
| US Federal Register（8 簇×机构） | `app/connectors/us_federal.py` | ✅ |
| Browser capture 通道 | `app/connectors/browser.py` + `relevance_browser.py` | ✅ |
| 多语言相关性规则（三层判定器） | `app/core/relevance.py`（portal/policy）+ `relevance_browser.py`（browser） | ✅ 测试 21+20 |
| 黑粉监管四线 | `relevance.py::black_mass_lines` | ✅ |
| 原始 evidence 不可变 | `outputs/*.jsonl`（快照）+ 备份机制 | ✅ |
| 人工审核 overlay | `review_decisions.jsonl` + `app/api/store.py` 叠加 | ✅ |
| review feedback → 规则 → 重判 → 回归 | `scripts/rejudge_standard_v2.py` + `tests/test_portal_judge.py` | ✅ |
| convergence feedback | `app/core/feedback.py`（6 道防死循环闸门） | ✅ |
| source registry | `sources/*.yaml` + `app/core/geo.py` | ✅ |
| coverage audit（4 维） | `scripts/audit_collection_coverage.py` | ✅ exit 0 |
| 源真实性（源级） | `app/core/authenticity.py`（L1-L5 域名/TLS/跳转链） | ✅ |
| 去重（通道优先级） | `store.py` / `make_report.py` / `audit_collection_coverage.py` 三处一致 | ✅ |
| 面板 + 审核 UI（收录原因/备注） | `frontend/` + `app/api/main.py` | ✅ |

### 1.2 数据现状（2026-09-12）

```
全库 ~3.2k 条；US 1459（相关127）/ EU 149（相关109）/ 27 国 NIM 396
人工决策 25 条；测试断言 21+20+5
```

---

## 2. 七个专项审计问题的答案

### Q1. YAML 与 Python 是否存在重复维护规则？——**存在，且已漂移**

| YAML | Python（真源） | 漂移情况 |
|---|---|---|
| `search-boundary.yaml :: relevance.policy.must_match_any / reject_if_match / human_review` | `relevance.py` 中各自的常量与词表 | **已漂移**：两边词表已不同步（YAML 是 09-10 写的文档，Python 经 4 批用户判例迭代） |
| `search-boundary.yaml :: boundary.dimensions`（hr/feedstock/…） | `coverage.py` 硬编码同一维度 | 注释称"保持一致"，无机制保证 |
| `search-boundary.yaml :: source_authenticity` | `authenticity.py` 硬编码白名单/阈值 | 无机制保证 |
| `keyword-taxonomy-eol-battery.yaml :: terms_by_cluster`（C1-C8） | `policy-eu-us-eol-blackmass.yaml :: terms_by_cluster` + `policy-us.yaml :: topics` | **同一词表 2-3 份**（EU 关键词又在 taxonomy `discovery_terms`） |
| `eu-acts-tracked.yaml` | 运行时由 `build_plan()` 读取 | ✅ 该文件是真源 |

**关键 fact**：`grep search-boundary.yaml` 在 app/scripts 中**只命中注释引用**——
该文件**没有任何运行时消费者**，是纯文档。配置单一真源（规格 §12）当前为 **0/100**。

### Q2. search-boundary.yaml 是否仍存在过时模型？——**是，三处全中**

1. `time_window.policy.months = 36` —— 固定 36 个月窗口（对"当前有效法规"根本错误）
2. `languages: [zh, en]` —— 把检索语言与分析语言混为一谈（NIM 多语言教训已在代码里血流成河，配置未更新）
3. `size.policy_cells: EU 117 / US 91`（= 13 源 × 9/7 主题）—— **固定 source×topic 网格**，未按 Source Role 建模

### Q3. 文档定义与 runtime 实现是否漂移？——**是**

- `search-boundary.yaml`（09-10）描述 36 月窗口/双语言/固定网格 → runtime（09-12）已不遵守
- `docs/` 已有文档（运行架构、验证报告、本次的搜证体系说明）中规则与代码一致（刚写），但 `03_数据源管理和验证体系.md` 中字段口径早于当前 JSON schema
- `coverage.py` 注释引用 YAML 但无加载逻辑

### Q4. relevance.py 是否硬编码了与 YAML 重复的词表？——**是（大量）**

`relevance.py` 内嵌：`REJECT_IF_MATCH`、`V2_IN_SCOPE`、`V2_OFF_SCOPE`、`V2_REVIEW_TYPES`、
`PORTAL_DISPOSAL_PATTERNS`、`PORTAL_FINANCIAL_FRAME`、`PORTAL_MATERIAL_ANCHORS`、
`PORTAL_PROCEDURAL_TITLES`、`PORTAL_DOMAIN_ANCHORS`、`MEMBER_STATE_PATTERNS`、
`black_mass_lines` 词表…（约 15 组、数百条模式）——全部 Python 硬编码；
YAML 中同名清单**不再被读取**。任何调整都要改代码（违反"配置单一真源"）。

### Q5. policy coverage 是否错误复用企业情报模型？——**部分复用**

- `coverage.py`（企业线）：粒子模型 = 企业 × 维度，判 verified_claims 数量/质量/时效
- 政策线目前 = `audit_collection_coverage.py`（4 维对账）＋ YAML 里的 **固定 source×topic 格子**
- **缺失**：按 **Source Role**（官方公报/EUR-Lex 主体/授权法案/NIM/环境署/运输署/海关/标准/Basel/OECD…）
  的 `expected/configured/reachable/collector_available` 模型（规格 §5）——这是本阶段要补的核心

### Q6. relevant=True 是否混合了多类文书？——**是（全混）**

当前数据模型只有 `relevant/relevance_score/needs_human_review/rejected_by/hits`。
以下均以 `relevant=True` 出现，**无字段区分**：
- binding regulation（2023/1542）✓
- delegated/implementing（2025/606、2025/2289）✓
- proposal（52020PC0798）✓
- advisory（PHMSA 通告）✓
- official guidance（52025XC00214）✓
- 信息页（曾混入 3 条，已被 browser 判定的 info_page 规则拦在门外——**但仍是二值模型**）

**后果**：`audit exited 0` 无法证明"法规语料完整"，因为语料里混着非立法文书。

### Q7. source score 是否被错误用于政策法规真实性验收？——**源级有、文档级无**

- `authenticity.py`：L1-L5（域名白名单/同形字/编辑距离/TLS/主办方），输出**源级** `base_credibility`
- 政策文档的"真实性"事实上靠：CELEX 号 / NIM 号 / FR document_number 写在 meta 里——**ad-hoc，无 schema 校验**
- **缺失**：文档级 Legal Identity（canonical_id/jurisdiction/issuer/status…规格 §7）与其校验
- 未发现"用源分数判文档真伪"的错误用法；但反过来，**文档身份未被独立验证**（若 meta 缺失即不可审计）

---

## 3. 数据模型缺口（Phase 4A 要补的字段）

现有记录（outputs/*.jsonl）字段：
`evidence_id / region / channel / source_id / cluster_hint / url / title / publish_date /
relevant / relevance_score / needs_human_review / hits / rejected_by / meta / text / review_reason`

**缺口字段**（新模块产出，经 backfill 增量写入，**不覆盖旧证据**）：

```
acceptance_class      A1|A2|B|C|D
instrument_type       statute|regulation|directive|delegated_act|implementing_act|
                      administrative_rule|standard|official_guidance|advisory|
                      proposal|draft|consultation|information_page|news
binding_force         binding|partially_binding|non_binding|proposal|informational|unknown
legal_status          effective|not_yet_effective|amended|repealed|replaced|expired|
                      proposal|draft|unknown
topic_ids             [T01..T14]
legal_family          {root_act, relations:[...]}
identity              {canonical_id, jurisdiction, official_identifier, issuer, ...}
```

---

## 4. 兼容性风险与红线

| 风险 | 缓解 |
|---|---|
| 新字段写回破坏旧快照 | `backfill_policy_metadata.py` 默认 `--dry-run`；只**新增**键，不改既有键 |
| 新 acceptance 与现有判例冲突 | 新分类器**只做增强**：`acceptance.relevant = (class in A1/A2/B)` 需与现有 `relevant` 对齐——用 Gold Set 验证，**不先替换**运行时判定 |
| 重判跳过 NIM/browser 的特殊保护 | 保持（`is_nim`/`is_browser` 分流逻辑不动） |
| pytest 与脚本式测试并存 | 旧 6 个测试是脚本式（`main()`；`pytest -q` 不收集）→ 新增 `tests/policy/` 用 pytest 风格；旧测试继续用 `py tests/xxx.py` 跑 |
| frontend/面板读取 | 新字段全部加在记录顶层，面板向后兼容（未知字段忽略） |
| search-boundary.yaml 重构破坏企业线 | 只**新增** `policy_v2` 段（三层时间/语言模型/角色模型），旧段保留至迁移完成 |

**不能破坏的现有能力**（重申）：原始不可变 / review overlay / feedback / browser judge /
NIM 规则 / 回归测试 / dedupe / backup / convergence 六闸门 / source health / collectors。

---

## 5. 本阶段可复用模块（直接接线，不重写）

| 复用 | 用途 |
|---|---|
| `eur_lex.find_acts_by_title` | Legal Family 的关系发现（标题锚点=现存能力） |
| `discover_eu_acts.py` 锚点扫描 | family expansion 的执行器 |
| `review_decisions.jsonl` | Gold Set 的人类判据来源（25 条决策→初始银标） |
| `geo.py` SOURCE_COUNTRY | jurisdiction 映射基座 |
| `audit_collection_coverage.py` 4 维 | 并入 saturation 的 SG1 子检查 |
| `feedback.py` novel_rate | SG8 边际新颖度（保留门） |
| `authenticity.check_url` | Source Universe 的 reachable 验证 |
| `app/api/store.py` 只读路径 | audit CLI 的数据读取入口 |

---

## 6. 本阶段新增物（预告，最小增量）

```
sources/regulatory-topics.yaml          T01-T14 统一主题本体
sources/policy-acceptance-rules.yaml    A1/A2/B/C/D 判据（含正/反例）
sources/instrument-types.yaml           文书类型 + 约束力
sources/jurisdiction-registry.yaml      EU/27国/US联邦/50州 Source Role 矩阵
sources/policy-goldset.yaml             Gold Set（含 holdout≥20%）
app/policy/config.py                    Pydantic 强校验单一真源
app/policy/acceptance.py                分类器（AI 辅助但不单点）
app/policy/instruments.py               instrument/binding 判定
app/policy/source_universe.py           jurisdiction × role 状态机
app/policy/legal_identity.py            文档级身份解析与校验
app/policy/legal_graph.py               法律家族图 + 完整性
app/policy/goldset.py                   Gold Set 评估
app/policy/saturation.py                SG1-SG9 饱和门
scripts/audit_policy_universe.py        CLI
scripts/evaluate_policy_goldset.py      CLI
scripts/audit_legal_family.py           CLI
scripts/audit_policy_saturation.py      CLI
scripts/backfill_policy_metadata.py     兼容旧数据（默认 dry-run）
tests/policy/…                          8 个 pytest 测试文件
docs/phase4a/PHASE4A_…REPORT.md         最终报告
```

---

## 7. 审计结论（执行摘要）

1. **工程底座完备**（采集/判定/审核/反馈），本阶段**不重写**，只**增量**；
2. **验收层完全缺失**：五层（Source Universe → Acceptance → Legal Family → Gold Set → Saturation）从零建；
3. **配置漂移已坐实**：`search-boundary.yaml` 无消费者、词表多份维护、36 月窗口/双语言/固定网格过时——按 §12 统一到 `app/policy/config.py`（Pydantic）；
4. **数据模型缺口明确**：acceptance_class/instrument_type/binding_force/legal_status/topic_ids/legal_family/identity 七组字段，全部走 backfill 增量写入；
5. **口径风险最高处**：`relevant=True` 混装（Q6）——A1/A2/B/C/D 分类落地前，任何"饱和"结论都不可信。

---

*下一步：按规格 §2→§11 逐层实现（配置→分类→身份→家族→GoldSet→饱和），每层测试先行。*
