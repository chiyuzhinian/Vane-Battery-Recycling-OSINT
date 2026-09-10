# Vane-Battery-Recycling-OSINT

> 基于 [Vane](https://github.com/ItzCrazyKns/Vane) 的动力电池回收 OSINT 二次开发方案
> 企业情报采集 + 国内外政策监测 + Claude 深度分析

研究者：chiyuzhinian
最后更新：2026-09-10

---

## 一、这个项目解决什么问题

退役（车用）动力电池回收领域的情报研究，目前最大的三个痛点是：

| 痛点 | 本项目的解法 |
|---|---|
| 信息源分散在年报、环评、公告、招投标、专利、新闻、行业数据库 7 类渠道 | **多源搜证引擎**：定向源直采 + Vane 通用搜索 + 人工投喂 三通道归一化 |
| 同一事实多个说法，不知道信哪个 | **五层交叉验证**：来源权威性 → 多源确认 → AI 逻辑检查 → 时效 → 溯源，输出 0-100 质量分 |
| 政策更新靠人肉盯，容易漏 | **政策周更监测**：中国 + 欧盟 + 美国，变更事件自动识别与推送 |

分工设计：**Vane 负责"需求拆解 + 数据源搜证"，Claude 负责"深度分析"**。

---

## 二、文档索引（按顺序阅读）

| # | 文档 | 内容 | 状态 |
|---|---|---|---|
| 00 | 项目总体规划 | 需求分析、三阶段路线图、系统架构全景 | ⏳ 待写 |
| 01 | 快速开始指南 | Vane 部署、环境配置、首次验证 | ⏳ 待写 |
| 02 | 电池回收 OSINT 使用指南 | 5 维度采集工作流、政策监测方法 | ⏳ 待写 |
| 03 | [数据源管理和验证体系](03_数据源管理和验证体系.md) | 信息源金字塔、验证决策树、质量分级、审核工作流 | ✅ |
| 04 | [二次开发方案-后端](04_二次开发方案-后端.md) | 需求拆解、多源搜证、交叉验证、源自学习、调度、API | ✅ |
| 05 | [二次开发方案-前端](05_二次开发方案-前端.md) | UI/UX 设计、Dashboard、数据展示组件 | ✅ |
| 06 | 数据库设计和管理 | 云端存储、Schema、迁移与备份 | ⏳ 待写 |
| 07 | [Python 采集脚本详解](07_Python采集脚本详解.md) | 可运行的采集脚本、模块详解 | ✅ |
| 08 | Claude 集成和深度分析 | Prompt 模板库、报告生成 | ⏳ 待写 |
| 09 | 部署和维护 | 云端部署、监控告警、维护指南 | ⏳ 待写 |
| 10 | 案例演示 | 格林美采集、政策跟踪、报告生成完整案例 | ⏳ 待写 |

> 📐 **系统架构、Vane/SearxNG 各自作用、搜索边界定义** 见 [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 三、数据源配置（`sources/`）

```
sources/
├── battery-recycling-sources.yaml   # 总入口：加载顺序、维度↔源映射、全局规则
├── policy-cn.yaml                   # 中国政策源（⏳ 待回填 URL）
├── policy-eu.yaml                   # 欧盟政策源（✅ 本次新增）
├── policy-us.yaml                   # 美国政策源（✅ 本次新增）
├── companies.yaml                   # 目标企业注册表（26 家）
└── info-sources.yaml                # 行业信息源（咨询机构 13 + 协会 17）
```

### 政策源

| 区域 | 权威入口 | 状态 |
|---|---|---|
| 中国 | 待回填 | ⏳ 你已持有，回填 URL 即可启用 |
| 欧盟 | EUR-Lex 法规 (EU) 2023/1542、DG ENV 电池专题页、官方公报 L 系列 | ✅ 已核实入口 |
| 美国 | Federal Register API（**无需 API Key，已实测可用**）、EPA、DOE/MESC、IRS 45X | ✅ 已核实 API |
| 成员国/州 | 德国 UBA、法国 ADEME、加州 CalRecycle | ⏳ 域名待确认 |

### 目标企业（26 家）

- **已深度配置**：格林美（002340.SZ）、邦普循环（宁德时代 300750.SZ 子公司）
- **上市公司系**：光华科技、天奇股份、中伟新材料、骆驼资源循环、赣锋循环、杰瑞再生循环、欣旺达再生、浙江天能新材料、厦门厦钨循环、赣州豪鹏
- **非上市专精**：金晟新能源、博萃循环、中资环电池、杰成新能源、福建常青、巴特瑞、恒创睿能、南通北新、安徽巡鹰、江苏青衫、鑫茂、瑞科美

> ⚠️ 18 家标记为 `verify_status: pending`（主体全称/上市状态待核实），清单见 `sources/companies.yaml` 末尾。
> 未核实的企业**不写入不确定的股票代码**，避免串数据。

### 行业信息源（30 条）

咨询机构：高工锂电、电池中国、电池网、起点锂电、鑫椤锂电、SMM 新能源、上海有色网、OFweek 锂电网、新产业智库、EVTank、真锂研究、富宝、电池之家

协会组织：CABIA、中国化学与物理电源行业协会电池应用分会、中国电池工业协会、中国循环经济协会、中国物资再生协会（含资源强制回收产业联盟/废旧电池回收利用分会/报废汽车专委会）、北京资源强制回收产业联盟、废电池回收利用专业委员会、麦克阿瑟基金会、中国工业节能与清洁生产协会新能源电池回收专业委员会、中国汽车工业协会、中国电子节能技术协会、中国再生资源回收利用协会、中国有色金属工业协会、电池百人会

> 域名未核实的一律留空，走"新源发现"流程：检索 → 人工确认官网 → 回填域名 → 转 verified。
> **不写死未核实的 URL，避免采到仿冒站。**

---

## 四、核心质量规则（不可绕过）

```
✓ 无来源 URL           → 永不 verified
✓ 存在数据冲突          → 永不 verified（必须人工裁决）
✓ 单一来源且非官方源     → 永不 verified
─────────────────────────────────────────
质量分 ≥ 80 → 直接入库
质量分 60-79 → 待人工审核
质量分 < 60  → 强制人工审核
```

---

## 五、三阶段路线

| 阶段 | 周期 | 目标 |
|---|---|---|
| 一 | 1-2 周 | 核心采集（格林美/邦普 5 维度）+ 政策周更 + 最小 Dashboard |
| 二 | 1 个月 | Claude 深度分析 + 实体消解 + 看板升级 + 数据源自学习 |
| 三 | 后续 | 全球政策覆盖（EU/US 扩面）+ 中英双语 |

---

## 六、数据源可达性实测（能不能搜到？）

```bash
py scripts/verify_sources.py              # 全量可达性（本机 Python 命令为 py，3.12.10）
py scripts/verify_sources.py --region CN  # 只看中国
py scripts/verify_sources.py --collect US # 真实采集
```

**42 个源：✅ 可达 32 / 🚫 反爬 8 / ❌ 失效 2**

| 区域 | 结果 |
|---|---|
| 🇨🇳 CN | **16/16 全部可达**（最大单点: std.samr.gov.cn，占你历史命中量的 52.9%） |
| 🇪🇺 EU | 8 可达 / 4 反爬（EUR-Lex 改走 SPARQL 已打通）/ 1 失效 |
| 🇺🇸 US | 8 可达 / 4 反爬（均有 site: 降级）/ 1 失效 |

**真实采集已跑通**（政策侧 + 企业侧）：

```
政策侧
  美国 Federal Register：138 条原始 → 57 条相关（41%）
  欧盟 EUR-Lex SPARQL ：电池法规 32023R1542 + 14 个更正版本
企业侧
  巨潮资讯 cninfo      ：84 条 → 23 条相关，全部命中目标企业
                         （格林美/天奇/光华科技的动力电池回收项目公告）
  环评公示 eia         ：10 个站点可采（企业级项目公示需打通省级专栏）
```

完整报告：[`docs/verification-report-2026-09-10.md`](docs/verification-report-2026-09-10.md)

> ⚠️ **两个必须知道的坑**（已修复）：
> ① Python 的 TLS 栈连不上 `gxt.hunan.gov.cn` 和 `ec.europa.eu`，但 curl 完全正常——
> 不做交叉验证会把可用源误判为失效。已在 `app/connectors/base.py` 内置 curl 回退。
> ② 相关性规则必须用真实数据校准：首版误杀了 45X 最终规则等 3 条核心政策，
> 修正后美国采集合规数从 16 条提升到 **57 条**。

---

## 七、项目结构

```
├── ARCHITECTURE.md                  # 系统架构 + Vane/SearxNG 作用 + 搜索边界
├── 0X_*.md                          # 11 篇方案文档（见上表）
├── README.md
├── requirements.txt                 # Python 依赖（部署到 Linux 后使用）
├── app/
│   ├── connectors/                  # 定向源直采（通道 B）
│   │   ├── base.py                  #   基类 + 限速 + curl 回退 + POST 支持 + ProbeResult
│   │   ├── cninfo.py                #   企业侧：巨潮资讯公告/年报（✅ 已验证）
│   │   ├── eia.py                   #   企业侧：环评公示（✅ 多站点，结构无关抽取）
│   │   ├── eur_lex.py               #   政策侧：欧盟 Publications Office SPARQL
│   │   └── us_federal.py            #   政策侧：美国 Federal Register 公开 API
│   └── core/
│       ├── relevance.py             # 相关性四段式判定（含回归自检）
│       ├── authenticity.py          # 源真实性（白名单/同形字/编辑距离/TLS）
│       └── coverage.py              # 覆盖率格子模型 + 缺口根因分类
├── docs/
│   └── verification-report-2026-09-10.md   # 全量验证报告（政策侧 + 企业侧）
├── scripts/
│   ├── verify_sources.py            # 可达性 + 真实采集（Python，主用）
│   ├── verify-sources.ps1           # 同上（PowerShell 版，备用）
│   ├── probe-urls.ps1               # curl 批量探测（诊断 TLS 问题用）
│   └── diag_cn_sources.py           # 中国源接口探测（写连接器前的摸底工具）
└── sources/
    ├── battery-recycling-sources.yaml   # 总入口
    ├── search-boundary.yaml             # 搜索边界 / 相关性规则 / 召回金标准
    ├── policy-cn.yaml                   # 中国 16 源（✅ 已验证）
    ├── policy-eu.yaml / policy-us.yaml  # 欧美政策源（✅ 已验证）
    ├── eia-sources.yaml                 # 环评公示源清单（10 站点）
    ├── companies.yaml                   # 26 家目标企业
    └── info-sources.yaml                # 咨询机构 + 协会
```

---

## 八、快速开始

```bash
git clone https://github.com/chiyuzhinian/Vane-Battery-Recycling-OSINT.git
cd Vane-Battery-Recycling-OSINT

# 数据源配置总入口
cat sources/battery-recycling-sources.yaml
```

> 部署步骤、环境变量、Docker Compose 见 04 篇附录与后续的 01 / 09 篇。
