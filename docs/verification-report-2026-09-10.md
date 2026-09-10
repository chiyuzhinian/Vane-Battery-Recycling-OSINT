# 数据源验证报告 · 2026-09-10

> 首次全量可达性验证 + 真实采集合验
> 复现命令：`py scripts/verify_sources.py`（可达性）/ `py scripts/verify_sources.py --collect US|EU`（真实采集）

---

## 一、总览

| 指标 | 结果 |
|---|---|
| 验证源总数 | **42 个**（CN 16 / EU 13 / US 13） |
| ✅ 可达可采 | **32 个（76.2%）** |
| 🚫 被反爬拦截 | 8 个（有替代路径，非阻塞） |
| ❌ 域名失效/不可达 | **2 个**（nrel.gov、eba250.eu） |
| 真实采集 | US 138 条、EU 26 条 |
| 相关性过滤后可用 | US 57 条、EU 15 条 |

**结论：搜索边界内的政策侧已基本打通。** 未打通的 8 个反爬站全部有降级路径（SPARQL / site: 搜索 / 等 API Key），不构成盲区；2 个失效域名已标记。

---

## 二、逐源结果

### 中国（16/16 全部可达 ✅）

| source_id | 域名 | HTTP | 大小 | 备注 |
|---|---|---|---|---|
| cn_std_samr | std.samr.gov.cn | 200 | 106 KB | ⭐ 占比 52.9%，待写专用 Connector |
| cn_mee | www.mee.gov.cn | 200 | 198 KB | 占比 16.5% |
| cn_miit | www.miit.gov.cn | 200 | 64 KB | 占比 9.4% |
| cn_miit_wap | wap.miit.gov.cn | 200 | 64 KB | 占比 3.5%，需与主站去重 |
| cn_mot_xxgk | xxgk.mot.gov.cn | 200 | 3 KB | 危废运输，易被忽略 |
| cn_samr | www.samr.gov.cn | 200 | 94 KB | |
| cn_ndrc | www.ndrc.gov.cn | 200 | 85 KB | |
| cn_gov | app.www.gov.cn | 200 | 0 KB | 空响应体，需换入口 |
| cn_ttbz | www.ttbz.org.cn | 200 | 233 KB | 团体标准 |
| cn_mof_szs | szs.mof.gov.cn | 200 | 15 KB | 税收优惠 |
| cn_tax_zj | zhejiang.chinatax.gov.cn | 200 | 53 KB | |
| cn_gz_gxj | gxj.gz.gov.cn | 200 | 66 KB | |
| cn_bj_jxj | jxj.beijing.gov.cn | 200 | 91 KB | |
| cn_cq_jjxxw | jjxxw.cq.gov.cn | 200 | 91 KB | |
| cn_hunan_gxt | gxt.hunan.gov.cn | 200 | 83 KB | ⚠️ 需 curl 回退（见 §四.1） |
| cn_jl_gxt | gxt.jl.gov.cn | 200 | 37 KB | |

### 欧盟（8 可达 / 4 反爬 / 1 失效）

| source_id | 域名 | HTTP | 结论 |
|---|---|---|---|
| eu_dg_env_batteries | environment.ec.europa.eu | 200 | ✅ 核心，可 diff 监测 |
| eu_dg_env_news | environment.ec.europa.eu | 200 | ✅ |
| eu_presscorner | ec.europa.eu | 200 | ✅ 需 curl 回退 |
| eu_eurostat_batteries | ec.europa.eu | 200 | ✅ 需 curl 回退 |
| eu_de_uba | umweltbundesamt.de | 200 | ✅ 德国 |
| eu_recharge | rechargebatteries.org | 200 | ✅ |
| eu_eurobat | eurobat.org | 200 | ✅ |
| eu_tande | transportenvironment.org | 200 | ✅ |
| eu_eurlex_battery_reg | eur-lex.europa.eu | **202** | 🚫 反爬 → **改走 SPARQL（已验证可用）** |
| eu_eurlex_oj_l | eur-lex.europa.eu | **202** | 🚫 同上 |
| eu_echa | echa.europa.eu | **403** | 🚫 → site: 搜索降级 |
| eu_fr_ademe | ademe.fr | **403** | 🚫 → site: 搜索降级 |
| eu_eba250 | eba250.eu | — | ❌ 域名失效 |

