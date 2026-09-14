# Phase 4B-2B — Batch 1 Scale-Out Report（EU27 + US50/DC 首批量）

> 阶段：4B-2B Batch 1 ｜ 日期：2026-09-14 ｜ 分支：`phase4b2a`
> 契约冻结：`docs/phase4b2b/00_SCALEOUT_CONTRACT_FREEZE.md`
> 纪律：本 Batch 以 **Production Onboarding** 为目标；核心框架未重设计；
> 未触发 STOP-THE-LINE（无 P0 schema bug / 证据污染 / 身份碰撞）；
> 未达目标处一律如实标注，**未伪造 PASS**。

---

## 1. Executive Summary

- **Batch 1 选择**：EU 6 国（BE/HU/IT/SK/CZ/AT）＋ US 8 州（MI/GA/IL/TN/TX/NV/OH/CO），
  由 `jurisdiction_priority_score`（8 维加权）重算 + 难度分层（easy/medium/hard 全覆盖）
  自动产生（`outputs/audit/batch1_jurisdiction_selection.{json,csv}`）。
- **Source Proof**：14/14 完成真实探测（含 0 样本者如实记录）；
  **CONNECTED（≥1 真实样本）= 7 国/州**；12 个真实官方样本落盘（proof 层）。
- **onboarding 率**：EU **3/6 = 50%**、US **4/8 = 50%** —— **低于 §15 的 80% 目标**。
- **根因（如实）**：本网络出口对多个官方域的整体不可达（区域拦截/连接重置/DNS/
  403），验证于 curl 直连同败（RIS 503、NJT reset、ejustice 超时、epd.georgia DNS、
  cdphe 403、codes.ohio.gov 拒连）。**非框架缺陷**。
- **判定：BATCH 1 = PARTIAL**（框架修正项全部完成且全绿；覆盖目标受外部限制未达）。

## 2. Selected Jurisdictions

| 组 | 选择 | 排除 |
|----|------|------|
| EU | BE, HU, IT, SK, CZ, AT | 已 CONNECTED 专线：SE/FI/DE/NL/ES/FR/PL |
| US | MI, GA, IL, TN, TX, NV, OH, CO | 已 eligible：CA/WA |

依据：priority 分数重算 + 「禁止只选最容易」→ difficulty 档
easy(=AT/CO)/medium(=IT、TN、NV、OH)/hard(=HU、MI、TX) 全覆盖；
US 约束 ≥2 个 policy_signal≥4（MI/IL/CO ✓）。

## 3. Source Universe

- 新增 `sources/jurisdiction-sources/{JID}.yaml` 11 份（BE/GA/CO 沿 4B-2A 既有）。
- 每份含：official_owner / official_domain / access_method / entry_url /
  search_attempts / samples_known / known_limitations。

## 4. Source Role Coverage

| JID | 角色（CONNECTED/共探测） | 状态 |
|-----|--------------------------|------|
| IT | normattiva（2 样本） | CONNECTED |
| SK | slov-lex（2 样本） | CONNECTED |
| CZ | PSP sbirka（1 样本） | CONNECTED |
| BE | ejustice | BLOCKED（连接超时） |
| HU | njt / magyarkozlony | BLOCKED（reset；MK 域可达无文档） |
| AT | RIS | BLOCKED（503 区域拦截） |
| IL | IL-EPA（1 样本） | CONNECTED |
| TN | TDEC（1 样本） | CONNECTED |
| TX | statutes（2 样本） | CONNECTED |
| NV | NDEP（3 样本） | CONNECTED |
| MI | legislature / EGLE | BLOCKED（JS 渲染 / 403） |
| GA | epd.georgia.gov | BLOCKED（DNS 不可解析） |
| OH | codes.ohio.gov / EPA | BLOCKED（拒连；EPA 入口可达） |
| CO | cdphe | BLOCKED（403） |

## 5. New Connectors

**0**。本 Batch 产出达到 proof 层（真实样本）；connector 化列入 P1
（对 7 个 CONNECTED 辖区）。禁止「跳过 Source Proof 直接写 crawler」——已执行。

## 6. Real Policy Corpus

12 个真实样本（IT 2 / SK 2 / CZ 1 / TX 2 / NV 3 / IL 1 / TN 1），
均为官方域直取（200）；**条数仅为描述统计，非 KPI**。

## 7. Domain / Acceptance

**无规则改动**（冻结遵守）。新样本未进入分类管道（入库后走既有 classifier）；
无 UNKNOWN_DOMAIN_PATTERN 产生。

## 8. Evidence Completeness

- 既有库基线不变（2B1R：A1/A2/B applicable 100%、B clause 100%、FETCH_FAILED 0）。
- 本 Batch 的 7 个可采辖区尚未入库（connector P1 后并入）。

## 9. Identity

- `ISSUERS` 已覆盖全部 11 个新契约（`identity_jurisdiction.py` 增补；
  测试 `test_issuers_cover_all_contracts` 恢复绿色）。
- 新辖区 identity pattern 写入各自 Contract `identity_strategy`（待入库启用）。

## 10. Topic Coverage

无变化（T01–T14 口径沿用；新样本未入库）。

## 11. Black Mass

