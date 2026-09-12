# Phase 4B-2A · Step 1 报告 —— Convergence 协议修正（Search Plan Versioning）

> 交付日：2026-09-13 ｜ 基线：Phase 4B-1 `1de0747`（历史只读，零修改）
> 本步解决规格第一优先级问题：**连续轮次之间搜索空间发生变化仍被计入同一 streak**。

---

## 1. 交付物

| 类别 | 文件 | 说明 |
|---|---|---|
| 引擎 | `app/policy/search_plan.py` | SearchPlan Pydantic 模型 + `plan_hash()`（sha256，11 类语义字段）+ `validate_plan()` 跨配置 fail-fast + `build_registry()` |
| 引擎 | `app/policy/rounds.py`（扩展） | `DEDUPE_RULE_VERSION` / `ROUND_MODES` / `VALIDITY_ENUM` / `HIGH_RISK_B_TOPICS`；`RouteResult` 增加 `source_success` / `transient_recovered` / `new_by_class` / `new_high_risk_B`；`build_round_record` 绑定 `plan_id/plan_hash/round_mode/round_validity`；`convergence_status(plan_hash=…, mode_required=…)` 严格化 + 高价值护栏 |
| 引擎 | `app/policy/convergence_recheck.py` | 历史轮次**只读**重标记（FULL/PARTIAL/INVALID + eligible_for_streak）+ 文件 sha256 承诺 |
| 引擎 | `app/policy/scope_saturation.py`（扩展） | SG8 读轮次：plan 绑定优先，legacy 视图显式 `plan_bound=false` |
| 配置 | `sources/search-plans/US_FED_PLAN_V1.yaml` | 冻结：5 机构 + 10 短语 + 7 CROSS 词 + 5 端点 + routes A/B/C/D |
| 配置 | `sources/search-plans/EU_SUPRA_PLAN_V1.yaml` | 冻结：6 CELEX 年前缀 + 9 关键词 + Basel 出版物 + 5 端点 |
| 执行器 | `scripts/run_discovery_round.py`（重构） | `--plan` / `--mode discovery|validation`；瞬态重试 1 次；逐源成功计数；validity 自动判定；索引双视图（`convergence` legacy + `plan_convergence` 严格） |
| 审计 | `scripts/audit_convergence_protocol.py`（新） | 产出 `outputs/audit/convergence_recheck.json` |
| 测试 | `tests/phase4b2a/`（6 文件 37 条） | hash 稳定性 / reset / validity / mode 分离 / class 级新颖度 / 重标记 |

## 2. 协议语义（写死并测试锁定）

```
plan_hash = sha256(canonical_json(plan_id, jurisdiction, scope, source_roles,
    source_endpoints, critical_sources, query_taxonomy_version, query_set,
    language_set, time_window, year_segments, discovery_routes,
    acceptance_rule_version, dedupe_rule_version))
（created_at / notes 不参与 hash —— 非语义变更不得制造伪 reset）

streak 资格（三者缺一不可）：
    plan_hash 一致  AND  round_mode == convergence_validation  AND  round_validity == FULL
    （PARTIAL / INVALID 一律中断扫描且不计数；legacy 轮次永不参与）

高价值护栏（converged 之外单独输出 blocked_by_high_value）：
    · 证据轮出现 new_A1 > 0              → 阻断
    · 证据轮出现 new_high_risk_B > 0     → 阻断（B ∩ T01/T02/T05/T10/T13）
    · 证据轮每一轮都新增 new_A2          → 阻断（持续出现核心政策语料 ≠ 饱和）

MODE A（discovery_expansion）：允许扩词/扩源/换路（记录 reset），不参与 SG8
MODE B（convergence_validation）：禁止改 routes/词表（`--plan` 校验直接拒绝）
```

## 3. 历史轮次只读重标记（`convergence_recheck.json`）

| 轮次 | 新协议评级 | 依据 | eligible_for_streak |
|---|---|---|---|
| EU_SUPRA R1（nov=1.0） | ✅ FULL | 无失败 | ❌（legacy 无 plan 绑定） |
| EU_SUPRA R2（nov=0.0） | ✅ FULL | 无失败 | ❌ |
| EU_SUPRA R3（nov=0.15） | ✅ FULL | 无失败（年段扩张不是失败，但本就属搜索空间变更） | ❌ |
| US_FED R1（nov=0.463） | ⚠️ PARTIAL | 1× FR ConnectError（critical 源端点级降级，角色主体完成） | ❌ |
| US_FED R2（nov=0.0294） | ✅ FULL | 无失败 | ❌ |
| US_FED R3（nov=0.1333） | ⚠️ PARTIAL | 2× FR ConnectError（同上） | ❌ |

**结论事实**：6/6 历史轮次均为 legacy（无 plan 绑定）→ 新协议下 streak=0
（与 4B-1 报告"未收敛"结论一致，但原因被正确归因：*实验协议缺陷 + 源宇宙未闭合*，而非"源已饱和"）。
网络失败 3 次全部入档为 `critical_endpoint_degraded`——**不得解释为"没有新增结果"**。

历史零改动承诺：artifact 记录 6 个轮次文件 sha256；测试 `test_convergence_recheck.py`
持续核验（历史被修改即红）。

## 4. Search Plan 注册表（冻结哈希）

| plan_id | hash（前 12） | scope | routes |
|---|---|---|---|
| `US_FED_PLAN_V1` | `67e228b3f54a` | US_FEDERAL | A,B,C,D |
| `EU_SUPRA_PLAN_V1` | `7416c831399d` | EU_SUPRANATIONAL | A,B,C,D |

> 4B-1 的"R1 宽词表 → R2 深词表 → R3 换词表"落为 `LEGACY_QUERY_SETS`（仅复现用）；
> V1 词表为三轮并集冻结 —— 自 V1 起每轮使用**完全相同**的搜索空间。

## 5. 测试与回归

```
tests/phase4b2a: 37 passed（hash 稳定性 14 变体 / reset / validity / mode / class 护栏 / 重标记+承诺）
全量回归: 216 passed（Phase 4B-2A 37 + Phase 4B-1 133 + Phase 4A 46）
旧脚本: 21/21 ｜ 10/10 ｜ 5/5 ｜ 4/4 全绿
兼容性：无 plan kwarg 的旧调用（含 4B-1 测试与旧索引）行为不变；`--show` 兼容旧索引
```

## 6. 遗留（后续步骤处理）

- 索引 `plan_convergence` 双视图将在下一次真实轮次运行时写入（Step 8）；
- `run_discovery_round.py` 的 EUR-Lex 通道重试依赖连接器内部实现（HTTP 直连通道已内置重试）；
- 参考管辖地（DE/NL/ES/FR）的 plan 文件在 Step 2/3 随契约与 pilot 一并生成。