### 美国（8 可达 / 4 反爬 / 1 失效）

| source_id | 域名 | HTTP | 结论 |
|---|---|---|---|
| us_federal_register | federalregister.gov | 200 | ✅ **公开 API，无需 Key** |
| us_epa_batteries | epa.gov | 200 | ✅ URL 已修正（原 404） |
| us_doe_eere | energy.gov | 200 | ✅ URL 已修正 |
| us_doe_mesc | energy.gov | 200 | ✅ URL 已修正（改用站根） |
| us_irs_45x | irs.gov | 200 | ✅ |
| us_usgs_minerals | usgs.gov | 200 | ✅ |
| us_naatbatt | naatbatt.org | 200 | ✅ |
| us_recell | recellcenter.org | 200 | ✅ 需浏览器 UA |
| us_congress_bills | congress.gov | **403** | 🚫 API 需免费 Key |
| us_state_ca_calrecycle | calrecycle.ca.gov | **403** | 🚫 → site: 搜索降级 |
| us_bci | batterycouncil.org | **403** | 🚫 → site: 搜索降级 |
| us_call2recycle | call2recycle.org | **403** | 🚫 → site: 搜索降级 |
| us_nrel | nrel.gov | — | ❌ 本机网络不可达 |

---

## 三、真实采集结果

### 美国 · Federal Register

```
输入：4 个关键词 × 3 个机构（DOE / EPA / IRS） × 2 页
取回：138 条原始文档
过滤：57 条相关（41.3%）、81 条噪声
落盘：outputs/us_federal_20260910_194847.jsonl
```

**过滤掉的噪声类型**（说明过滤器工作正常）：
- TSCA 化学品新用途规则、空气质量管理计划、温室气体排放标准
- 电池充电器能效测试程序（`battery charger` 已列入拒绝词）
- 电解电容无功补偿等与电池无关的能源规则

**保住的关键政策**（说明过滤器没有过度杀伤）：
- `Advanced Manufacturing Production Credit`（IRA 45X 最终规则）
- `Clean Vehicle Credits ... Critical Minerals and Battery Components`
- `Notice of Final Determination on 2023 DOE Critical Materials List`
- `Request for Public Comment ... Battery and Electronics Recycling Inc.`

### 欧盟 · EUR-Lex SPARQL

```
输入：CELEX 32023R1542 精确跟踪 + 关键词发现
取回：26 条（已按语言去重，见 §四.3）
过滤：15 条相关
落盘：outputs/eur_lex_20260910_195042.jsonl
```

**采集到的内容**：电池法规 (EU) 2023/1542 本体 **+ 14 个更正版本**（R(01) ~ R(14)）。

> 💡 **情报价值**：14 个更正版本说明该法规条文在实务中存在大量歧义与反复修订。
> 这个数字本身就是跟踪信号——每次新增更正都可能影响企业的合规路径。
> 通用搜索引擎给不了这个，只有结构化源能给。

---

## 四、验证中发现并修复的 4 个技术问题

### 1. Python 的 TLS 栈连不上部分政府站点（重要）

| 站点 | httpx（OpenSSL） | curl（Windows SChannel） |
|---|---|---|
| gxt.hunan.gov.cn | ❌ `SSL: BAD_ECPOINT` | ✅ 200 / 83 KB |
| ec.europa.eu | ❌ `SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC` | ✅ 200 / 21 KB |

**这不是源的问题，是客户端的问题**——若不做这一步排查，会误判两个可用源为"失效"。

**修复**：`app/connectors/base.py` 增加 `_try_curl` 回退，并维护 `TLS_QUIRK_HOSTS` 清单（已知不兼容的站直接走 curl，省一次失败往返）。

### 2. 部分站点只放行浏览器 UA

| 站点 | 默认 UA | 浏览器 UA |
|---|---|---|
| recellcenter.org | ❌ 403 | ✅ 200 / 69 KB |

**修复**：curl 回退统一带浏览器 UA；`verify_sources.py` 遇 403 自动重试一次。