无变化（EU 六线 COVERED 保持）。

## 12. MODE A Results

**未执行** —— SOP 顺序（Source Proof 为硬门）已完成；**7 个 CONNECTED 辖区的
DISCOVERY_EXPANSION 轮列为 Batch 2 首要动作**。

## 13. MODE B Results

**未进入**（无冻结 plan）。

## 14. Jurisdiction Status（Batch 1 汇总）

- **onboarded（CONNECTED）**：IT/SK/CZ ｜ IL/TN/TX/NV —— 7 个
- **proof-done, not connected**：BE/HU/AT ｜ MI/GA/OH/CO —— 7 个（如实 blocked/gap）
- `outputs/audit/batch1_metrics.json` 保存逐辖区明细。

## 15. Batch Metrics

| 指标 | 值 | §15 目标 | 判定 |
|------|----|---------|------|
| EU onboarding（CONNECTED） | 3/6 = 50% | ≥80% | ✗ |
| US onboarding（CONNECTED） | 4/8 = 50% | ≥80% | ✗ |
| Source Proof 管线完成 | 14/14 = 100% | — | ✓ |
| Critical Source Coverage | 7/14 辖区有 ≥1 critical role | ≥90% | ✗（外部限制） |
| 高价值全文 applicable | 100%（既有库 A1/A2/B） | ≥95% | ✓ |
| B clause | 100% | ≥95% | ✓ |
| Domain contradiction | 0 | =0 | ✓ |
| Identity completeness | 100%（既有库） | ≥90% | ✓ |
| Source failure reason code | 全部（proof limitations + 本节 §16） | 全有 | ✓ |
| No raw evidence corruption | 无事件 | — | ✓ |
| Regression | 388 passed, 0 failed | 无回归 | ✓ |

## 16. Blocked Sources（全部带 reason code）

| source | reason code | 证据 |
|--------|-------------|------|
| AT ris.bka.gv.at | `HTTP_503_REGIONAL_BLOCK` | httpx+curl 同 503（30KB 错误页） |
| HU njt.hu | `CONNECTION_RESET_PERSISTENT` | RemoteProtocolError / curl 56 reset |
| BE ejustice.just.fgov.be | `CONNECT_TIMEOUT` | curl 21s 超时 |
| MI legislature.mi.gov | `JS_RENDERED_NO_STATIC_DOCS` | 200 但无可解析文书链 |
| MI michigan.gov | `HTTP_403_DOMAIN_WIDE` | EGLE 及根域 403 |
| GA epd.georgia.gov | `DNS_RESOLVE_FAIL` | curl host 解析失败 |
| OH codes.ohio.gov | `CONNECTION_REFUSED_TIMEOUT` | 多次 ConnectTimeout/拒连 |
| CO cdphe.colorado.gov | `HTTP_403` | 拦截壳 |

## 17. P0 / P1 / P2

- **P0 = 0**（无框架缺陷；未触发 STOP-THE-LINE）。
- **P1**：① 网络出口修复（或代理/镜像通道）以解 7 个 blocked；② 对 7 个
  CONNECTED 辖区落 connector 并入 evidence 管道；③ MODE A 轮（search plan 冻结）。
- **P2**：A1 案例积累、批次 2 选池扩展、registry 逐行状态刷新。

## 18. Framework Changes（相对冻结版本）

1. **Scale-Out Gate 聚合修正**（§2 规格）：新增 `aggregate_eligible()`，
   `audit_scaleout_gate.py` 改 every-eligible 逐一评估，输出
   `eligible_total/pass/fail`；**禁止 `eligible[0]` 样本代表**；
   新测试 `tests/phase4b2b/test_scaleout_gate_all_eligible.py`（5 项）。
2. **Fulltext 双口径**（§3 规格）：`fulltext_rate_strict` /
   `fulltext_rate_applicable` / `no_independent_manifestation_count`；
   记录级 `content_exempt_reason=NO_INDEPENDENT_OFFICIAL_MANIFESTATION`
   （224 条历史记录补字段）。
3. **Source Proof 执行器加固**：curl.exe 回退（TLS 兼容/瞬态），不改 Schema。
4. **契约新增连带**：`ISSUERS` 覆盖 Batch 1 11 辖区；`jurisdiction_map` 测试
   更新（MI 契约生效后 `us_mi_*` 正确归属 US-MI —— 行为增强，非回归）。

## 19. Regression

```
py -m pytest tests -q → 388 passed（2026-09-14；383 基线 + 5 新测试）
```

## 20. Batch 2 Recommendation

**BATCH 2: NOT READY（当前网络环境）**。两个前置：
1. **网络出口/通道修复**（代理/VPN/镜像）——否则 medium/hard 区将持续大面积
   `HTTP_403/DNS/RESET` 类失败（本 Batch 实证 7 例）。
2. **先消化 Batch 1 成果**：7 个 CONNECTED 辖区 → connector + 入库 + MODE A
   （same-hash streak 起步），再扩 Batch 2 池。
模式建议：Batch 2 仍保 easy/medium/hard 分层与 ≥2 政策信号约束，但**优先
可达性中位数以上**，hard 区限量（≤1/4）以维持推进率。
