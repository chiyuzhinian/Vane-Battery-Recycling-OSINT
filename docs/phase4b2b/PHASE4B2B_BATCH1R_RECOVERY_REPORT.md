# Phase 4B-2B — Batch 1R Recovery Report（Network Vantage Recovery & Deep-Onboarding）

> 阶段：4B-2B Batch 1R ｜ 日期：2026-09-14 ｜ 分支：`phase4b2a`
> 冻结遵守：`docs/phase4b2b/00_SCALEOUT_CONTRACT_FREEZE.md`（Policy Core Schema 未改；
> 新增内容全部在 runtime/audit overlay 层）
> 纪律：runner 访问失败 **不得** 等价为 source 缺失；未达 80% Gate 处如实 PARTIAL。

---

## 1. Executive Summary

- **Track A（Network Vantage Recovery）**：建立分层访问观测（DNS→TCP→TLS→HTTP→
  内容）与 Source/Runner 分离分类；复测实证：**7 个原 blocked 中 3 个恢复**
  （AT、US-GA、US-CO），**官方替代路由建立 3 条**（AT=RIS OGD API、HU=Magyar
  Közlöny、US-CO=colorado.gov），**仍 blocked 4 个**（HU/BE/US-MI/US-OH）。
- **Track B（Deep-Onboarding）**：CONNECTED 样本 **12 → 21**（+9）；MODE A
  （DISCOVERY_EXPANSION）对 10 个 CONNECTED 辖区启动并记录（MODE B 未进入）。
- **Batch Gate**：EU onboarding **4/6 = 66.7%**、US **6/8 = 75.0%**——**低于 80%**；
  保持原门槛不降 → **BATCH 1 = PARTIAL / BATCH 2 = NOT READY**。
- **关键结论**：原 Batch 1 的失败中，至少 **DNS_RESOLVE_FAIL（GA）被证伪**（runner
  瞬态）；**HTTP_503_REGIONAL_BLOCK（AT）为出口区域限制**（官方替代路由可达）；
  多辖区呈 **高抖动出口**（同端点跨轮 200/timeout 交替）。此即
  **ENVIRONMENT_ACCESS_GAP**，而非 SOURCE_MISSING。
- **Runner B（独立云环境）**：当前不可用（无云凭据/ssh 模板为空）——已列 P0
  前置；所有连接层失败标记 `awaiting_independent_runner=true`。
- **测试**：388 → **414 passed**（新增 6 文件 26 项）。

## 2. Original Batch 1 Status（对比基线）

EU 6 选：BE/HU/IT/SK/CZ/AT（CONNECTED 3）｜ US 8 选：MI/GA/IL/TN/TX/NV/OH/CO
（CONNECTED 4）｜ 样本 12 ｜ onboarding ≈50% ｜ 判定 PARTIAL（根因：网络出口）。

## 3. Network Vantage Matrix

产物：`outputs/audit/network_vantage_matrix.json / .csv`（20 行 × 15 字段；
runner_id=`runner-local-dev-1`，egress_region=`local-cn`）。两轮复测（round1/2）
关键行：

| 端点 | R1 | R2 | 最终分类 |
|------|----|----|----------|
| AT ris.bka.gv.at | 503 | 503 | **ACCESS_CONTROLLED**（区域拦截） |
| AT data.bka.gv.at（OGD） | — | **200** | **OFFICIAL_ALT_OK** |
| HU njt.hu | reset | no_response | **CURRENT_RUNNER_BLOCKED** |
| HU magyarkozlony.hu | 200 | 200 | **OFFICIAL_ALT_OK** |
| BE ejustice | timeout | timeout | **CURRENT_RUNNER_BLOCKED**（awaiting cloud） |
| US-MI legislature | no_response | no_response | **CURRENT_RUNNER_BLOCKED** |
| US-MI EGLE | 403 | 403 | **ACCESS_CONTROLLED**（域级） |
| US-GA epd | 200 | 200 | **SOURCE_AVAILABLE**（原 DNS_FAIL 证伪） |
| US-OH codes | timeout | timeout | **CURRENT_RUNNER_BLOCKED** |
| US-CO cdphe | 200 | 200 | **SOURCE_AVAILABLE**（原 403 间歇证伪） |
| IT/SK/CZ/IL/TN/TX/NV（对照） | 混合 | 混合 | 源可用；**出口高抖动**实证 |