### 3. SPARQL 返回同一法规的多语言标题（数据污染）

同一 CELEX 会返回 da / de / en / fr / it 等多语言标题。若不去重，同一条法规会在库中重复 5~24 次，**并且会让交叉验证的"独立来源计数"虚高**（把同一份文件的不同语言版本当成多个独立来源）。

**修复**：`eur_lex.py` 只保留 `lang == "en"`。效果：EU 采集量 65 → 26 条，全部为有效记录。

### 4. 相关性规则过度杀伤（漏政策）

第一版用纯子串 `battery recycl`，结果误杀 3 条核心政策：

| 被误杀的文档 | 原因 |
|---|---|
| `Advanced Manufacturing Production Credit` | 标题不含 "battery" |
| `Clean Vehicle Credits ... Critical Minerals and Battery Components` | 不含 "battery recycl" |
| `Notice of Final Determination on 2023 DOE Critical Materials List` | 不含 "battery" |
| `Battery and Electronics Recycling Inc.` | 中间夹了 "and electronics" |

**修复**（`app/core/relevance.py`）改为四段式：
1. **强模式**（正则，允许中间夹 ≤5 个词）→ 相关
2. **上下文词 + 锚点共现** → 相关（如 "critical mineral" 需与 "battery/lithium/vehicle" 同现）
3. **税优/能源条款类** → 相关但标 `needs_human_review`（**宁可多一条待审，不可漏一条政策**）
4. 其余 → 丢弃

**效果**：US 采集合规数 16 → **57**（提升 3.6 倍），同时噪声仍被拦截。

回归样本见 `app/core/relevance.py` 的 `__main__`，任何时候改规则都要跑一遍：

```bash
py app/core/relevance.py
```

---

## 五、结论

### 已达成

- ✅ **CN 政策源 100% 可达**（16/16），已按实测占比排定优先级
- ✅ **US 政策源打通**，Federal Register 开放 API 已跑出 138 条真实数据
- ✅ **EU 政策源走 SPARQL 打通**，拿到法规本体 + 14 个更正版本
- ✅ **相关性规则经真实数据校准**，并建立回归样本
- ✅ **源真实性校验**（域名白名单 / 同形字 / 编辑距离）已实现

### 剩余缺口

| 缺口 | 影响 | 建议动作 |
|---|---|---|
| std.samr.gov.cn 未直采 | 占 CN 政策量 52.9%，**最大单点** | 优先写专用 Connector |
| CN 站点仅验证到站根 | 不知栏目 URL 与更新频率 | 探测栏目结构 + RSS |
| 4 个 US + 4 个 EU 站点被 403 | 有 site: 降级，非阻塞 | 需要时上 Playwright |
| Congress.gov 缺 API Key | 少一个美国立法提案源 | api.data.gov 申请免费 Key |
| 企业侧连接器（cninfo / eia）未实现 | **企业 130 格的主要来源** | 第二阶段优先 |
| nrel.gov / eba250.eu 失效 | 各少 1 个源，可替代 | 标记观察，不阻塞 |

---

## 六、企业侧连接器验证（同日追加）

企业侧此前是**0 覆盖**——26 家企业 × 5 维度 = 130 格，一格都没采。
本轮补上两个连接器：`cninfo`（公告/年报）与 `eia`（环评公示）。

### 6.1 巨潮资讯（cninfo）—— ✅ 成功，数据质量极好

```
接口：GET http://www.cninfo.com.cn/new/fulltextSearch/full
实测：HTTP 200 application/json，无需 Key，无需登录
采集：84 条 → 23 条相关（27.4%）
```

**采到的公告（全部命中目标企业）**：

| 企业 | 公告 |
|---|---|
| 格林美 | 控股子公司动力再生与兰钧新能源签署**动力电池绿色回收利用**战略合作协议 |
| 格林美 | 与匈牙利总领事馆签署**报废动力电池循环回收**项目合作备忘录 |
| 格林美 | 无锡空港经开区**年回收处理 10 万套动力电池**项目投资协议 |
| 天奇股份 | 对外投资暨签订《**动力电池回收利用湿法冶金项目**合资协议书》 |
| 光华科技 | 与安徽鑫盛/元宝淘车/五洲龙/奇瑞万达/广西华奥/南京金龙/北汽 签署**废旧动力电池回收处理**合作协议（7 连） |

