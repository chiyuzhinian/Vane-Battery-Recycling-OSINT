# Phase 4B-1 · Step 2 报告 —— US Federal Legal Identity Hardening & Source Alias 对账

> 日期：2026-09-12 ｜ 状态：**Step 2 完成**（FR 身份富化 + backfill 扩展 + 别名对账）
> 纪律：原始 evidence 不可变；overlay 增量写入；dry-run 默认；失败分类不静默。

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| US 身份解析 | `app/policy/identity_us.py` | ✅ FR 官方字段解析（citation/RIN/docket/cfr_references/type/effective_on） |
| backfill 纯逻辑 | `app/policy/backfill.py` | ✅ 过滤（region/role/only-missing/limit）· overlay 行 · 完整度度量 |
| 富化 CLI | `scripts/enrich_us_identity.py` | ✅ FR 单文档 API + 本地缓存 + 失败分类；默认 dry-run |
| backfill CLI（升级） | `scripts/backfill_policy_metadata.py` | ✅ 新参数 + before/after + failed/ambiguous/human review |
| 别名对账 | `sources/source-role-aliases.yaml` + `expand_role_sources()` | ✅ 逻辑源名 → 真实 source_id |
| 矩阵升级 | `scripts/audit_source_roles.py` | ✅ evidence 计数经别名展开 + 新增 `evidence_sources` 列 |
| 测试 | `tests/phase4b1/`（+3 文件 21 条） | ✅ **99 passed**（本阶段 53 + Phase 4A 46） |

复现命令：
```
py scripts/enrich_us_identity.py --source-role FEDERAL_REGISTER --limit 120 --apply
py scripts/backfill_policy_metadata.py --region US --source-role FEDERAL_REGISTER --limit 120
py scripts/audit_source_roles.py
py -m pytest tests/phase4b1 tests/policy -q
```

---

## 2. US 联邦身份富化（真实运行结果）

**数据源**：`GET federalregister.gov/api/v1/documents/{num}.json`（公开官方，无需 Key）

```
目标 120 条 → ok=15 cache=105 failed=0 ambiguous=0 无文档号=0（耗时 7.2s，二次运行）
累计 fr_identity_overlay.jsonl = 135 个文档
```

真实身份字段（以 PHMSA 锂电池 IFR `2019-03812` 为例，全部取自官方 JSON）：

| 字段 | 值 |
|---|---|
| canonical_id | `FR:2019-03812` |
| official_identifier | `84 FR 8006`（FR 引用号） |
| fr_type / instrument | `Rule` → `administrative_rule` / `binding` |
| RIN | `2137-AF20` |
| cfr_references | `49 CFR 172 / 173 …`（**Step 3 的 FR→CFR 官方证据**） |
| docket_ids | `PHMSA-2016-0014 (HM-224I)` |
| effective_on / status | `2019-03-06` → `effective` |

纪律落实：
- **Notice 等宽泛类型不猜类型**（`instrument_type` 留空并记录 issue，交 Step 8 metadata 全量处理）
- `Proposed Rule` → `proposal`（不得冒充已生效法规）
- 未来生效日期 → `not_yet_effective`

---

## 3. backfill 前后完整度（真实度量）

```
US FEDERAL_REGISTER 前 120 条：
身份完整度 before = 15/120 (12.5%)  →  after = 99/120 (82.5%)   Δ +70.0%
failed = 0 ｜ ambiguous = 0 ｜ human_review_required = 4
```

- **未富化的 21 条仍未完整** = FR 官方类型为 Notice 等未映射类型（诚实保留，不臆造）
- 文书类型分布（官方元数据优先后）：`administrative_rule 63 / proposal 33 / unknown 21 / official_guidance 2 / consultation 1`
- 产物：
  - `outputs/fr_identity_overlay.jsonl`（135 行，FR 官方身份）
  - `outputs/policy_metadata_overlay.jsonl`（本次 120 行；增量合并，保留旧行）
- **原始 evidence 未改动**（`outputs/*.jsonl` 只读）

---

## 4. Source Alias 对账（矩阵真实修正）

**问题**：注册表登记的是逻辑源名，库内是真实 `source_id` → 部分角色 `evidence_count` 误记 0。