## 4. 7 Blocked Jurisdictions — before / after

| JID | Before（Batch 1） | After（1R） |
|-----|------------------|-------------|
| AT | BLOCKED（RIS 503） | ✅ **RECOVERED**：官方 OGD API（data.bka 检索 + ogd.bka 文档 200）→ CONNECTED（2 文档样本） |
| HU | BLOCKED（NJT reset） | 🔶 官方替代路由建立（magyarkozlony 200）；文档枚举待 MODE A → 未 CONNECTED |
| BE | BLOCKED（timeout） | ⏳ 仍 blocked（awaiting cloud runner） |
| US-MI | BLOCKED（403/JS） | ⏳ 仍 blocked（legislature 无响应 + EGLE 403 控制壳） |
| US-GA | BLOCKED（DNS fail） | ✅ **RECOVERED**：复测 200（runner 瞬态证伪）→ CONNECTED（EPD 4 样本） |
| US-OH | BLOCKED（拒连/404） | ⏳ 仍 blocked（awaiting cloud runner） |
| US-CO | BLOCKED（403） | ✅ **RECOVERED**：复测 200（主页）→ CONNECTED（1 样本；browser 回退保留） |

## 5. Source vs Runner Failure Classification

- 全新 overlay 模块 `app/policy/network_vantage.py`：7 态枚举
  （SOURCE_AVAILABLE / CURRENT_RUNNER_BLOCKED / SOURCE_PARTIAL /
  ACCESS_CONTROLLED / MULTI_VANTAGE_BLOCKED / SOURCE_FAILURE / UNKNOWN）。
- **纪律测试锁定**：单 vantage 连接层失败 → `CURRENT_RUNNER_BLOCKED` +
  `awaiting_independent_runner=true`；`MULTI_VANTAGE_BLOCKED` 仅在
  **独立出口 ≥2 且全败**时可判（本机同出口场景不适用）。
- 复测翻转实证：GA（DNS_RESOLVE_FAIL→SOURCE_AVAILABLE）、CO（403→200）——
  **runner 失败被证伪的实锤**。

## 6. Execution Routing（Track C）

`ops/source-access-routing.yaml`：runners（local 活跃 / cloud 未配置）+
14 条路由规则 + fallback 链（official_alt / browser_channel）+
`log_fields=[runner_id, egress_region, route_selected, fallback_used]`。
测试 `test_execution_route_selection.py` 锁定结构与规则。

## 7. 7 Connected Jurisdictions Deep-Onboarding

覆盖 10 个 CONNECTED 辖区（含 1R 新增 AT/GA/CO）：
样本刷新与扩展（IT 3、SK 2、CZ 2、AT 2、IL 1、TN 1、TX 2、NV 3、GA 4、CO 1）。

## 8. Real Samples（12 → 21）

新增/刷新 9 条：IT +1（152/2006 环境法典）、CZ +1（185/2001 废物法）、
AT +2（OGD NOR12151966 html/xml——**含"ADR 锂电池运输"条目**）、
GA +4（EPD Land Protection 等）、CO +1（CDPHE 主页）。
全部为官方域 200 直取；样本仅为通道真实性证据——**Corpus 完成度依赖 MODE A**。

## 9. MODE A Results（DISCOVERY_EXPANSION）

`outputs/audit/batch1r_mode_a_log.json`：10 辖区启动记录（roles / endpoints /
本国语关键词 / 枚举方式 / status）。要点：
- **AT（新通道）**：OGD API `Suchworte` 分页枚举——**技术路线已通**
  （JSON 含每文档 XML/HTML/RTF/PDF 直链）；
