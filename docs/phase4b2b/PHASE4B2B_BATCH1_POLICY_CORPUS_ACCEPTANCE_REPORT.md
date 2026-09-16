# Phase 4B-2B Batch 1C —— Policy Corpus Production & Acceptance 报告

> 阶段：**Policy Corpus Production & Acceptance**（SOURCE CONNECTED → REPORTABLE POLICY CORPUS）
> 日期：2026-09-16 ｜ 分支：`phase4b2a` ｜ 测试：**432 passed**
> 纪律：不继续证明"网站能不能访问"；只回答"真正拿到了哪些政策、为什么可信、
> 业务部门可以拿哪些数据去汇报"。BE / US-OH / US-NV / US-IL 保持受阻，不伪造 corpus。

---

## 〇、一页结论

| 项目 | 结果 |
|---|---|
| **Batch 1 正式政策语料** | **127 条**（A2=4 ｜ B=17 ｜ C=102 背景 ｜ D=4 排除） |
| **已验收政策（ACCEPTED）** | **18 条**（+ REVIEW_REQUIRED 3 条待人工） |
| **JURISDICTION_CORPUS_ACCEPTED** | **5/6 可访问管辖地**（AT ✅ ｜ CZ ✅ ｜ SK ✅ ｜ IT ✅ ｜ US-TX ✅ ｜ HU ⚠️ 待补产）→ **83.3% ≥ 80%** |
| **Batch 1 Policy Corpus Gate** | **ACCEPTED**（P0=0 ｜ 高价值证据 100% ｜ 无证据污染 ｜ tests 0 fail） |
| **业务汇报数据** | **READY**（`outputs/reporting/BATCH1_POLICY_REPORTING_TABLE.csv / .xlsx`） |
| **A1 Gold Set** | **INSUFFICIENT**（verified=1 / holdout=0，目标 5/2 未变，如实） |
| **Batch 2** | **NOT READY**（前置：US 州通道 ×6、HU 补产、T06/T08/T13/T14 语料、A1 案例） |

---

## 一、执行概览（Step 0–8）

| Step | 内容 | 结果 |
|---|---|---|
| 0 | 语料机器与数据就绪审计 | ✅ 工具族齐备（acceptance / black_mass / identity / goldset / domain_scope） |
| 1 | AT 收敛链（adapter + MODE B） | ✅ AT_PLAN_V1 streak=2（R1–R4 FULL）；语料 16 文档 |
| 2 | EU5 语料生产（V2 扩产） | ✅ CZ/SK/HU V2 计划 + route C 引用扩张；CZ R7 +4、SK R6 +2、HU R5 耗尽 |
| 3 | US Batch1 MODE A | ⚠️ 部分：**US-TX 打通**（SPA 逆向→TCSS 原始域 + 章枚举 390→10 种子 + V2 收敛）；NV=Cloudflare 403；IL=TLS 超时；GA=SPA；MI/OH 维持受阻 |
| 4 | Policy Acceptance Table | ✅ 23 字段主表 + 每辖区 9 件验收包 + overlay 体系 |
| 5 | 验收 Gate | ✅ `outputs/acceptance/gates/batch1_jurisdiction_gates.json` |
| 6 | 业务汇报总表（中文） | ✅ csv + xlsx（17 必备字段 + 3 证据附列） |
| 7 | A1 Gold Set | ⚠️ INSUFFICIENT（1/0） |
| 8 | 本报告 + 终端摘要 | ✅ |

---

## 二、语料交付总览

### 2.1 每个国家/州（Q2）

