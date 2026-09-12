# Phase 4B-1 · Step 9 报告 —— A1 Gold Set 搜证（真实结果：INSUFFICIENT_A1_GOLDSET）

> 日期：2026-09-12 ｜ 状态：**Step 9 完成（如实 PARTIAL）**
> 纪律：**绝不为凑 ≥5 人工伪造或降格 A1**；不足即输出 INSUFFICIENT_A1_GOLDSET

---

## 1. 搜证过程（三条路线全部跑过）

| 路线 | 执行 | 结果 |
|---|---|---|
| A/B EUR-Lex 官方检索（EV battery / traction battery / black mass 关键词） | `_fetch_by_keyword`（已验证通道） | 0 条候选通过标题级 A1 锚点 |
| B FR 引号短语（`"electric vehicle battery"` 等 3 词） | FR API 实时 | 26 条候选；**0 条标题级 A1** |
| C 自有语料全量扫描（3202 条标题 × EV/ELV/黑粉锚点 + 电池词） | 本地 | 16 条命中，均为：ELV/电池横向指令（A2）、EP 决议（非立法）、**BEV 整车贸易救济**（对象=整车，非牵引电池/黑粉） |

产物：`outputs/audit/a1_candidates.json`（26 条候选 + 逐条筛选理由）。

---

## 2. 真实结论与原因区分（用户要求）

```
a1_verified_count = 0  ｜  a1_holdout_count = 0
a1_goldset_status = INSUFFICIENT_A1_GOLDSET
```

**原因 A（语料稀少，已跑过的路线证明）**：
EU 超国家层面专门以「EV 牵引电池 / 黑粉」为对象的立法/授权法案极少 ——
核心立法（2023/1542、2025/2289、2018/849…）都是**横向电池法体系** → 按规格归 A2。
BEV 贸易救济条例（2024/785、2024/1866、2024/2754）对象是**整车进口**（powertrain
描述词），不满足 A1 的「EV 电池/黑粉」对象门槛 → 不得降格充数。

**原因 B（源宇宙未闭合，属 4B-2 范围）**：
- **US 州级**（WA/CO/IL/MN/ME… 多州有 EV 电池/电池 EPR 专项立法）→ US_STATES 仍 0/51；
- **EU 成员国**深度采集（NIM 索引之外的国家公报/部令原文）→ 仍为 4B-2；
- 以上两层正是 A1 型文书的真实栖息地（州级 EV 电池法案/成员国 EV 电池专条）。

---

## 3. 本轮 Gold Set 变更（仅新增，附依据）

新增 **2 个 hard B 案例**（标题无 battery，正文条款直接约束电池回收）：

| id | must_find | 期望 | 依据 | holdout |
|---|---|---|---|---|
| `hard_b_rcra_hazardous_waste` | `40 CFR Part 261` | B / regulation / binding | eCFR 官方 XML；T10 主题 + 条款证据（实测 B） | false |
| `hard_b_hazmat_shippers` | `49 CFR Part 173` | B / regulation / binding | eCFR 官方 XML；T05 主题 + 条款证据 | **true**（规则冻结后才发现） |

**未新增**：A1（不足）、hard D（下轮随 US 州级一起做，需真实样本）。

## 4. 验收指标（当前真实值）

```
cases_total = 24 ｜ found = 24 ｜ precision = 1.0 ｜ recall = 1.0 ｜ F1 = 1.0
a2_recall = 1.0 ｜ b_recall = 1.0（含 2 个 hard B）｜ a1_recall = null（无 A1 案例）
instrument_type_accuracy = 1.0（Step 8）
```

## 5. 变更文件

```
修改  app/policy/goldset.py（a1_verified_count / a1_holdout_count / a1_goldset_status）
修改  sources/policy-goldset.yaml（+2 hard B，24 案例）
新增  tests/phase4b1/test_goldset_a1_status.py
新增  scripts/discover_a1_candidates.py（三路线 A1 搜证，可复跑）
数据  outputs/audit/a1_candidates.json
```

**测试**：159 passed。

## 6. 下一步（Step 10）

LIVE 轮次 ×3（≥3 类独立路线）+ scope 饱和（EU_SUPRANATIONAL / EU_MEMBER_STATES /
US_FEDERAL / US_STATES）+ Black Mass 六线矩阵 + 16 节最终报告 + 终端摘要；
SG1 接线到新矩阵、SG5 接线到 overlay 身份（当前两处仍读旧口径）。