- IT/SK/CZ：固定 URN/ZZ/sqw 直链枚举（搜索页 SPA 限制记录）；
- GA/CO/IL/TN：站内主题页枚举（CO 子路径 403 → browser 回退）。
**MODE B 未进入**（PLAN_V1 待 MODE A 稳定）。

## 10. Source Role Coverage（Batch 1/1R）

| 辖区 | CONNECTED roles | 备注 |
|------|----------------|------|
| IT/SK/CZ/AT | 1（立法库） | AT 经官方 OGD |
| IL/TN/TX/NV/GA/CO | 1（环境/法典） | GA=EPD、CO=CDPHE |
| HU | 0（route 建立） | gazette 待枚举 |
| BE/OH/MI | 0 | awaiting cloud |

## 11. Identity

不变（既有库 100%）；AT/CZ/GA/CO 契约与 ISSUERS 覆盖复核通过（414 tests）。

## 12. Domain / Acceptance

**无规则改动**（冻结遵守）；无 UNKNOWN_DOMAIN_PATTERN。

## 13. Evidence Completeness

既有库基线不变（A1/A2/B applicable 100%、B clause 100%、FETCH_FAILED 0）；
新样本待入库。

## 14. Topic Coverage

无变化（新样本未入库）。

## 15. Black Mass Coverage

无变化（EU 六线 COVERED）。

## 16. Batch Gate（保持原 §15 门槛，不降）

| 指标 | EU | US | 门槛 | 判定 |
|------|----|----|------|------|
| selected | 6 | 8 | — | — |
| onboarded（CONNECTED） | **4**（IT/SK/CZ/AT） | **6**（IL/TN/TX/NV/GA/CO） | — | — |
| onboarding rate | **66.7%** | **75.0%** | ≥80% | ✗ ✗ |
| 真实样本 | 21（总数） | — | — | 描述统计 |
| source failures reason | 全部有 reason code | | 全有 | ✓ |
| 回归 | 414 passed / 0 fail | | 0 失败 | ✓ |

→ **BATCH 1 = PARTIAL**（不改门槛、不换辖区、不造 PASS）。

## 17. Remaining Blockers

| JID | blocker | reason code | recommended route |
|-----|---------|-------------|-------------------|
| HU | 公报文档枚举未成 | DOC_ENUMERATION_PENDING | magyarkozlony（MODE A 任务） |
| BE | 出口层超时 | CONNECT_TIMEOUT | cloud runner（待配置） |
| US-MI | 无响应 + EGLE 403 | HTTP_NO_RESPONSE / HTTP_403 | cloud runner + browser |
| US-OH | 拒连 + DNS 间歇 | CONNECT_TIMEOUT / DNS_ERROR | cloud runner（待配置） |
| （横贯）| 出口高抖动 | NETWORK_INSTABILITY | retry 策略 + cloud 复核 |

## 18. Batch 2 Recommendation

**NOT READY**（Gate 未达）。顺序建议：
1. **配置 Runner B**（用户提供授权云主机 → `ops/source-access-routing.yaml`
   填入 egress_region；对 BE/OH/MI 及 hovers 复核——**这是解锁 ≥80% 的关键**）；
2. **HU 文档枚举**（magyarkozlony MODE A——单点突破可至 EU 5/6）；
3. 消化 10 个 CONNECTED 的 MODE A → PLAN_V1（进入 MODE B 的前提）；
4. 之后启动 Batch 2 选池。

## 19. Tests

388 → **414 passed**（0 fail）。新增：
`test_network_vantage_classification.py`、`test_runner_failure_not_source_failure.py`、
`test_multi_vantage_probe.py`、`test_execution_route_selection.py`、
`test_source_proof_requires_samples.py`、`test_batch1_onboarding_gate.py`。

## 20. Commits

本阶段提交见仓库 `phase4b2a` 分支（Batch 1R 单一提交，含 overlay 模块/
探测脚本/恢复产物/路由配置/契约刷新/6 测试/本报告）。
