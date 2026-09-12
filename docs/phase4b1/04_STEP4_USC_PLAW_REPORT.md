# Phase 4B-1 · Step 4 报告 —— U.S. Code & Public Law 官方接入与法律关系

> 日期：2026-09-12 ｜ 状态：**Step 4 完成**
> 结果：US_FEDERAL **critical 8/9 (88.9%)** ｜ mandatory 11/12 (91.7%)（仅剩 CBP）

---

## 1. 交付物

| 交付物 | 路径 | 状态 |
|---|---|---|
| govinfo 连接器（USC/PLAW） | `app/connectors/govinfo.py` | ✅ 官方通道（无 Key） |
| USC/PL 身份与关系（纯逻辑） | `app/policy/us_code.py` | ✅ key、解析、PL→USC、CFR→USC 桥、条款摘录 |
| 采集 CLI | `scripts/collect_us_code_plaw.py` | ✅ 4 条真实记录（0 失败） |
| 法律关系总审计 | `scripts/audit_legal_links.py` → `outputs/audit/us_legal_links.json` | ✅ 三类关系全量 |
| 测试 | `test_usc_identity.py` + `test_public_law_relation.py` | ✅ 11 条（真实页面夹具） |

**回归**：`pytest tests/phase4b1 tests/policy` → **121 passed**。

---

## 2. 官方通道（实测）

```
USC  目录 : wssearch/rb/uscode                     → 200（年份枚举）
USC  正文 : content/pkg/USCODE-{y}-title{t}/html/USCODE-{y}-title{t}-chap{c}.htm → 200
PLAW 枚举 : wssearch/rb/plaw                       → 200（119/118/117… + docCount）
PLAW 正文 : content/pkg/PLAW-{c}publ{n}/html/PLAW-{c}publ{n}.htm → 200
congress.gov API → 403（需 Key）→ 记 API_KEY_REQUIRED（官方替代 = govinfo）
uscode.house.gov → Python 侧超时（TIMEOUT）→ 官方替代同上
```

**实测格式事实（写入代码注释与测试）**：
- USC 条文清单 = 两栏分析表 `<div class="two-column-analysis-style-content-left">6921.</div>`
- 不存在章节返回**伪 404**（HTTP 200 + `<title>Page Not Found</title>`）→ 必须显式识别为失败
- 大法（IIJA 3.8MB / IRA 1MB）的电池条款在深处 → **必须带相关条款摘录**
- IRA 无 "to amend title N" 措辞，用 **govinfo 官方边缘注记** `NOTE: 26 USC 55` → 段落级 AMENDS 证据

---

## 3. 采集结果（4 条，0 失败）

| evidence_id | 文档 | 规模 | 分类 |
|---|---|---|---|
| `us_usc_42_82` | U.S.C. Title 42 Chap.82（RCRA 固废/危废） | 116 条 | **B** |
| `us_usc_42_103` | U.S.C. Title 42 Chap.103（CERCLA） | 47 条 | C |
| `us_plaw_117_58` | IIJA（135 STAT. 429） | USC×775 ｜ REL×1076 | **B** |
| `us_plaw_117_169` | IRA（136 STAT. 1818） | USC×214 ｜ REL×300 | **B** |

---

## 4. 法律关系总账（全部官方证据）

```
FR  → codified_in    → CFR ：184 链接 ｜ eCFR 核验 34 (18.5%) ｜ 唯一 part 67
CFR → AUTHORIZED_BY  → USC ：33 链接 ｜ 唯一目标 17
      例：49 CFR 171 → 49 U.S.C. 5101（危货运输法）
          40 CFR 260 → 42 U.S.C. 6905（RCRA）
PL  → AMENDS         → USC ：80 链接（IIJA/IRA）
      例：PL:117-58 → USC:23:101 / USC:1:1 …
```
> 说明：PL→USC 当前以 AMENDS 为主（IIJA 大量 highway/water 条款）；CODIFIED_AS 在
> 完整文本扫描下会继续增长（Step 10 全量轮次）。

---

## 5. 矩阵变化

```
US_FEDERAL  mandatory  9/12 (75.0%)  →  11/12 (91.7%)
            critical   6/9  (66.7%)  →  8/9   (88.9%)   （US_CODE、PUBLIC_LAW 升 CONNECTED）
剩余：CBP = ACCESSIBLE（无采集器）→ Step 5
```

---

## 6. 过程中修的两个真实缺陷（已测试锁定）

1. **USC 段号解析为空**：旧正则找 `§`，但 govinfo 用两栏分析表 → 0 段（40:273 曾误报）。
   修正后 42 USC 82 → 116 段。
2. **大法条款被截断**：IRA/IIJA 走 acceptance 时只见头部（税收/储能条款），主题词全丢 → D。
   修正：`relevance_excerpts` + **按主题命中优先排序**，且摘录置于 text 前部（判定窗口内）→ B。
   （同时新增 `clean vehicle`/`tax credit` 等关键词；此为"把真实相关条款交给同一个判定器"，非放宽标准。）

---

## 7. 变更文件

```
新增  app/connectors/govinfo.py
新增  app/policy/us_code.py
新增  scripts/collect_us_code_plaw.py
新增  scripts/audit_legal_links.py
新增  tests/phase4b1/test_usc_identity.py / test_public_law_relation.py
新增  tests/phase4b1/fixtures/govinfo_{usc_42_82_head.html, plaw_117_169_head.html}
修改  sources/jurisdiction-registry.yaml（US_CODE、PUBLIC_LAW → CONNECTED + 官方源）
数据  outputs/uscplaw_20260912_141143.jsonl ｜ outputs/audit/us_legal_links.json
      outputs/cache/govinfo/*.htm
```

## 8. 下一步（Step 5）

CBP（CROSS 裁定）+ BIS（EAR/FR 机构通道）源头接入与 **instrument_type 区分**
（ruling/guidance/notice/order ≠ regulation）。