| 辖区 | 记录 | A1 | A2 | B | C(背景) | D(排除) | Gate | 备注 |
|---|---|---|---|---|---|---|---|---|
| AT 奥地利 | 24 | 0 | 0 | **12** | 12 | 0 | ✅ | Batterienverordnung / AWG / ADR 锂电系列 |
| HU 匈牙利 | 31 | 0 | 0 | 0 | 30 | 1 | ⚠️ | 公报通道 3 实体文书（薄）；NIM 元数据 27 条背景 |
| CZ 捷克 | 36 | 0 | 0 | **1** | 34 | 1 | ✅ | 170/2010 电池专条 + 273/2021 等；NIM 元数据 28 条背景 |
| SK 斯洛伐克 | 17 | 0 | 0 | **2** | 15 | 0 | ✅ | 79/2015 / 373/2015 体系；slov-lex 专线 |
| IT 意大利 | 13 | 0 | **4** | 0 | 9 | 0 | ✅ | D.Lgs 188/2008 等 2006/66 转化法令（标题补全后回升 A2） |
| US-MI 密歇根 | 0 | — | — | — | — | — | ⛔ | legislature 403；仅 EGLE 浏览器样本（非文书） |
| US-GA 佐治亚 | 2 | 0 | 0 | 0 | 0 | 2 | ⛔ | 官方站 JS 渲染（SPA）；仅来源页样本 |
| US-IL 伊利诺伊 | 0 | — | — | — | — | — | ⛔ | ilga.gov TLS 握手超时（本出口） |
| US-TN 田纳西 | 0 | — | — | — | — | — | ⛔ | 通道未建立（骨架契约） |
| **US-TX 得克萨斯** | **4** | 0 | 0 | **2** | 2 | 0 | ✅ | TCSS 静态法典 10 章种子；2B+2C |
| US-NV 内华达 | 0 | — | — | — | — | — | ⛔ | NRS 请求 Cloudflare 403（本地出口实证） |
| US-CO 科罗拉多 | 0 | — | — | — | — | — | ⛔ | 通道未建立（骨架契约） |
| （BE 比利时） | — | — | — | — | — | — | ⛔ | MULTI_VANTAGE_BLOCKED（前阶段实证，保持） |
| （US-OH 俄亥俄） | — | — | — | — | — | — | ⛔ | 品牌 404 WAF + codes 超时（三通道实证，保持） |

> 主表 127 行明细：`outputs/acceptance/batch1_policy_acceptance.csv / .json`。
> "D=排除"与"背景 C"按 §八 状态机标注，**不以 `relevant=true` 作为终态**。

### 2.2 A1/A2/B/C/D 分布（Q3）

```text
A1 = 0    A2 = 4    B = 17    C = 102（背景/索引层 55 条为 NIM 元数据）  D = 4
```

- 高价值（A1/A2/B）合计 **21 条**；
- C 背景中 **55 条为欧盟 NIM 多语言实施措施索引**（设计上封顶 C、不充当 national corpus 证据）；
- D 排除 4 条（GA 来源页样本 2 + HU 公报卷宗 1 + CZ 越域护栏降级 1）。

### 2.3 记录级状态（§八）

```text
ACCEPTED = 18 ｜ REVIEW_REQUIRED = 3 ｜ BACKGROUND = 102 ｜ EXCLUDED = 4
```

REVIEW_REQUIRED 3 条 = B_CANDIDATE 口径（缺条款定位或身份不全，不得 confirmed B）。

---

## 三、约束力与文书类型（Q4）

| 维度 | 数值 |
|---|---|
| binding（A–C 区间内） | **103 / 123**（其余 20 条类型未定，多为 ADR 通告类与元数据层） |
| 高价值类类型分布 | regulation 3 ｜ statute 3 ｜ administrative_rule 1 ｜ unknown 14（AT ADR 通告 + 州法章） |
| 新增法定名称模式 | zákon/vyhláška/nařízení/nariadenie/rendelet/decreto/verordnung/health-and-safety-code（本阶段并入 `instrument-types.yaml`） |

**binding 类示例**：AT Batterienverordnung、AT AWG、CZ 542/2020 系、SK 79/2015 系、
IT D.Lgs 188/2008（2006/66/CE 转化）、TX HSC 361（Solid Waste Disposal Act）。

---

## 四、主题与黑粉六线（Q5 / Q6）

### 4.1 T01–T14 覆盖（Batch1 全局，docs 计数）