> 这直接填上了 `strategy` 与 `feedstock` 两个维度，并且**每条都有可溯源的公告详情页 URL**。

**修复的一个缺陷**：初版把公告标题映射成**单**维度，结果 23 条全被标成 `strategy`（因为标题里都有"合作"）。
而"签订动力电池回收战略合作协议"同时涉及 strategy 与 feedstock。
已改为**多标签**（`dimension_hint` 返回列表），并调整关键词优先级（产能/产销 > 回收 > 技术 > 人事 > 合作）。

### 6.2 环评公示（eia）—— ⚠️ 部分成功，暴露一个重要的结构性事实

```
采集：108 条 → 2 条相关
命中内容：
  · 生态环境部《关于印发集成电路制造、锂离子电池及相关电池材料制造、
    电解铝、水泥制造四个行业建设项目环境影响评价文件审批原则的通知》
  · 同文件的征求意见稿
```

**关键发现：省级/国家级"环评管理"栏目首页给的是「政策与审批原则」，不是「企业项目公示」。**

要拿到邦普、金晟等企业的具体产能项目环评，必须进到各站点的
**"建设项目环评受理公示"专栏**（通常在站点深层），或使用站点搜索。

**已做的两处改进**：
1. 排除栏目导航链接——增加 `_looks_like_article()` 判定：
   真正的公示条目 URL 必带 4 位年份或 ≥5 位数字 ID，而栏目目录形如 `/ywgz/hjyxpj/jsxmhjyxpj/`。
   不排除时会混入"建设项目环境影响评价"等栏目名污染结果。
2. 相关性规则补充"电池制造/材料制造"类目——上述 MEE 审批原则标题里**没有"回收"二字**，
   但它恰恰决定电池（含回收）项目能否获批建厂，属于必须跟踪的政策。
   已加入 `POLICY_MAYBE_TERMS`，转人工复核而非丢弃。

**站点可用性**：

| 站点 | 状态 |
|---|---|
| 生态环境部（受理公示 / 环评管理） | ✅ 200 |
| 广东省生态环境厅 | ✅ 200（邦普、金晟、杰成所在） |
| 江苏省生态环境厅 | ✅ 200 |
| 湖南省生态环境厅 | ✅ 需 curl 回退（邦普循环所在地，优先级最高） |
| 上海市 / 安徽省 / 浙江省生态环境厅 | ✅ 可采（条目较少） |
| 江西省生态环境厅 | 🚫 JS cookie 挑战页，需 Playwright |
| 中国环评网 chinaeia.com | ❌ 站点不可达 |

**待办**：探测各省"受理公示"专栏的准确 URL，并补充**市级**生态环境局
（如宁德市、荆门市、宜春市）——市级公示往往比省级更早、更细，含具体处理规模。

### 6.3 企业侧覆盖率现状

| 维度 | 企业侧来源 | 覆盖情况 |
|---|---|---|
| strategy | cninfo ✅ + 环评 | 🟢 13 家上市系已通 |
| operation | cninfo ✅（年报/产销）+ 环评（规模） | 🟡 上市系可采，非上市待环评专栏 |
| feedstock | cninfo ✅ + 环评（处理能力） | 🟡 同上 |
| technology | cninfo（专利/技术公告）+ 专利库（未接） | 🔴 专利连接器未实现 |
| hr | cninfo ✅（任免公告） | 🟡 仅上市系 |

**结论**：13 家上市系企业（占 50%）的 4 个维度已具备稳定来源；
13 家非上市企业仍主要依赖环评专栏的进一步打通。

---

## 七、复现方式

```bash
# 环境：Python 3.12（本机命令为 py）
py scripts/verify_sources.py                 # 全量可达性
py scripts/verify_sources.py --region CN     # 只看中国
py scripts/verify_sources.py --collect US    # 真实采集美国
py scripts/verify_sources.py --json          # JSON 输出（可接 CI）
py app/core/relevance.py                     # 相关性规则回归自检
```
