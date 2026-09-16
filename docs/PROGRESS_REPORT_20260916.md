# 退役电池回收 OSINT 系统 —— 进度总报告（截至 2026-09-16）

> 分支 `phase4b2a` @ `3fc8f0a`（已推送）｜ 测试 **418 passed** ｜
> **BATCH 1 双门槛通过**（EU 83.3% + US 87.5%）

---

## 一、当前状态快照

### 1.1 核心指标

| 指标 | 当前值 | 门槛/目标 | 状态 |
|---|---|---|---|
| BATCH 1 · EU 组 onboarded | **5/6 = 83.3%** | ≥ 80% | ✅ |
| BATCH 1 · US 组 onboarded | **7/8 = 87.5%** | ≥ 80% | ✅ |
| 搜索计划（PLAN）注册 | 14 张（V1/V2） | 每辖区 ≥1 | ✅ |
| 收敛验证 | **11/11 全收敛**（streak=2） | 连续 ≥2 轮零新增 FULL | ✅ |
| 真实官方样本 | **25 份**（EU 11 + US 14） | 每源 ≥1 | ✅ |
| 测试套件 | **418 passed** | 0 fail | ✅ |
| 端点注册 | 33 角色 / 69 端点 | — | ✅ |
| 发现轮记录 | 57 轮（discovery_rounds） | — | ✅ |

### 1.2 辖区看板（Batch 1 全量 + pilot）

| 辖区 | 通道 | 样本 | PLAN_V1 | 收敛 | 备注 |
|---|---|---|---|---|---|
| **AT** | RIS OGD（API+文档） | 2 | ✅ 已冻结 | ⏳ 待起跑 | MODE A 实采 80/57、8 文档入库 |
| **HU** | Magyar Közlöny（?content= + letoltes PDF） | 2 | ✅ | ✅ streak=2 | 云+本地双 vantage |
| **CZ** | PSP sbirka（年枚举+全文） | 2 | ✅ | ✅ streak=2 | 电池专条 170/2010 |
| **SK** | Slov-Lex 静态门户（HTML+PDF） | 2 | ✅ | ✅ streak=2 | 81/2015、373/2015（batéri×90） |
| **IT** | Normattiva（veloce+N2Ls） | 3 | ✅ | ✅ streak=2 | 188/2008 电池专法 |
| **BE** | ejustice.just.fgov.be | 0 | — | — | ⛔ 双 vantage 封锁（需目标区 vantage） |
| **US-MI** | **browser 通道**（EGLE） | 2 | — | — | ✅ 1R-2 恢复（sha256 存证） |
| **US-OH** | codes/epa/legislature.ohio.gov | 0 | — | — | ⛔ 三通道终判 BLOCKED（全州 WAF） |
| **US-GA** | EPD | 4 | — | — | ✅ |
| **US-IL / TN / TX / NV / CO** | 州环保署/法库 | 1/1/2/3/1 | — | — | ✅ |
| （pilot）SE / FI / US-CA / US-WA | 各自通道 | — | ✅（V1/V2） | ✅ 4/4 | 4B-2A 批次 |

### 1.3 环境与运维快照

- **磁盘**：C: 可用 **89.9GB**（起点 ~0.1GB；Docker vhdx 180.4→88.3GB，已压缩）
- **Docker**：5 容器运行中（vane / lithium-intel / wewe-rss×2 / github-mcp-server）
- **云 Runner B**：runner-cloud-1（阿里云 106.12.59.96，egress=aliyun-cn）active
- **服务**：前端 3100（node）+ 后端 8010（py）运行中

---

## 二、系统架构现状（模块）

| 层 | 位置 | 内容 |
|---|---|---|
| 策略引擎 | `app/policy/` | search_plan（版本化+sha256 哈希）、acceptance（A/B/C/D 分类 + 主题词表）、network_vantage（7 态访问分类）、saturation_gates、rounds（收敛机制）、source_universe |
| 配置面 | `sources/` | `source-endpoints.yaml`（33 角色/69 端点）、`jurisdiction-registry.yaml`、`search-plans/`（14 张）、`jurisdiction-sources|onboarding/`（契约 22+ 份）、`regulatory-topics.yaml`（多语种主题词根：de/en/cs/sk/hu/it/fi/pl/ee…） |
| 执行面 | `scripts/` | `run_jurisdiction_round.py`（8 辖区适配器：SE/FI/US-CA/US-WA/CZ/IT/HU/SK）、`probe_network_vantage.py`、`ingest_cloud_samples.py`、`ingest_browser_samples.py`、`batch1_metrics.py`、`batch1r_recovery_decisions.py`、`onboard_jurisdiction_sources.py`、审计工具族 |
| 路由 | `ops/source-access-routing.yaml` | runner-local-dev-1 + runner-cloud-1；per-jurisdiction 规则（含 browser_channel fallback） |
| 测试 | `tests/` | 418 tests（phase4b1/2a/2b/2b0 + 配置/计划/路由/收敛） |