| T01 | T02 | T03 | T04 | T05 | T06 | T07 | T08 | T09 | T10 | T11 | T12 | T13 | T14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **21** | 4 | 1 | **13** | 0 | 7 | 0 | 1 | 4 | 9 | 1 | 0 | 0 |

- 强项：**T02 回收网络 / T05 贮存运输 / T11 追溯**（AT ADR + Batterienverordnung 贡献大）；
- 缺口：**T06 拆解前处理 / T08 回收效率 / T13 进出口 / T14 财税** = 0（US 州级与 EU 深度文书缺口所致，列入 Batch 2 前置）。

### 4.2 Black Mass 六线（现有词表口径）

| 线 | 命中 docs |
|---|---|
| waste_status 废物定性 | 0* |
| hazardous 危废定性 | 1 |
| transport 运输（危货） | **15** |
| transboundary 越境转移 | 0 |
| customs 海关/进出口 | 0 |
| end_of_waste 再生料/废物终结 | 1 |

\* 词表以英/中为主，德/捷/斯洛伐克/意语"废物定性"表述未全覆盖——**词表扩展为 Batch 2 工作项**（如实标注，不虚增）。

---

## 五、管辖地验收（Q7 / Q8 / Q12）

### 5.1 JURISDICTION_CORPUS_ACCEPTED 明细

| 检查项（§十二） | AT | CZ | SK | IT | US-TX | HU |
|---|---|---|---|---|---|---|
| critical source coverage ≥90% | ✅ | ✅ | ✅ | ✅ | ✅（TCSS 代偿，PARTIAL 通道注明） | ✅ |
| identity completeness ≥95% | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 高价值文书 ≥1 | ✅(12) | ✅(1) | ✅(2) | ✅(4) | ✅(2) | ❌(0) |
| A1/A2/B applicable fulltext ≥95% | ✅ | ✅ | ✅ | ✅ | ✅ | vacuous |
| B clause evidence ≥95% | ✅ | ✅ | ✅ | vacuous | ✅ | vacuous |
| domain contradiction = 0（护栏后） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Topic Mapping 无 P0 缺陷 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MODE B converged / NOT_YET 声明 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **结论** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |

### 5.2 证据完整性（§九，全局）

```text
A2: n=4  fulltext 4/4 (100%)  条款引用 3/4
B : n=17 fulltext 17/17 (100%) 条款引用 17/17 (100%)
三口径保留：strict_fulltext_rate / applicable_fulltext_rate /
            no_independent_manifestation_count=0
```

### 5.3 每个辖区的验收包（§十一）

`outputs/acceptance/{JID}/` ×9 件：`accepted_policies.csv` · `coverage.json` ·
`topic_matrix.json` · `black_mass_matrix.json` · `source_roles.json` ·
`convergence.json` · `blocked_gaps.json` · `evidence_samples.md` · `summary.md`
（12 个 Batch1 辖区全部生成）。

### 5.4 Batch 1 验收（Q12）

§十三 口径（**可访问管辖地**为分母——受阻辖区单独列示）：

```text
可访问（本阶段实证可采）：AT / HU / CZ / SK / IT / US-TX = 6
达到 CORPUS_ACCEPTED：AT / CZ / SK / IT / US-TX = 5  → 5/6 = 83.3% ≥ 80% ✅
P0 = 0 ✅ ｜ 高价值证据 = 100% ✅ ｜ 原始证据无污染 ✅ ｜ tests 432 passed ✅
```

**Batch 1 Policy Corpus = ACCEPTED**（附注：HU 需补产后方可升级；US 州级覆盖薄弱，
详见第十章 Batch 2 前置）。

---

## 六、BE / US-OH 与受阻州明细（Q9）

