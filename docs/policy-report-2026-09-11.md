# 退役动力电池 / 报废汽车 / 黑粉 —— 欧美政策法规采集报告

生成时间：2026-09-11 02:31 UTC　（数据截止同上）

> **阅读说明**：本报告只收录**已判定相关**的条目，每条都附原文链接，可直接点开核查。
> 采集层已剔除：非 200 响应的拦截页、WAF 人机验证页、以及门户模糊匹配产生的噪声。

---

## 一、总览

| 指标 | 数量 |
|---|---:|
| 去重后的证据条目 | 1284 |
| 判定为**相关** | **236** |
| 　其中高置信（自动判定） | 113 |
| 　其中待人工复核 | 123 |
| 覆盖监管层级 | 7 |
| 欧盟法规全文快照 | **7 部**（可离线核查条文） |

### 按监管层级分布

| 层级 | 条目 | 主要机构 | 最高可信度 |
|---|---:|---|---:|
| EU 一级立法 | 19 | 欧盟官方公报（EUR-Lex）、欧盟官方公报（EUR-Lex 关键词检索） | 100 |
| EU 机构文件 | 6 | 欧洲化学品管理局（ECHA） | 95 |
| 成员国法 | 4 | 德国联邦法律门户（官方 XML） | 100 |
| 成员国数据 | 19 | ADEME 开放数据门户、Stichting OPEN（电池/电子生产者责任组织） | 95 |
| 美国联邦 | 177 | 美国联邦公报（Federal Register）、DOT 管道与危险材料安全管理局（PHMSA） | 100 |
| 美国州级 | 3 | CalRecycle | 92 |
| 美国行业 | 8 | Battery Council International（铅电池协会） | 82 |

---

## 二、黑粉监管四条线（本项目的核心结论）

> **黑粉的监管不在电池法里**，而是分散在四条独立线上。
> 不同的业务问题要引不同的法，下面把已收集的证据按线归位。

### ①废物跨境转移 —— 黑粉在成员国之间运输、或出口到第三国时适用的规则

> 为什么归这条线：黑粉属于废物，跨境运输受《废物运输条例》(EU) 2024/1157 与巴塞尔公约约束

**法规全文命中（5 部，已存本地快照）**

- **CELEX 32006L0066**（45,594 字符）
  - 本地快照：`sources/eurlex-fulltext/32006L0066.txt`
- **CELEX 32008L0098**（78,227 字符）
  - 本地快照：`sources/eurlex-fulltext/32008L0098.txt`
- **CELEX 32023R1542**（352,016 字符）
  - 在线原文：http://publications.europa.eu/resource/cellar/d0065c31-2ce3-11ee-95a2-01aa75ed71a1
  - 本地快照：`sources/eurlex-fulltext/32023R1542.txt`
- **CELEX 32024R1157**（303,332 字符）
  - 本地快照：`sources/eurlex-fulltext/32024R1157.txt`
- **CELEX 52023PC0451**（236,682 字符）
  - 本地快照：`sources/eurlex-fulltext/52023PC0451.txt`

### ②危险货物运输 —— 按 UN 编号运输时的包装、文件与培训要求

> 为什么归这条线：黑粉与 DDR 电池属危险货物，美国归 49 CFR（PHMSA），欧洲归 ADR

**与电池/黑粉直接相关（42 条）**

- **Transporting Lithium Batteries | PHMSA**
  - 原文：https://www.phmsa.dot.gov/lithiumbatteries
- **Sustainable Materials Management (SMM) Web Academy Webinar: Safe Transportation of Lithium Batteries: What You Need to K**
  - 原文：https://www.epa.gov/smm/sustainable-materials-management-smm-web-academy-webinar-safe-transportation-lithium-batteries
- **Hazardous Materials: Notice of Actions on Special Permits**
  - 日期：`2025-05-12`
  - 原文：https://www.federalregister.gov/documents/2025/05/12/2025-08273/hazardous-materials-notice-of-actions-on-special-permits
- **Hazardous Materials: Notice of Actions on Special Permits**
  - 日期：`2024-04-02`
  - 原文：https://www.federalregister.gov/documents/2024/04/02/2024-06884/hazardous-materials-notice-of-actions-on-special-permits
- **Hazardous Materials: Notice of Actions on Special Permits**
  - 日期：`2025-06-12`
  - 原文：https://www.federalregister.gov/documents/2025/06/12/2025-10723/hazardous-materials-notice-of-actions-on-special-permits