---

## 三、历史进度汇总（阶段链）

### Phase 4A —— 源宇宙建模
- 管辖区 × 源角色模型（EU/27 成员国/美国联邦+50 州）；"URL 存在 ≠ coverage"纪律；
  状态机 NOT_ONBOARDED → … → COMPLETE ｜ BLOCKED。

### Phase 4B-1 —— 端点注册表与源角色体系（Steps 0-10）
- `source-endpoints.yaml` 注册表 + 角色状态推导（endpoint ≠ role）；
- LIVE 轮次 ×6、scope 饱和 ×4、黑粉六线矩阵；instrument_type 精度 → 1.0；
  Legal Family 官方关系闭环（P0 unresolved=0）；A1 Gold Set 首枚。

### Phase 4B-2A —— Jurisdiction Onboarding Framework（Steps 0-10）
- 收敛协议修正：**Search Plan Versioning + plan_hash**（语义 11 字段，变更即 reset）；
- Pilot 锁定（评分制）：**SE / FI / US-CA / US-WA**；Source Proof + 契约生成；
- jurisdiction 级 MODE A/B 轮（发现 + 收敛验证）：**4/4 全收敛**；
- EU 三连接器（SFST/ISAP/Finlex）+ US 州连接器（leginfo/RCW）+ 多语种词表（FI/PL/EE）。

### Phase 4B-2B0 —— 规模化就绪（Steps 0-10）
- 三层收敛状态 + eligibility gates；身份硬化（construct/decompose/measure）；
- Domain Relevance Guard（5 级 scope）；blocked channel 攻坚（PL/KY/MN 3/7）；
- 黑粉缺口澄清 + 路线多样性矩阵；pilot 收官报告 + scale-out gate verdict。

### Phase 4B-2B1 —— Scale-Out Readiness（Steps 0-8）
- 证据完备性 gate（§4/§5）+ 内容回填；SE/US-CA/US-WA 三辖区收敛资格达成；
- 通道适配 3→5/7；黑粉州/联邦边界说明（transboundary/customs→NOT_APPLICABLE_STATE_LEVEL）；
- **Scale-Out READY 终报告（18 节）**；EUR-Lex 软封恢复（CELLAR 官方 REST 通道）。

### Phase 4B-2B Batch 1 —— EU6 + US8 生产接入
- 14 辖区并批量 onboarding（首轮 PARTIAL：EU 5/6、US 6/8=75%）。

### Batch 1R —— Network Vantage Recovery
- **云 Runner B 上线**（阿里云）+ 双 vantage 矩阵（7 blocked 判定）；
- 恢复 4/7：**AT**（OGD 通道全链路：枚举 80/57 → 8 文档 → AT_PLAN_V1 冻结）、
  **HU**（Közlöny 通道）、GA、CO；BE/OH/MI 双 vantage 保持 blocked；
- 纪律固化：单 vantage 连接失败 → CURRENT_RUNNER_BLOCKED，不上升为源失败。

### MODE B 批次 1 —— CZ/IT/HU/SK 通道化与收敛
- 侦查 Round 1-9（全部实采）：攻克 JS 壳站——
  CZ PSP 年枚举/全文、IT veloce+N2Ls、HU `?content=` 真参数+PDF 实体、SK 静态门户镜像；
- **4×PLAN_V1 冻结**（端点 +12、注册表 +3 角色）→ 收敛轮：
  CZ 6 轮、IT 6 轮、HU 4 轮、SK 5 轮 → **四辖区 streak=2 全收敛**；
- 关键修复：cs/sk/hu/it 词表、CZ 标题模式、IT 门户噪音/FAQ 误伤、SK 301 重定向+PDF 优先。

### Batch 1R-2 —— 第三通道（真实浏览器栈）
- **US-MI 恢复**：desktop-browser-mcp 破 bot 壳（EGLE 2 样本 200，sha256 存证）
  → **US 7/8 = 87.5% 达标**（BATCH 1 双门槛通过）；
- **US-OH 三通道终判 BLOCKED**：本地/云/浏览器一致被拒（ohio.gov 全州品牌 404
  = WAF 策略遮蔽；截屏存证）——恢复路径=美区 vantage。

### 运维插曲 —— 磁盘抢救
- C: 0.1GB → **89.9GB**：波 1-2（备份/Temp/npm/pnpm/yarn/回收站）；
  波 3 Docker vhdx fstrim 87.9GiB + diskpart 压缩（180.4→88.3GB）。

---

## 四、关键资产清单

### 4.1 搜索计划（14 张）
AT_PLAN_V1 ｜ CZ_PLAN_V1 ｜ HU_PLAN_V1 ｜ IT_PLAN_V1 ｜ SK_PLAN_V1 ｜
SE_PLAN_V1/V2 ｜ FI_PLAN_V1 ｜ US_CA_PLAN_V1/V2 ｜ US_WA_PLAN_V1/V2 ｜
EU_SUPRA_PLAN_V1 ｜ US_FED_PLAN_V1