**修复**（`sources/source-role-aliases.yaml` + 通配展开，别名键必须在注册表中，测试 fail-fast）：

| 逻辑源 | 展开为 | 结果 |
|---|---|---|
| `eu_nim` | `eu_nim_*` | EURLEX_NIM：0 → **396** |
| `eu_eurlex_waste_shipment` | `eu_eurlex_battery_reg` + `eu_eurlex_keyword` | CUSTOMS_TRADE：0 → **586** |
| （组合） | + 4 国专线 | MEMBER_STATE_LEGISLATION：134 → **530** |

**矩阵变化（EU_SUPRANATIONAL）**：
```
mandatory  4/9  (44.4%)  →  6/9  (66.7%)
critical   4/8  (50.0%)  →  5/8  (62.5%)      （NIM、CUSTOMS_TRADE 升为 CONNECTED）
US_FEDERAL 不变：mandatory 9/12 (75%) ｜ critical 6/9 (66.7%)
```
> 说明：`eu_eurlex_waste_shipment` 与电池法共用同一 EUR-Lex 通道（不同锚点），
> 别名语义是「该通道服务此角色」，不是重复造数——`evidence_sources` 列逐行可审计。

---

## 5. 新增/修改文件

```
新增  sources/source-role-aliases.yaml
新增  app/policy/identity_us.py
新增  app/policy/backfill.py
新增  scripts/enrich_us_identity.py
修改  scripts/backfill_policy_metadata.py     （薄封装 + 新参数 + 完整度报告）
修改  scripts/audit_source_roles.py           （别名展开 + evidence_sources 列）
修改  app/policy/config.py                    （AliasConfig + load_aliases）
修改  app/policy/source_access.py             （expand_source_patterns / expand_role_sources）
新增  tests/phase4b1/{test_identity_us,test_identity_backfill,test_source_aliases}.py
新增  tests/phase4b1/fixtures/fr_{2019-03812,2024-09094}.json   （真实官方夹具，公开数据）
新增  docs/phase4b1/02_STEP2_US_IDENTITY_BACKFILL_REPORT.md（本文件）
产物  outputs/fr_identity_overlay.jsonl · outputs/policy_metadata_overlay.jsonl
      outputs/cache/fr_documents/*.json · outputs/audit/source_role_gap_matrix.{json,csv}
```

---

## 6. 测试结果

```
tests/phase4b1（Step 2 新增 21 条）
  test_identity_us.py        FR 官方身份解析（真实夹具 8 条）
  test_identity_backfill.py  过滤/合并/完整度/dry-run（8 条）
  test_source_aliases.py     别名展开 + fail-fast（5 条）
tests/phase4b1（Step 1 32 条）+ tests/policy（Phase 4A 46 条）
合计：99 passed / 0 failed

旧脚本式回归：21/21 · 10/10 · 5/5 · 4/4（未破坏）
```

> 环境备注：本机 `%TEMP%\pytest-of-*` 存在权限缺陷（WinError 5），测试改用仓库内临时目录（已注明）。

---

## 7. 遗留（不隐藏）

1. **ambiguous 口径**：初版误把"类型未映射备注"计为 ambiguous → 已修正为 `fr_ambiguous` 标志（现为 0）。
2. **overlay 覆盖范围**：`fr_identity_overlay` 135 文档 vs `policy_metadata_overlay` 120 行（两脚本选取窗口不同）；
   Step 10 全量回填时统一。
3. **21 条 Notice 类未映射**：等 Step 8 metadata-first 全量判定（不提前猜）。
4. **US_CODE / CBP / PUBLIC_LAW 仍 0 数据**：Step 4 / Step 5 接入 collector 后自然消除。

---

## 8. 下一步（Step 3）

`app/connectors/ecfr.py`：eCFR 三通道（titles / search / full-xml，均已实测 200）→ 固定 3–10 真实样本 →
`FR → codified_in → CFR Title/Part` 链（用 Step 2 已解析的 `cfr_references` 做官方对照）→
`tests/phase4b1/test_ecfr_identity.py` + `test_fr_cfr_link.py` → Step 3 报告。