- **Hazardous Materials: Notice of Actions on Special Permits**
  - 日期：`2023-04-24`
  - 原文：https://www.federalregister.gov/documents/2023/04/24/2023-08590/hazardous-materials-notice-of-actions-on-special-permits

**属该监管领域、但未检出电池线索（1 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Hazardous Materials: Mandatory Regulatory Reviews To Unleash American Energy and Improve Government Efficiency**
  - 日期：`2025-06-04`
  - 原文：https://www.federalregister.gov/documents/2025/06/04/2025-10091/hazardous-materials-mandatory-regulatory-reviews-to-unleash-american-energy-and-improve-government

### ③危废定性 —— 黑粉是否按危险废物管理 —— 直接决定处置成本

> 为什么归这条线：定性不同，运输、存储、处置的许可与成本差一个量级

**属该监管领域、但未检出电池线索（1 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Verordnung über das Europäische Abfallverzeichnis [avv]**
  - 原文：https://www.gesetze-im-internet.de/avv/

### ④战略价值认定 —— 黑粉作为关键原材料回收能拿到的政策激励

> 为什么归这条线：欧盟关键原材料法 (EU) 2024/1252、美国 IRA 45X 都把回收料计入激励

**法规全文命中（2 部，已存本地快照）**

- **CELEX 32024R1252**（221,942 字符）
  - 本地快照：`sources/eurlex-fulltext/32024R1252.txt`
- **CELEX 52023PC0451**（236,682 字符）
  - 本地快照：`sources/eurlex-fulltext/52023PC0451.txt`

**与电池/黑粉直接相关（4 条）**

- **EU-BATTERIES_REGULATION-ANX_I_VI_ART_13_5 - ECHA**
  - 原文：https://echa.europa.eu/eu-batteries_regulation-anx_i_vi_art_13_5?p_p_id=eucleflegislationlist_WAR_euclefportlet&p_p_lifecycle=0
- **Section 45X Advanced Manufacturing Production Credit**
  - 日期：`2023-12-15`
  - 原文：https://www.federalregister.gov/documents/2023/12/15/2023-27498/section-45x-advanced-manufacturing-production-credit
- **Section 30D Excluded Entities**
  - 日期：`2023-12-04`
  - 原文：https://www.federalregister.gov/documents/2023/12/04/2023-26513/section-30d-excluded-entities
- **Advanced Manufacturing Production Credit; Correction**
  - 日期：`2024-11-26`
  - 原文：https://www.federalregister.gov/documents/2024/11/26/2024-27588/advanced-manufacturing-production-credit-correction

**属该监管领域、但未检出电池线索（4 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Transfer of Certain Credits**
  - 日期：`2024-04-30`
  - 原文：https://www.federalregister.gov/documents/2024/04/30/2024-08926/transfer-of-certain-credits
- **Section 6418 Transfer of Certain Credits**
  - 日期：`2023-06-21`
  - 原文：https://www.federalregister.gov/documents/2023/06/21/2023-12799/section-6418-transfer-of-certain-credits
- **Section 6417 Elective Payment of Applicable Credits**
  - 日期：`2023-06-21`
  - 原文：https://www.federalregister.gov/documents/2023/06/21/2023-12798/section-6417-elective-payment-of-applicable-credits
  - …另有 1 条

---

## 三、政策法规清单（按监管层级）

### EU 一级立法

**机构**：欧盟官方公报（EUR-Lex）　**可信度**：100/100　**条目**：19　
**内容**：电池与废电池法规 (EU) 2023/1542 及关联立法

#### 欧盟官方公报（EUR-Lex）（15 条）

- **EU legislation CELEX 32023R1542R(14)**
  - 日期 2026-07-28　原文：http://publications.europa.eu/resource/cellar/ab3cbe7e-8a1f-11f1-8e61-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(13)**
  - 日期 2026-04-10　原文：http://publications.europa.eu/resource/cellar/0247a0f6-3476-11f1-be39-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(12)**
  - 日期 2026-02-17　原文：http://publications.europa.eu/resource/cellar/3f4e448f-0ba1-11f1-8870-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(11)**
  - 日期 2025-10-08　原文：http://publications.europa.eu/resource/cellar/8cc766e0-a3e2-11f0-97c8-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(10)**
  - 日期 2025-03-25　原文：http://publications.europa.eu/resource/cellar/ece5f079-0919-11f0-b1a3-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
  - …另有 10 条（共 15 条，见 `outputs/eol_*.jsonl`）

#### 欧盟官方公报（EUR-Lex 关键词检索）（4 条）

