# Phase 4B-1 · Step 5 报告 —— CBP & BIS 贸易源接入

> 日期：2026-09-12 ｜ 状态：**Step 5 完成**
> 里程碑：**US_FEDERAL critical 9/9 (100%) ｜ mandatory 12/12 (100%)** 🎯

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| CROSS 连接器 | `app/connectors/cbp_cross.py` | ✅ 官方 API（`/api/search`，无需 Key） |
| 贸易源身份规则 | `app/policy/us_trade.py` | ✅ 裁定=official_guidance；模糊检索主题过滤 |
| 采集 CLI | `scripts/collect_us_trade_sources.py` | ✅ 22 条记录（0 失败） |
| 测试 | `test_cbp_instrument_type.py` + `test_bis_instrument_type.py` | ✅ 9 条（真实 CROSS 夹具） |

**回归**：`pytest tests/phase4b1 tests/policy` → **130 passed**。

---

## 2. CBP（CROSS 官方 API）

```
✅ GET https://rulings.cbp.gov/api/search?term={q}   → 200 JSON
     {"rulings":[{rulingNumber, subject, categories, rulingDate, tariffs, …}], totalHits}
❌ https://rulings.cbp.gov/search?term=…             → SPA（JS 渲染，无静态结果）
❌ https://www.cbp.gov/trade/rulings                 → 403 Access Denied（记 HTTP_403）
```
- 检索为**模糊匹配**（搜 `battery` 会带回巧克力/甘草糖裁定）→ 已加**主题整词过滤**。
- 裁定类型固定 `official_guidance / non_binding`（测试锁定：不得判 regulation/directive/administrative_rule）。
- 实采：`lithium battery` → 10 条裁定（过滤后）；`black mass`/`battery waste`/`battery recycling` → 过滤后 0 条（无含该短语的裁定，**非失败**）。

## 3. BIS

```
✅ FR 机构通道（agency=industry-and-security-bureau）：black mass 3 / lithium battery 7 / critical minerals export 2
✅ bis.doc.gov EAR 页面（guidance 通道，端点配置内）
type 映射（官方字段优先）：Rule → administrative_rule/binding；Proposed Rule → proposal；Notice 不猜（Step 8）
```

## 4. 采集结果（22 条，0 失败）

```
CROSS 裁定 10 ｜ FR CBP 2 ｜ FR BIS 12（去重后）
分类分布：B=1，D=21
```
⚠️ **如实记录**：CROSS 的 10 条锂电池归类裁定被判 D —— 现有主题词表对
「tariff classification / customs ruling」类文书覆盖不足（T13 词表缺 customs/ruling 锚点）。
这是**已定位的 Step 8 修正项**，本步不擅自放宽规则。

## 5. 矩阵（US 联邦闭环达成）

```
US_FEDERAL  mandatory 11/12 → 12/12 (100.0%)
            critical   8/9  → 9/9  (100.0%)
EU_SUPRANATIONAL 不变：mandatory 6/9 ｜ critical 5/8（Step 6 处理 Basel/OECD/Standards）
```

## 6. 变更文件

```
新增  app/connectors/cbp_cross.py ｜ app/policy/us_trade.py
新增  scripts/collect_us_trade_sources.py
新增  tests/phase4b1/test_cbp_instrument_type.py / test_bis_instrument_type.py
新增  tests/phase4b1/fixtures/cross_search_battery.json
修改  sources/jurisdiction-registry.yaml（CBP → CONNECTED + cbp_cross；BIS 备注）
数据  outputs/trade_20260912_141508.jsonl
```

## 7. 下一步（Step 6）

EU 跨境/标准层：Basel（技术导则，draft≠binding）+ OECD（legalinstruments）
+ Standards（官方 metadata：`open_access_status` / `metadata_source_type`，角色 ceiling=PARTIAL）。