| 辖区 | 状态 | 证据 |
|---|---|---|
| BE | MULTI_VANTAGE_BLOCKED | 本地 + 云（aliyun-cn）双出口实证（ejustice 超时/拒绝）；前阶段已定案 |
| US-OH | MULTI_VANTAGE_BLOCKED | ohio.gov 品牌 404（全州 WAF）+ codes.ohio.gov ERR_TIMED_OUT；本地/云/真实浏览器三通道终判 |
| US-NV | 新受阻 | NRS 章节请求 **Cloudflare 403 挑战页**（本地出口；轮次 R1 fail=2 存证） |
| US-IL | 新受阻 | ilga.gov **TLS 握手超时**（本出口连不上，非页面级 403） |
| US-GA | 通道缺口 | 官方站 JS 渲染（SPA），未定位可静态采集面 |
| US-MI | 部分受阻 | legislature.mi.gov 403；EGLE 仅浏览器样本（非文书，不充当 corpus） |
| US-TN / US-CO | 通道未建立 | 维持骨架契约（TN/CO 未在本阶段找到合法静态通道） |

> 受阻辖区**从 corpus completeness 分母与 source-access 分母中分别说明**（本报告五/六章分列），不伪造 complete。

---

## 七、A1 Gold Set（Q10）

```text
verified = 1（us_ca_sb615_traction，既有）
holdout = 0
status = INSUFFICIENT_A1_GOLDSET  → 目标 verified ≥5 / holdout ≥2 未达标（如实）
```

本阶段语料生产中的自然 A1 扫描（EUR-Lex A/B 路线 + FR 引号短语）均为 0 命中；
A1 定义**未做任何放宽**。最近邻候选（留待 Batch 2）：FMVSS 305a（EV 电池安全，联邦）、
EU 2023/1542 授权法案系列（supra 层）。

---

## 八、MODE B 收敛（Q11）

| 计划 | 收敛 | streak | 说明 |
|---|---|---|---|
| AT_PLAN_V1 | ✅ | 2 | R1–R4 FULL，16 文档 |
| CZ_PLAN_V1 | ✅ | 2 | 6 轮 |
| CZ_PLAN_V2 | 声明 NOT_YET | 0 | R7 扩产 +4（1B+3C）；验证轮未排（扩产空间已显性化） |
| SK_PLAN_V1 | ✅ | 2 | 5 轮 |
| SK_PLAN_V2 | 声明 NOT_YET | 0 | R6 +2（1B+1C） |
| HU_PLAN_V1 / V2 | ✅ / NOT_YET | 2 / 0 | V2 R5 零新增（耗尽） |
| IT_PLAN_V1 | ✅ | 2 | — |
| US_TX_PLAN_V2 | ✅ | 2 | R3 +2（C）；R4/R5 零新增 FULL |
| SE/FI/US-CA/US-WA（pilot） | ✅ | 2 | reference/regression，不计入 Batch1 新增 |

**读法**：V1 全部收敛；V2 为扩产新增搜索空间（按纪律 reset streak），
其收敛状态以**显式 NOT_YET_CONVERGED 声明**进入验收（§十二允许）。

---

## 九、业务汇报数据（Q13）

**READY** — `outputs/reporting/BATCH1_POLICY_REPORTING_TABLE.csv / .xlsx`
（`openpyxl` 生成 xlsx；CSV 为 UTF-8-BOM，中文 Excel 直开）。

- 行范围：ACCEPTED 18 + REVIEW_REQUIRED 3 + BACKGROUND（企业可读背景） 102 → 123 行；
- 必备 17 列（国家/州、政策名称、编号、层级、类型、当前状态、发布/生效日期、
  A1/A2/B/C/D、监管主题、黑粉关联、动力电池关联、核心要求、对回收企业影响、
  证据条款、官方链接、审核状态）+ 3 证据附列（`policy_summary_cn` / `affected_actor` /
  `affected_material`）；
- **中文生成规则**：受控本体词表（T01–T14 的 `name_zh`/`description`/`business_relevance`）
  + 证据条款引用；**不自动翻译原文、不脱离 evidence 推断**。原文引用与官方链接保留在
  同行"证据条款 / 官方链接"列，供人工复核；
- 发布/生效日期未定位时为"待补"（不猜测）；`effective_status_cn` 由标题级标记判定
  （修订法令/待人工核验等）。