- **Regulation (EU) 2026/1738 of the European Parliament and of the Council of 8 July 2026 on circularity requirements for vehicle des**
  - 日期 2026-07-08　原文：http://publications.europa.eu/resource/cellar/394bc298-86fd-11f1-bf5e-01aa75ed71a1
- **Commission Implementing Regulation (EU) 2025/2289 of 13 November 2025 laying down rules for the application of Regulation (EU) 202**
  - 日期 2025-11-13　原文：http://publications.europa.eu/resource/cellar/93e152fa-c67b-11f0-8da2-01aa75ed71a1
- **Regulation (EU) 2025/1561 of the European Parliament and of the Council of 18 July 2025 amending Regulation (EU) 2023/1542 as rega**
  - 日期 2025-07-18　原文：http://publications.europa.eu/resource/cellar/fe1163e4-6cdd-11f0-bf4e-01aa75ed71a1
- **Commission Delegated Regulation (EU) 2025/606 of 21 March 2025 supplementing Regulation (EU) 2023/1542 of the European Parliament **
  - 日期 2025-03-21　原文：http://publications.europa.eu/resource/cellar/5881a55e-5873-11f0-a9d0-01aa75ed71a1

### EU 机构文件

**机构**：欧洲化学品管理局（ECHA）　**可信度**：95/100　**条目**：6　
**内容**：电池法规物质限制数据库（附件 I / 第 13(5) 条 / 附件 VI）

- **Legislation - ECHA**　`待复核`
  - 原文：https://echa.europa.eu/legislation
- **Batteries - ECHA**
  - 原文：https://echa.europa.eu/batteries
- **Legislation - ECHA**
  - 原文：https://echa.europa.eu/batteries-legislation
- **Understanding the Batteries Regulation - ECHA**
  - 原文：https://echa.europa.eu/understanding-batteries-regulation
- **ECHA's activities under Batteries Regulation - ECHA**
  - 原文：https://echa.europa.eu/echas-activities-under-batteries-regulation
  - …另有 1 条（共 6 条，见 `outputs/eol_*.jsonl`）

### 成员国法

**机构**：德国联邦法律门户（官方 XML）　**可信度**：100/100　**条目**：4　
**内容**：AltfahrzeugV 报废车法 / BattDG 电池法 / AVV 废物目录

- **Verordnung über Anforderungen an die Behandlung von Elektro- und Elektronik-Altgeräten* [eag-behandv]**
  - 原文：https://www.gesetze-im-internet.de/eag-behandv/
- **Verordnung über die Überlassung, Rücknahme und umweltverträgliche Entsorgung von Altfahrzeugen [altautov]**
  - 原文：https://www.gesetze-im-internet.de/altautov/
- **Gesetz zur Durchführung der Verordnung (EU) 2023/1542 betreffend Batterien und Altbatterien [battdg]**
  - 原文：https://www.gesetze-im-internet.de/battdg/
- **Verordnung über das Europäische Abfallverzeichnis [avv]**　`黑粉线 ③`
  - 原文：https://www.gesetze-im-internet.de/avv/

### 成员国数据

**机构**：ADEME 开放数据门户　**可信度**：95/100　**条目**：19　
**内容**：报废车（VHU）回收数据集

#### ADEME 开放数据门户（12 条）

- **Page non trouvée**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-trrs-et-trvs-des-cvhu-depuis-2018
- **Page non trouvée**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-liste-des-producteurs-enregistres-a-syderep
- **Page non trouvée**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-performances-cumulees-depuis-2018
- **Materiaux TE T1 - Répartition par type de traitement de quelques matériaux d'un VHU**
  - 原文：https://data.ademe.fr/datasets/materiaux-te-t1
- **REP - VHU - TRR et TRV des Broyeurs depuis 2018**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-trr-et-trv-des-broyeurs-en-2018
  - …另有 7 条（共 12 条，见 `outputs/eol_*.jsonl`）

#### Stichting OPEN（电池/电子生产者责任组织）（7 条）

- **Stichting OPEN - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/
- **Producenten & importeurs - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/producenten-importeurs/
- **Inzamelpartners, zoals gemeenten, retailers en metaalrecyclers - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/inzamelpartners-retailers/
- **Onze kerntaken - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/onze-organisatie/onzekerntaken/
- **Peperzeel opent nieuwe sorteerlijn voor batterijen - Stichting OPEN**
  - 原文：https://www.stichting-open.org/2026/07/15/peperzeel-opent-nieuwe-sorteerlijn-voor-batterijen/
  - …另有 2 条（共 7 条，见 `outputs/eol_*.jsonl`）

### 美国联邦

