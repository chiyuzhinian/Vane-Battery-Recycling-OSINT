# Phase 4B-1 · Step 7 报告 —— Legal Family 官方关系关闭（P0 unresolved = 0）

> 日期：2026-09-12 ｜ 状态：**Step 7 完成** ｜ 目标：**P0 legal family unresolved = 0** ✅

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| 官方关系解析 | `app/policy/family_official.py` | ✅ Cellar 入边谓词 + 合并逻辑 |
| 刷新 CLI | `scripts/refresh_legal_family.py` | ✅ 4 root × 7 关系（SPARQL） |
| 家族图升级 | `legal_graph.py` | ✅ 合并官方关系；自动读取官方产物 |
| 测试 | `tests/phase4b1/test_legal_family_official.py` | ✅ 5 条 |
| 数据 | `outputs/audit/legal_family_official.json`（新） + `legal_family_status.json`（更新） | ✅ |

**回归**：149 passed。

---

## 2. 官方关系（Cellar SPARQL，实测）

| Root | AMENDS | CORRIGENDUM_OF | REPEALS | TRANSPOSES | 提案 | 合并版本 |
|---|---|---|---|---|---|---|
| 32000L0053 ELV | **16**（32005D0063、32008L0112、32016L0774…） | **3**（R(01)/(02)/(03)） | 0 | 200 | 6 | 38 |
| 32006L0066 电池指令 | **5**（32008L0011/0012/0103、32013L0056…） | **4** | **1 → 32023R1542** | 200 | 6 | 14 |
| 32023R1542 电池法 | — | — | — | 200 | — | 36 |
| 32024R1157 WSR | **2**（32024R3230、32026R1703） | **5** | 0 | 0 | 2 | 13 |

**关键成果**：
- ELV 的 `AMENDS`、`CORRIGENDUM_OF` —— Phase 4A 遗留缺口 → **官方解决**
- 2006/66 的 `AMENDS`、`REPEALS` —— **官方解决**（REPEALS 证据 = 电池法 32023R1542，官方入边）
- 四个 P0 root 完整度全部 **1.0**，`P0 unresolved 总数 = 0` ✅（验收目标达成）
- 额外收获：官方 `TRANSPOSES`（NIM 转化措施）直接给出成员国措施清单（200 条/root）

---

## 3. 饱和门效果（Step 7 直接贡献）

```
EU: WEAK 4/9 → PARTIAL 6/9   （SG6/SG9 转绿）
US: WEAK 3/9 → PARTIAL 5/9
剩余：SG1（源宇宙口径待接新矩阵）、SG5（身份完整度待接 overlay）、SG7/SG8（Step 10）
```

---

## 4. 实现要点

- 谓词表固定（7 种）：`resource_legal_amends_/corrects_/repeals_/…` + `measure_national_implementing_implements_` + `act_consolidated_consolidates_` + 提案谓词。
- 方向为**入边**（`?src <pred> <root>`）：谁修订/废止/转化了本法。
- `absent_official`：查询**执行过且为空** → 官方缺席（≠ 缺口，报告中单列，不得算未解决）。
- `build_family_status()` 自动读取官方产物（文件缺失时保持 Phase 4A 行为，向后兼容）。

---

## 5. 变更文件

```
新增  app/policy/family_official.py
新增  scripts/refresh_legal_family.py
新增  tests/phase4b1/test_legal_family_official.py
修改  app/policy/legal_graph.py（合并官方关系 + 自动加载 + absent_official）
数据  outputs/audit/legal_family_official.json ｜ legal_family_status.json（完整度全 1.0）
```

## 6. 下一步（Step 8）

instrument 精度 ≥0.95：产出 `outputs/audit/instrument_mismatches.json`，
处理已定位项（CROSS tariff 词表、Notice 映射、40 CFR 273 universal waste、排放类 B 过宽）；
AI 仅辅助分类，**不得单独决定 binding force**。
