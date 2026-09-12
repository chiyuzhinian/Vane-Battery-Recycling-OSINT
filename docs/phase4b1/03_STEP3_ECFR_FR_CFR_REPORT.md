# Phase 4B-1 · Step 3 报告 —— eCFR 连接器 & FR → codified_in → CFR 关系链

> 日期：2026-09-12 ｜ 状态：**Step 3 完成**
> 目标：eCFR 官方结构化接入 + 「FR 文档 → 编纂于 → CFR 条文」官方证据链。

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| eCFR 连接器（3 通道） | `app/connectors/ecfr.py` | ✅ titles / search / full-XML（均官方、无需 Key） |
| CFR 身份与关系（纯逻辑） | `app/policy/cfr.py` | ✅ canonical id、Part 解析、USC/Pub.L/FR 引用抽取、链接构建 |
| Part 采集 CLI | `scripts/collect_ecfr_parts.py` | ✅ 默认目标 + `--from-links`（按 FR 引用动态选 part） |
| FR→CFR 审计 CLI | `scripts/audit_fr_cfr_links.py` | ✅ `outputs/audit/fr_cfr_links.json` |
| 测试 | `tests/phase4b1/test_ecfr_identity.py` + `test_fr_cfr_link.py` | ✅ 11 条（含官方 XML 真实夹具） |
| 数据 | `outputs/ecfr_20260912_140315.jsonl`（20 part） | ✅ 13 B / 7 D |

**回归**：`pytest tests/phase4b1 tests/policy` → **110 passed**（Phase 4A 46 + 4B-1 64）。

---

## 2. eCFR 连接器（实测记录）

```
GET /api/versioner/v1/titles.json                        → 200 {"titles":[...]}
GET /api/search/v1/results?query=battery&per_page=1      → 200 {"results":[...]}
GET /api/versioner/v1/full/{date}/title-{n}.xml?part={p} → 200（需 Accept: xml）
```

**实测发现的硬约束（已修复并写入代码注释）**：
- 请求日期若 **晚于该 title 最新发布日期 → 404**
  （`"requested date 2026-09-12 is past the title's most recent issue date of 2026-09-10"`）
  → 连接器新增 `latest_issue_date(title)`，采集器默认取官方最新可用日期。
- 实测体量：49 CFR 171 = 242KB；40 CFR 273 = 89KB。
- 不存在 part（如 19 CFR 1）→ 404 `{"error":"No matching content found."}` → 记 `ConnectorError`（非 0 结果）。

**解析字段**（`parse_part_document`，lxml）：Part 标题、`<DIV8 N="…">` 段列表（编号+heading）、
`<AUTH>` 权威注记 → **U.S.C. 引用 / Pub. L. 引用 / FR 引用**（→ Step 4 的桥）。

---

## 3. 采集结果（20 个 Part，官方 XML）

```
49 CFR 171/172/173（危货运输：锂电池条款）        → B
40 CFR 260/261（RCRA 危废 通则/鉴别）             → B
40 CFR 1031/1036/1037/1039/1054（车辆排放）       → B
10 CFR / 18 CFR 系列（按 FR 引用动态选入）         → D（背景，如实）
40 CFR 273（通用废物/电池收集框架）                → D ⚠️ 见 §6
```

采集 20 / 失败 0；每条 Part 记录携带：`cfr_key / section_count / authority / usc_citations / public_laws / fr_citations / currentness`。

---

## 4. FR → CFR 关系链（官方证据）

**证据来源**：FR API 官方字段 `cfr_references`（Step 2 已解析）——**不由标题猜测**。

```
FR 文档 135 条 → 链接 184 条 → 唯一 CFR part 67 个
eCFR 侧已核验 part：20 个
命中率：34/184 (18.5%)
实例：
  · 2026-04366（91 FR 10862）→ CFR:40:260 / CFR:40:261
  · 2026-03157（91 FR 7686） → CFR:40:1036 / 1037 / 1039
  · 2025-14572（90 FR 36288）→ CFR:40:1036 / 1037 / 1039
```
未核验的 47 个 part 明确标注「**未采集，非失败**」（清单见 `fr_cfr_links.json.unmatched_parts`），
后续按 `--from-links` 继续补齐即可（命令已就绪）。

---

## 5. 分类器语义修正（Step 3 附带修复，测试锁定）

**缺陷**：`classify_record` 第 0 步把「记录缺 `relevant` 字段」与「旧判定器判不相关」一律当 D。
后果：新采集器（eCFR 等不预置 relevant）全部早退为 D —— 与主题词表无关。

**修正**：仅 `relevant is False`（显式拒绝）才早退；字段缺失 → 交内容分类。
**验证**：49 CFR 172/173、40 CFR 260/261 由 D → **B**（正确）；Phase 4A 46 条测试全部保持通过（110 passed）。

---

## 6. 已知缺口（如实记录，进 Step 8/9）

1. **40 CFR 273（通用废物/电池收集）仍为 D**：主题词表未含 `universal waste` 锚点 → Step 8 连同 instrument 精度一起校准。
2. **排放类 part 被判 B**：B 面存在过宽风险（40 CFR 1031–1054 与电池回收只有间接关系）→ Step 8 用 Gold Set 校准 B 门。
3. **FR→CFR 命中率 18.5%**：受限于已采集 part 数量（非失败）；Step 10 全量轮次时补采。

---

## 7. 变更文件

```
新增  app/connectors/ecfr.py
新增  app/policy/cfr.py
新增  scripts/collect_ecfr_parts.py
新增  scripts/audit_fr_cfr_links.py
新增  tests/phase4b1/test_ecfr_identity.py / test_fr_cfr_link.py
新增  tests/phase4b1/fixtures/ecfr_40cfr273_trimmed.xml（官方 XML 裁剪夹具）
修改  app/policy/acceptance.py            （第 0 步语义修正）
修改  sources/jurisdiction-registry.yaml  （CFR_ECFR：sources+us_ecfr，status CONNECTED）
数据  outputs/ecfr_20260912_140315.jsonl ｜ outputs/audit/fr_cfr_links.json
      outputs/cache/ecfr/*.xml（20 个 part 官方 XML 缓存）
```

## 8. 下一步（Step 4）

U.S. Code + Public Law（govinfo 官方通道）：固定 3–10 真实样本 → `USC:{title}:{section}` /
`PL:{congress}-{num}` 身份 → `AUTHORIZES / AMENDS / CODIFIED_AS / IMPLEMENTED_BY` 关系
（数据源已就绪：`<AUTH>` 权威注记中的 USC 与 `Pub. L.` 引用即官方桥）。
