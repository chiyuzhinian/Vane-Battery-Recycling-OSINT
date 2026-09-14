# Phase 4B-2B — Scale-Out Contract Freeze（Batch 1 冻结）

> 生成：2026-09-14 ｜ 阶段：4B-2B Batch 1 前置 ｜ 分支：`phase4b2a`
> 原则：本文件冻结 Batch 1 全程使用的接口。**除 STOP-THE-LINE（§14）
> 场景外，Batch 过程中不得修改核心 schema**；确需修改必须走
> SCHEMA_CHANGE 记录流程（见 §5），禁止 silent drift。

---

## 1. 冻结接口总表

| # | 接口 | 版本 | 载体（代码/数据） | 验证方式 |
|---|------|------|------------------|----------|
| 1 | Jurisdiction Contract | v1 | `sources/jurisdiction-onboarding/{JID}.yaml` + `app/policy/jurisdiction_onboarding.py` | yaml 加载无异常；`mandatory_source_roles` 与 registry role_schema 一致 |
| 2 | Source Role Schema | v1 | `sources/source-role-aliases.yaml` + `sources/jurisdiction-registry.yaml`（role_schema） | `scripts/audit_source_roles.py` |
| 3 | Source Proof Schema | v1 | `app/policy/source_proof.py` → `outputs/audit/source_proofs/{JID}.json` | `scripts/onboard_jurisdiction_sources.py` 真实采样产出；空样本不得 CONNECTED |
| 4 | Search Plan Schema | v1 / V2 | `sources/search-plans/{JID}_PLAN_V{n}.yaml` + `app/policy/search_plan.py` | `validate_plan()`；`plan_hash` 冻结（MODE B 只认同 hash FULL rounds） |
| 5 | Content State | v1（+2B1R 豁免、+2B §3 双口径） | `app/policy/content_state.py` | 六态枚举：FULLTEXT / METADATA_ONLY / PLACEHOLDER / FETCH_FAILED / PAYWALLED_KNOWN / NOT_APPLICABLE；豁免记录带 `content_exempt_reason=NO_INDEPENDENT_OFFICIAL_MANIFESTATION` |
| 6 | Domain Scope | v1 | `sources/domain-scope-rules.yaml` + `app/policy/domain_scope.py` | `domain_scope.py` 内 `version == 1` 校验；`scripts/audit_domain_acceptance_consistency.py` |
| 7 | Acceptance Class | v1 | `sources/policy-acceptance-rules.yaml` + `app/policy/acceptance.py` | `guard_class`/`guarded_effective_class`；`scripts/audit_domain_acceptance_consistency.py` |
| 8 | Legal Identity | v1 | `app/policy/legal_identity.py` + `identity_jurisdiction.py` / `identity_us.py` / `identity_hardening.py` | `scripts/audit_identity_completeness.py`；pattern 按辖区记录于 Contract `identity_strategy` |
| 9 | Coverage Matrix | v1 | `scripts/audit_jurisdiction_layers.py` / `audit_jurisdiction_contracts.py` / `audit_jurisdiction_coverage.py` → `outputs/audit/jurisdiction_{layers,contracts}.json` | eligible/plan_converged/route_families 字段稳定 |
| 10 | Convergence | v1 | `app/policy/rounds.py`（MODE A = DISCOVERY_EXPANSION；MODE B = CONVERGENCE_VALIDATION）+ `app/policy/convergence_layers.py` | 同 `search_plan_hash` + FULL rounds 才累计 streak；`scripts/audit_jurisdiction_convergence.py` |
| 11 | Scale-Out Gate | v1（4B-2B §2 聚合版） | `app/policy/saturation_gates.py::evaluate_scaleout_preconditions` + `aggregate_eligible` → `outputs/audit/scaleout_readiness.json` | **every-eligible 逐一评估**；输出 `eligible_total / eligible_pass / eligible_fail`；禁止 `eligible[0]` 样本代表 |

## 2. 版本规则（记录于各载体头部或常量）

- **schema_version**: 所有 `sources/*.yaml` 与 onboarding/source 配置均为 `version: 1`；运行时校验（如 `domain_scope.py` 强制 `version == 1`）。
- **rule_version**: `domain-scope-rules.yaml` / `policy-acceptance-rules.yaml` / `jurisdiction-priority-signals.yaml` 等规则的任何修改 = 版本升级事件，须走 §5 流程。
- **search-plan version rules**: Vn 递增仅在 MODE A（DISCOVERY_EXPANSION）期间；进入 MODE B 后 plan 冻结，`plan_hash` 记录于 `outputs/audit/jurisdiction_layers.json`。历史冻结 hash 示例：SE_V2=`b22caa0377a2`、US_CA_V2=`9ab375a053ba`、US_WA_V2=`69a4f37344f0`、FI_V1=`bd138f120fb1`。
- **acceptance_version**: v1（`policy-acceptance-rules.yaml`）。
- **domain_version**: v1（`domain-scope-rules.yaml`）。
- **identity_version**: v1（`legal_identity.py` + `identity_*.py`）。

## 3. Batch 1 范围（选择产物）

- 选择依据：`jurisdiction_priority_score` 重算（`scripts/audit_jurisdiction_priority.py`）→ `scripts/select_batch1_jurisdictions.py` → `outputs/audit/batch1_jurisdiction_selection.{json,csv}`。
- **EU（6）**：BE、HU、IT、SK、CZ、AT
- **US（8）**：US-MI、US-GA、US-IL、US-TN、US-TX、US-NV、US-OH、US-CO
- 约束核对：难度档 easy/medium/hard 全覆盖 ✅；US ≥2 个 `policy_signal ≥ 4` ✅（MI/IL/CO）。

## 4. 冻结期禁令（Batch 期间）

1. 不得修改 Acceptance / Domain / Identity / Convergence / Saturation 核心框架
   （除非命中 STOP-THE-LINE：P0 schema bug、raw evidence corruption、identity
   collision、acceptance/domain systematic error、dedupe corruption、
   Search Plan hash defect、Gate bypass）。
2. 不得为让数据"看起来正确"临时修改规则；新文书类型记
   `UNKNOWN_DOMAIN_PATTERN` 进入 review。
3. 不得将 metadata-only 计为 confirmed B；高价值全文须同时报告
   `fulltext_rate_strict` / `fulltext_rate_applicable` /
   `no_independent_manifestation_count`。
4. Source Proof 是硬门：无 `real_sample_urls` 不得 CONNECTED。

## 5. SCHEMA_CHANGE 记录流程（模板）

若确需修改冻结接口，在 `docs/phase4b2b/CHANGES.md` 追加：

```
## SCHEMA_CHANGE #<n> — <date>
- interface: <Jurisdiction Contract / Source Role / ...>
- reason: <STOP-THE-LINE 证据或明确理由>
- affected jurisdictions: [ ... ]
- backfill required: <yes/no + 范围>
- approved by: <本阶段记录>
```

并同步更新本文件 §1 表格版本号。**禁止 silent drift。**

## 6. 声明

本冻结在 Batch 1 首次 Source Proof 执行前生效；所有 Batch 1 步骤
（Source Universe → Endpoint Probe → Source Proof → Connector → Identity →
Domain → Acceptance → Topic → Evidence → Coverage → MODE A → Freeze →
MODE B → Convergence）均以本文件所列接口为准。