---

## 十、Batch 2 评估（Q14）

**NOT READY**。前置条件（按优先级）：

1. **US 州级通道**（MI / GA / IL / TN / NV / CO）：需要美区 vantage（Cloudflare/WAF）
   + SPA 逆向（GA/TX 模式）或官方 API 清单化；当前仅 TX 达标；
2. **HU 补产**：公报通道实体文书 3 份——需 njt.hu 立法库恢复或公报期内嵌文书枚举；
3. **主题/黑粉词表扩展**：T06/T08/T13/T14 与多语"废物定性"（Batch1 命中 0）；
4. **A1 案例累积**：目标 5/2 不变；
5. V2 计划的收敛循环（CZ/SK/HU，各需 2 个验证轮）。

---

## 十一、工件清单与复现

```text
outputs/acceptance/batch1_policy_acceptance.csv / .json   （23 字段主表，127 行）
outputs/acceptance/gates/batch1_jurisdiction_gates.json
outputs/acceptance/{JID}/ × 9 件（12 辖区）
outputs/reporting/BATCH1_POLICY_REPORTING_TABLE.csv / .xlsx
outputs/overlays/corpus_title_overlay.jsonl   （标题补全 8 条）
outputs/overlays/identity_overlay.jsonl       （身份补全 8 条）
```

复现命令：

```powershell
py scripts/build_acceptance_table.py            # 全量重建主表/包/Gate/业务表
py scripts/enrich_corpus_titles.py              # 标题 overlay 重建
py scripts/build_identity_overlay.py            # 身份 overlay 重建
py -m pytest tests -q                           # 432 passed
```

---

## 十二、纪律声明

- **不伪造**：BE / OH / NV / IL 受阻如实入档；HU 高价值=0 如实标 REVIEW_REQUIRED；
- **原始 evidence 不可变**：标题/身份补全走 overlay（`outputs/overlays/`，审计可回溯）；
- **双语义修复**：`classify_record` 的 `relevant` 陷阱已修（系统产出记录不再被误判 D，
  +3 回归测试）；
- **domain 护栏并入终类**：OUT_OF_SCOPE+强类→D、SUPPORTING+A1/A2→B（2B1 口径），
  越域降级 2 条记录在案；
- **分母纪律**：corpus completeness 与 source-access 分母分列（第五章 /
  第六章），NIM 发现层不计入 identity 分母；文档数量仅为描述指标。

---

## 附录 A：终端摘要（§十七）

```text
PHASE 4B-2B BATCH 1C RESULT

EU:  selected: 6 ｜ accessible: 5 ｜ corpus_accepted: 4 ｜ blocked: 1(BE)
US:  selected: 8 ｜ accessible: 1 ｜ corpus_accepted: 1 ｜ blocked: 7(OH/NV/IL/GA/MI/TN/CO)

Accepted policies: A1:0  A2:4  B:17  C:102  D:4   （主表 127；含背景）
Binding: 103/123（A–C）
Evidence completeness: A1: —   A2: 100%   B: 100%   B clause: 100%
Identity: 全部达标辖区 ≥95%（overlay 后）
T01-T14: T02=21 T05=13 T11=9 T07=7 T03=4 T10=4 T01=1 T04=1 T09=1 T12=1
         缺席：T06 T08 T13 T14
Black Mass: transport=15 ｜ hazardous=1 ｜ end_of_waste=1 ｜ waste_status=0 ｜
            transboundary=0 ｜ customs=0
Converged jurisdictions: AT CZ SK IT US-TX（5/6 可访问）＋ pilot 4
Partial jurisdictions: HU（高价值=0）
Blocked jurisdictions: BE US-OH US-NV US-IL US-GA US-MI US-TN US-CO
Gold Set: INSUFFICIENT（verified=1 / holdout=0）
P0: 0        Tests: 432 passed
BATCH 1 POLICY CORPUS: ACCEPTED
BUSINESS REPORT DATA: READY
BATCH 2: NOT READY
```
