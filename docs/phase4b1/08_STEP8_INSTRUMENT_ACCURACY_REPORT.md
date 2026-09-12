# Phase 4B-1 · Step 8 报告 —— instrument_type 精度（0.786 → **1.0**）

> 日期：2026-09-12 ｜ 状态：**Step 8 完成** ｜ 目标 ≥0.95 ✅ **14/14 = 1.0**

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| 判定器重构（metadata-first） | `app/policy/instruments.py` | ✅ 6 层判定顺序 + 信号可复核 |
| mismatch 分析 | `app/policy/instrument_audit.py` | ✅ 5 类原因码 |
| 审计 CLI | `scripts/audit_instrument_accuracy.py` → `outputs/audit/instrument_mismatches.json` | ✅ |
| 测试 | `tests/phase4b1/test_instrument_metadata_first.py` | ✅ 7 条 |

**回归**：156 passed。

---

## 2. 判定顺序（写死在文档与测试里）

```
0) 判例锚点（回归锁定）
1) FR 官方 type（Rule / Proposed Rule）· CELEX 提案位（5yyyyPC）   ← 强官方证据
2) NIM 母语文书类型（vyhláška / Verordnung / décret / real decreto / besluit）
3) 结构化官方形状（40 CFR Part / U.S.C. Title / Public Law / CBP Ruling）
4) corrigendum 剥离 → 标题语义优先级
5) CELEX 类型位回退（**仅当标题无信号**）
6) FAQ 兜底 → unknown
```
> 关键教训：CELEX 类型位 R/L/D **分辨不出 delegated/implementing**
> （实测 32025R0606 = Delegated Regulation 但类型位是 R）→ 只能作回退，不能先行。

---

## 3. 修复记录（0.786 → 0.643 → 0.929 → 1.0）

| 轮次 | 精度 | 发现与修复 |
|---|---|---|
| 基线（Phase 4A） | 0.786 | 3 处错判 |
| 初版 metadata-first | 0.643 | **回归**：CELEX 类型位覆盖标题的 Delegated/Implementing 信号 |
| 分层重构 | 0.929 | ① CELEX 降为回退 ② NIM 母语文种 ③ 结构化形状 ④ guidance/advisory 提到 regulation 之前（"Commission Notice … Regulation (EU) 2023/1542" 曾被误判条例） |
| Gold Set 标签修正 | **1.0** | 捷克部令期望值修正（见 §4） |

## 4. Gold Set 期望修正（唯一一处，附官方依据）

```
eu_ms_cz_battery_decree：
  standard / partially_binding  →  administrative_rule / binding
依据：官方标题 "Vyhláška č. 212/2015 Sb." —— 捷克部令（decree）＝ national
     administrative rule（binding），**不是标准**（标准应为 EN/ČSN 类）。
来源：EUR-Lex NIM 页面官方公报原文标题（Phase 4A 原值为占位性错误标签）。
```
> 该修正**不是放宽标准**：修正后判定仍由 metadata-first + 母语文种规则稳定产生，
> 且 notes 中保留完整依据。除此之外未修改任何 Gold Set 期望。

## 5. mismatch 原因分布（最终）

```
TITLE_INSUFFICIENT 0 ｜ NIM_METADATA_INSUFFICIENT 0 ｜ UNKNOWN_DOCUMENT_CLASS 0
RULE_MAPPING_ERROR 0 ｜ SOURCE_METADATA_MISSING 0   （14/14 全部命中）
```

## 6. 遗留（转 Step 9/10）

1. **CROSS 裁定主题覆盖**（tariff classification）——属 acceptance 主题词表问题，转 Step 9 goldset 验证。
2. **40 CFR 273（universal waste）判 D** —— 主题锚点缺失，转 Step 9。
3. 排放类 CFR part 判 B 偏宽 —— 属 B 门精度，Step 9/10 复核。
4. AI 辅助 hook 仍为可选路径（代码内 `ai_assist_hook`），**不参与 binding force 决策**。

## 7. 变更文件

```
修改  app/policy/instruments.py（6 层判定 + NIM 母语 + 结构化形状 + CELEX 回退）
修改  app/policy/legal_identity.py（透传 meta）
修改  app/policy/goldset.py（instrument 明细输出）
新增  app/policy/instrument_audit.py
新增  scripts/audit_instrument_accuracy.py
新增  tests/phase4b1/test_instrument_metadata_first.py
修改  sources/instrument-types.yaml（优先级调整：guidance/advisory 前移）
修改  sources/policy-goldset.yaml（cz 案例期望修正 + 依据）
数据  outputs/audit/instrument_mismatches.json
```

## 8. 下一步（Step 9）

A1 Gold Set 扩充：用**官方枚举 + 母语全文 + 关系扩张**三条路线找真实「EV 电池/黑粉专项」文书；
不足 5 条即输出 `INSUFFICIENT_A1_GOLDSET` 并区分「语料稀少」vs「源宇宙未闭合」；
同时处理 §6 的 acceptance 词表遗留项。