（收敛索引覆盖 11 张，**11/11 全收敛**；AT/EU/US-FED 走各自通道或待起跑）

### 4.2 存证（outputs/ 下，不入库，报告引用哈希）
- `audit/source_proofs/`：23 个辖区 proof（25 份 200 样本）
- `audit/cloud_samples/`：Runner B 云端样本（HU×2）
- `audit/browser_samples/`：真实浏览器样本（US-MI×2 + US-OH 404 截屏）
- `discovery_rounds/`：57 轮轮记录（含四辖区收敛链）

### 4.3 主要报告
- `docs/phase4b2b/PHASE4B2B_BATCH1R_RECOVERY_REPORT.md`（20 节 + 附录 A/B）
- `docs/phase4b2b/PHASE4B2B_MODEB_BATCH1_CHANNELS.md`（含收敛轮 + 1R-2 章节）
- `outputs/audit/batch1_metrics.json` / `batch1_channel_recovery.json`

---

## 五、存量问题与风险

| # | 问题 | 级别 | 处置建议 |
|---|---|---|---|
| 1 | **BE / US-OH 封锁**（本地+云+浏览器三通道一致被拒） | P2 | 目标地区 vantage（美区/欧区 runner）；否则长期 BLOCKED 记录 |
| 2 | **AT_PLAN_V1 未起跑收敛轮** | P2 | 与其他四辖区同法起跑（适配器需补 AT；可复用 OGD 通道） |
| 3 | MODE B 语料累积未规模化（执行轮=采样扩张） | P3 | 四辖区 PLAN 已冻结，可直接排轮 |
| 4 | SK 无电池专法（泛废物层）；CZ 部分种子泛述 D | P3 | 记录在案（判据一致性优先，不放水） |
| 5 | 环境：云 Runner B 单点；磁盘压缩后需监控 | P3 | 定期 `docker system df`；必要时再 fstrim |

---

## 六、下一步建议（优先级排序）

1. **MODE B 执行排轮**：CZ/IT/HU/SK 四辖区按已冻结 PLAN 采集成语料（目标各 8-20 文档）
2. **AT 起跑**：适配器 + 收敛轮（通道已验证，工作量小）
3. **BATCH 2 准备**：双门槛已过，前置条件大幅改善
4. **OH/BE 长期方案**：美区/欧区 vantage 可用时一键恢复（通道脚本已备）

---

## 附录 A：提交链（近 30，`git log --oneline`）

```
3fc8f0a  batch1r-2: browser 通道恢复 US-MI → US 7/8=87.5% 达标；OH 三通道终判
cdbeb13  modeb batch1: 四辖区收敛轮完成（streak=2 全收敛）+ 适配器/词表/修复
81b2982  modeb batch1: CZ/IT/HU/SK 通道化（Round 1-9）+ 4×PLAN_V1 冻结
4f252c6  batch1r: MODE A 深化（AT 全链 + AT_PLAN_V1 冻结）
fe6e722  batch1r: Runner B 上线 + HU 恢复 → EU 5/6
4904979  batch1r: Network Vantage Recovery + Deep-Onboarding
54251b8  batch1: 生产接入首批量（EU6+US8）+ 框架两修正
30cbedf  2b1r: EUR-Lex 依赖恢复（CELLAR 官方通道）与 Scale-Out READY
b652e3e  2B1 Step 8: final scale-out readiness report
51c55c5  2B0 Step 10: pilot closure + scale-out gate verdict
6346f44  4B-2A Step 10: final onboarding report + contract backfill
0de8740  4B-2A Step 9: MODE B convergence 4/4
dcd3fbd  4B-2A Step 8: jurisdiction-level MODE A rounds
84e32b6  4B-2A Step 1: Search Plan Versioning（收敛协议修正）
278db2b  4B-1 Step 10: LIVE 轮次 ×6 + 最终报告
```

## 附录 B：关键文件索引

```
app/policy/search_plan.py          计划版本化 + 哈希 + 注册表校验
app/policy/acceptance.py           A/B/C/D 分类（多语种主题词根）
app/policy/network_vantage.py      7 态访问分类（MULTI_VANTAGE 纪律）
sources/search-plans/*.yaml        14 张冻结计划
sources/source-endpoints.yaml      33 角色 / 69 端点
scripts/run_jurisdiction_round.py  轮执行器（8 辖区适配器）
scripts/ingest_browser_samples.py  浏览器通道样本注入（1R-2 新范式）
ops/source-access-routing.yaml     runner 路由（含 browser fallback）
```

---
*报告生成：2026-09-16 ｜ 数据源：git / batch1_metrics.json / discovery_rounds.json / source_proofs*