**机构**：美国联邦公报（Federal Register）　**可信度**：100/100　**条目**：177　
**内容**：DOE / EPA / IRS / DOT 的法规、通知与征询

#### 美国联邦公报（Federal Register）（169 条）

- **Securing the United States Bulk-Power System**　`待复核`
  - 日期 2026-09-09　原文：https://www.federalregister.gov/documents/2026/09/09/2026-18370/securing-the-united-states-bulk-power-system
- **Superfund Tax on Chemical Substances; Request To Modify List of Taxable Substances; Notice of Filing for Butadiene-acrylonitrile-m**　`待复核`
  - 日期 2026-09-09　原文：https://www.federalregister.gov/documents/2026/09/09/2026-18264/superfund-tax-on-chemical-substances-request-to-modify-list-of-taxable-substances-notice-of-filing
- **Repeal of Fossil Fuel Restrictions for New Federal Buildings and Major Renovations of Federal Buildings**　`待复核`
  - 日期 2026-09-02　原文：https://www.federalregister.gov/documents/2026/09/02/2026-17979/repeal-of-fossil-fuel-restrictions-for-new-federal-buildings-and-major-renovations-of-federal
- **Rescission of Production Incentives for Cellulosic Biofuels**　`待复核`
  - 日期 2026-09-01　原文：https://www.federalregister.gov/documents/2026/09/01/2026-17872/rescission-of-production-incentives-for-cellulosic-biofuels
- **Nominations Request for the Good Neighbor Environmental Board**　`待复核`
  - 日期 2026-08-20　原文：https://www.federalregister.gov/documents/2026/08/20/2026-16931/nominations-request-for-the-good-neighbor-environmental-board
  - …另有 164 条（共 169 条，见 `outputs/eol_*.jsonl`）

#### DOT 管道与危险材料安全管理局（PHMSA）（8 条）

- **Understanding the Risks of Damaged, Defective, or Recalled (DDR) Lithium Batteries | PHMSA**　`黑粉线 ②`
  - 日期 March 29, 　原文：https://www.phmsa.dot.gov/training/hazmat/understanding-risks-damaged-defective-or-recalled-ddr-lithium-batteries
- **Lithium Battery Guide for Shippers | PHMSA**
  - 日期 November 2　原文：https://www.phmsa.dot.gov/training/hazmat/lithium-battery-guide-shippers
- **Transporting Lithium Batteries | PHMSA**　`黑粉线 ②`
  - 原文：https://www.phmsa.dot.gov/lithiumbatteries
- **Sustainable Materials Management (SMM) Web Academy Webinar: Safe Transportation of Lithium Batteries: What You Need to Know in 202**　`黑粉线 ②`
  - 原文：https://www.epa.gov/smm/sustainable-materials-management-smm-web-academy-webinar-safe-transportation-lithium-batteries
- **Used Lithium-Ion Batteries | US EPA**
  - 原文：https://www.epa.gov/recycle/used-lithium-ion-batteries
  - …另有 3 条（共 8 条，见 `outputs/eol_*.jsonl`）

### 美国州级

**机构**：CalRecycle　**可信度**：92/100　**条目**：3　
**内容**：Responsible Battery Recycling Program（AB 2440）

- **Product Stewardship and Extended Producer Responsibility (EPR) - CalRecycle Home Page**　`待复核`
  - 原文：https://calrecycle.ca.gov/epr/
- **Recycle - CalRecycle Home Page**　`待复核`
  - 原文：https://calrecycle.ca.gov/Recycle/
- **Battery Stewardship - CalRecycle Home Page**
  - 原文：https://calrecycle.ca.gov/EPR/batteries/

### 美国行业

**机构**：Battery Council International（铅电池协会）　**可信度**：82/100　**条目**：8　
**内容**：铅电池回收率统计、州级立法动向

- **Battery Council International Home | Battery Council International**
  - 原文：https://batterycouncil.org/
- **Battery Facts & Applications | Battery Council International**
  - 原文：https://batterycouncil.org/battery-facts-and-applications/
- **Battery Safety is a Global Issue that Doesn’t Stop at the Border**
  - 原文：https://batterycouncil.org/news/battery-safety-is-a-global-issue-that-doesnt-stop-at-the-border/
- **Why Every Lead Battery Matters to America's Supply Chain**
  - 原文：https://batterycouncil.org/news/critical-mineral-recovery-why-every-lead-battery-matters-to-americas-supply-chain/
- **Battery Policy & Initiatives | Battery Council International**
  - 原文：https://batterycouncil.org/policy-initiatives/
  - …另有 3 条（共 8 条，见 `outputs/eol_*.jsonl`）

