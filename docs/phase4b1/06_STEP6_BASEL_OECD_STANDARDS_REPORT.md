# Phase 4B-1 · Step 6 报告 —— EU 跨境/标准层（Basel / OECD / Standards）

> 日期：2026-09-12 ｜ 状态：**Step 6 完成**
> 结果：EU_SUPRANATIONAL **mandatory 7/9 (77.8%) ｜ critical 6/8 (75.0%)**

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| 跨境/标准身份逻辑 | `app/policy/crossborder.py` | ✅ Basel 阶段判定、OECD 类型、Standards 五概念 |
| 采集 CLI | `scripts/collect_eu_crossborder_sources.py` | ✅ 5 条记录 |
| SPA 失败类型 | `source_access.py`（`SPA_JS_RENDERED`） | ✅ 端点探测与角色判定（测试锁定） |
| 测试 | `test_basel_status.py` / `test_oecd_status.py` / `test_standard_access_status.py` | ✅ 14 条 |

**回归**：`pytest tests/phase4b1 tests/policy` → **144 passed**。

---

## 2. 实测事实（2026-09-12）

| 源 | 结果 | 结论 |
|---|---|---|
| Basel 技术导则页 | 200，服务端渲染（10.7k 文本） | ✅ 可解析 |
| Basel 出版物页 | 200 | ✅ 可解析（从官方 PDF 内引用发现） |
| Basel 官方 PDF | 200（971KB） | ⚠️ 可下载；本阶段无解析器 → `UNSUPPORTED_FORMAT`（metadata only） |
| OECD legalinstruments | 200 但 **4KB JS 壳** | ⚠️ **SPA**（`SPA_JS_RENDERED`）→ 需浏览器通道/官方 API |
| OECD 主站 | 403 | ❌ 记 HTTP_403 |
| CEN 门户 | 200 但 JS 跳转（790B） | ⚠️ SPA |
| ISO 目录 | 403 | ❌ CAPTCHA（≠ 付费墙） |
| EU Harmonised Standards 页 | 200，服务端渲染（31k 文本） | ✅ 可解析（官方引用通道） |
| JRC 出版物库 | 200（15k 文本） | ✅ 可解析 |

---

## 3. 采集结果与分类（5 条）

```
int_basel_basel_tech_guidelines_index  adopted   → official_guidance → B
int_basel_basel_publications           decision  → administrative_rule → B
int_basel_basel_pdf_14_7               unknown   → official_guidance → D（PDF 仅元数据）
int_std_eu_harmonised_standards_ref    metadata  → C（open_access_status=official_metadata_only）
int_std_jrc_repository                 metadata  → D
```
纪律落实（测试锁定）：
- `draft technical guideline` → **官方指引 / 非约束**（不得当 binding）
- COP 决定（Decision BC-x/y）→ binding
- 无全文的标准**不得生成条款证据**（fail-fast）
- EU 官方引用 → `metadata_source_type=EU_OFFICIAL_REFERENCE`，角色 **ceiling=PARTIAL**

---

## 4. 矩阵

```
EU_SUPRANATIONAL  mandatory 6/9 → 7/9 (77.8%) ｜ critical 5/8 → 6/8 (75.0%)
   CONNECTED：EU_OFFICIAL_JOURNAL / EURLEX_PRIMARY / EURLEX_DELEGATED_IMPLEMENTING /
             CUSTOMS_TRADE / ENVIRONMENT_AGENCY / BASEL
   PARTIAL（有据可循，非"未做"）：
     · STANDARDS —— 用户口径 ceiling=PARTIAL（EU 官方引用 ≠ 标准库接入完成）
     · OECD —— 官方端点实测为 SPA（需浏览器通道/官方 API）
US_FEDERAL 保持不变：mandatory 12/12 (100%) ｜ critical 9/9 (100%)
```

> ⚠️ 按§18 目标「EU critical = 100%」：**当前 6/8 为真实结果**。
> 剩余 2 项均有明确的、已实测的阻碍（STANDARDS 为用户设定的口径上限；OECD 为 SPA），
> 将在最终报告中作为 PARTIAL 项如实列出，不虚报为 100%。

---

## 5. 变更文件

```
新增  app/policy/crossborder.py
新增  scripts/collect_eu_crossborder_sources.py
新增  tests/phase4b1/{test_basel_status,test_oecd_status,test_standard_access_status}.py
修改  app/policy/source_access.py        （SPA_JS_RENDERED + 角色判定分支）
修改  app/policy/source_probe.py         （detect_spa 透传）
修改  app/policy/config.py               （probe.detect_spa）
修改  app/policy/source_universe.py      （int_/cbp_cross 采集器识别）
修改  sources/source-endpoints.yaml      （SPA 端点标记 + Basel 出版物端点）
修改  sources/jurisdiction-registry.yaml （BASEL/OECD/STANDARDS 状态与源）
数据  outputs/crossborder_20260912_141831.jsonl ｜ outputs/audit/source_probe_results.json（全量 46 端点）
```

## 6. 下一步（Step 7）

Legal Family 关闭：ELV（32000L0053）与 2006/66（32006L0066）的
`AMENDS / REPEALS / CORRIGENDUM_OF` —— 用 Cellar SPARQL + EUR-Lex 官方关系补齐，
目标 P0 unresolved = 0（或 `absent_official` + 证据）。