---

## 四、欧盟法规全文库（可离线核查条文）

> 只有链接的报告无法回答「第 X 条规定了什么」。
> 下面这些法规已把**正文**抓下来存本地，可搜索、可引用、可日后比对修订。

| CELEX | 正文长度 | 本地快照 | 在线原文 |
|---|---:|---|---|
| `32000L0053` | 32,106 字符 | `sources/eurlex-fulltext/32000L0053.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32000L0053 |
| `32006L0066` | 45,594 字符 | `sources/eurlex-fulltext/32006L0066.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006L0066 |
| `32008L0098` | 78,227 字符 | `sources/eurlex-fulltext/32008L0098.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32008L0098 |
| `32023R1542` | 352,016 字符 | `sources/eurlex-fulltext/32023R1542.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542 |
| `32024R1157` | 303,332 字符 | `sources/eurlex-fulltext/32024R1157.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157 |
| `32024R1252` | 221,942 字符 | `sources/eurlex-fulltext/32024R1252.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252 |
| `52023PC0451` | 236,682 字符 | `sources/eurlex-fulltext/52023PC0451.txt` | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52023PC0451 |

> 更新快照：`py scripts/fetch_eurlex_fulltext.py`（`--terms` 可按关键词扩充）

---

## 五、其他已下载的原始文档

| 文件 | 大小 | 来源站点 |
|---|---:|---|
| `Lithium-Battery-Guide-2024.pdf` | 12.3 MB | phmsa |
| `april_29_2021_epa_and_dot_speaker_slides_508.pdf` | 9.1 MB | phmsa |
| `DDR-brochure.pdf` | 2.7 MB | phmsa |
| `final_lithium-ion-battery-workshop-public-report_508web.pdf` | 799 KB | phmsa |
| `final.pdf` | 567 KB | phmsa |
| `Final-5-16-Lithium-Battery-Recycling-Safety-Advisory.pdf` | 352 KB | phmsa |
| `echa.europa.eu-eu-batteries_regulation-anx_i_vi_art_13_5.txt` | 220 KB | echa |
| `april_29_2021_introductory_slides_-_smm_web_academy.pdf` | 212 KB | phmsa |
| `ICAO_TI_Lithium_Battery_Summary_Chart.pdf` | 134 KB | phmsa |

---

## 六、数据源健康度

| 源 | 层级 | 相关条目 | 命中率参考 |
|---|---|---:|---|
| `us_federal_register` | 美国联邦 | 169 | — |
| `eu_eurlex_battery_reg` | EU 一级立法 | 15 | — |
| `browser_france` | 成员国数据 | 12 | — |
| `browser_bci` | 美国行业 | 8 | — |
| `browser_phmsa` | 美国联邦 | 8 | — |
| `browser_netherlands` | 成员国数据 | 7 | — |
| `browser_echa` | EU 机构文件 | 6 | — |
| `eu_eurlex_keyword` | EU 一级立法 | 4 | — |
| `de_gesetze` | 成员国法 | 4 | — |
| `browser_calrecycle` | 美国州级 | 3 | — |

> 命中率口径说明：不同通道的采集方式不同（API 精准查询 vs 全文检索），
> 跨通道比较命中率没有意义，故此处不列。同类通道内的命中率见 `outputs/eol_summary_*.md`。

---

## 七、已知覆盖缺口

| 缺口 | 说明 |
|---|---|
| 其他欧盟成员国 | 目前只覆盖德国、法国、荷兰；西班牙/意大利/波兰/比利时尚未接入 |
| 美国州级立法 | 仅加州 CalRecycle；其他州（如华盛顿、缅因）的电池 EPR 法案未覆盖 |
| 国际公约 | 巴塞尔公约（UNEP）源已登记但未纳入主管线 |
| 行业数据库 | Fastmarkets / Benchmark 等付费源未接入（成本问题） |
| 回收企业 | 目前仅有 Peperzeel（荷兰）一条企业产能情报，欧洲主要回收商（Umicore / Accurec / Duesenfeld）未系统覆盖 |

> 成员国源的选择方法（重要）：**看有没有专业机构或结构化 API，而不是看有没有开放数据门户。**
> 实测通用国家门户（govdata.de / dane.gov.pl）的全文搜索是**单字 OR 匹配**，搜"报废车"会返回"职业介绍所登记册"，垂直检索不可用。

---

_本报告由 `scripts/make_report.py` 生成，数据源为 `outputs/*.jsonl`。_
_重新生成：`py scripts/make_report.py`_
