# 退役动力电池 / 报废汽车 / 黑粉 —— 欧美政策法规采集报告

生成时间：2026-09-11 05:53 UTC　（数据截止同上）

> **阅读说明**：本报告只收录**已判定相关**的条目，每条都附原文链接，可直接点开核查。
> 采集层已剔除：非 200 响应的拦截页、WAF 人机验证页、以及门户模糊匹配产生的噪声。

---

## 一、总览

| 指标 | 数量 |
|---|---:|
| 去重后的证据条目 | 1626 |
| 判定为**相关** | **358** |
| 　其中高置信（自动判定） | 158 |
| 　其中待人工复核 | 200 |
| 覆盖监管层级 | 7 |
| 欧盟法规全文快照 | **7 部**（可离线核查条文） |

### 按监管层级分布

| 层级 | 条目 | 主要机构 | 最高可信度 |
|---|---:|---|---:|
| EU 一级立法 | 50 | 欧盟官方公报（EUR-Lex）、欧盟官方公报（EUR-Lex 关键词检索） | 100 |
| EU 机构文件 | 6 | 欧洲化学品管理局（ECHA） | 95 |
| 成员国法 | 28 | 荷兰 KOOP BWB 基础法规库（官方 XML）、西班牙官方公报 BOE（立法整合库 REST API） | 100 |
| 成员国数据 | 19 | ADEME 开放数据门户、Stichting OPEN（电池/电子生产者责任组织） | 95 |
| 美国联邦 | 244 | 美国联邦公报（Federal Register）、DOT 管道与危险材料安全管理局（PHMSA） | 100 |
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
  - 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157
  - 本地快照：`sources/eurlex-fulltext/32024R1157.txt`
- **CELEX 52023PC0451**（236,682 字符）
  - 本地快照：`sources/eurlex-fulltext/52023PC0451.txt`

**属该监管领域、但未检出电池线索（6 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Regulation (EU) 2024/1157 of the European Parliament and of the Council of 11 April 2024 on shipments of waste, amending**
  - 日期：`2020-08-20`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157
- **EU legislation CELEX 32024R1157R(01)**
  - 日期：`2024-09-20`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157R(01)
- **EU legislation CELEX 32024R1157R(02)**
  - 日期：`2024-12-09`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157R(02)
  - …另有 3 条

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

**属该监管领域、但未检出电池线索（5 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Verordnung über das Europäische Abfallverzeichnis [avv]**
  - 原文：https://www.gesetze-im-internet.de/avv/
- **Authorization of State Hazardous Waste Management Program Revisions: California**
  - 日期：`2025-09-11`
  - 原文：https://www.federalregister.gov/documents/2025/09/11/2025-17540/authorization-of-state-hazardous-waste-management-program-revisions-california
- **Massachusetts: Final Authorization of State Hazardous Waste Management Program Revisions**
  - 日期：`2025-09-05`
  - 原文：https://www.federalregister.gov/documents/2025/09/05/2025-17053/massachusetts-final-authorization-of-state-hazardous-waste-management-program-revisions
  - …另有 2 条

### ④战略价值认定 —— 黑粉作为关键原材料回收能拿到的政策激励

> 为什么归这条线：欧盟关键原材料法 (EU) 2024/1252、美国 IRA 45X 都把回收料计入激励

**法规全文命中（2 部，已存本地快照）**

- **CELEX 32024R1252**（221,942 字符）
  - 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252R(01)
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

**属该监管领域、但未检出电池线索（11 条）**

> 这些文件在正文里出现该领域的通用表述（如"危险货物法规"样板文字），可能相关也可能无关，需人工判断。

- **Corrigendum to Regulation (EU) 2024/1252 of the European Parliament and of the Council of 11 April 2024 establishing a f**
  - 日期：`2024-06-03`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252R(01)
- **Regulation (EU) 2024/1252 of the European Parliament and of the Council of 11 April 2024 establishing a framework for en**
  - 日期：`2024-05-23`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252
- **Corrigendum to Regulation (EU) 2024/1252 of the European Parliament and of the Council of 11 April 2024 establishing a f**
  - 日期：`2024-10-01`
  - 原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252R(02)
  - …另有 8 条

---

## 三、政策法规清单（按监管层级）

### EU 一级立法

**机构**：欧盟官方公报（EUR-Lex）　**可信度**：100/100　**条目**：50　
**内容**：电池与废电池法规 (EU) 2023/1542 及关联立法

#### 欧盟官方公报（EUR-Lex）（42 条）

- **EU legislation CELEX 32023R1542R(14)**
  - 日期 2026-07-28　原文：http://publications.europa.eu/resource/cellar/ab3cbe7e-8a1f-11f1-8e61-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(14)**
  - 日期 2026-07-28　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542R(14)
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(13)**
  - 日期 2026-04-10　原文：http://publications.europa.eu/resource/cellar/0247a0f6-3476-11f1-be39-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **Corrigendum to Regulation (EU) 2023/1542 of the European Parliament and of the Council of 12 July 2023 concerning batteries and wa**
  - 日期 2026-04-10　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542R(13)
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(12)**
  - 日期 2026-02-17　原文：http://publications.europa.eu/resource/cellar/3f4e448f-0ba1-11f1-8870-01aa75ed71a1
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32023R1542R(12)**
  - 日期 2026-02-17　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542R(12)
  - 全文快照：`sources/eurlex-fulltext/32023R1542.txt`（352,016 字符）
- **EU legislation CELEX 32024R1252R(05)**　`待复核、黑粉线 ④`
  - 日期 2026-02-11　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252R(05)
  - 全文快照：`sources/eurlex-fulltext/32024R1252.txt`（221,942 字符）
- **EU legislation CELEX 32024R1157R(05)**　`待复核、黑粉线 ①`
  - 日期 2025-12-12　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157R(05)
  - 全文快照：`sources/eurlex-fulltext/32024R1157.txt`（303,332 字符）
- **EU legislation CELEX 32024R1157R(04)**　`待复核、黑粉线 ①`
  - 日期 2025-12-11　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157R(04)
  - 全文快照：`sources/eurlex-fulltext/32024R1157.txt`（303,332 字符）
- **EU legislation CELEX 32024R1252R(04)**　`待复核、黑粉线 ④`
  - 日期 2025-11-14　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252R(04)
  - 全文快照：`sources/eurlex-fulltext/32024R1252.txt`（221,942 字符）
  - …另有 32 条（共 42 条，见 `outputs/eol_*.jsonl`）

#### 欧盟官方公报（EUR-Lex 关键词检索）（8 条）

- **Regulation (EU) 2026/1738 of the European Parliament and of the Council of 8 July 2026 on circularity requirements for vehicle des**
  - 日期 2026-07-08　原文：http://publications.europa.eu/resource/cellar/394bc298-86fd-11f1-bf5e-01aa75ed71a1
- **Regulation (EU) 2026/1738 of the European Parliament and of the Council of 8 July 2026 on circularity requirements for vehicle des**
  - 日期 2026-07-08　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1738
- **Commission Implementing Regulation (EU) 2026/1116 of 26 May 2026 listing the products, components and waste streams considered as **　`待复核、黑粉线 ④`
  - 日期 2026-05-26　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1116
- **Commission Implementing Regulation (EU) 2025/2289 of 13 November 2025 laying down rules for the application of Regulation (EU) 202**
  - 日期 2025-11-13　原文：http://publications.europa.eu/resource/cellar/93e152fa-c67b-11f0-8da2-01aa75ed71a1
- **Commission Implementing Regulation (EU) 2025/2289 of 13 November 2025 laying down rules for the application of Regulation (EU) 202**
  - 日期 2025-11-13　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025R2289
- **Regulation (EU) 2025/1561 of the European Parliament and of the Council of 18 July 2025 amending Regulation (EU) 2023/1542 as rega**
  - 日期 2025-07-18　原文：http://publications.europa.eu/resource/cellar/fe1163e4-6cdd-11f0-bf4e-01aa75ed71a1
- **Commission Delegated Regulation (EU) 2025/606 of 21 March 2025 supplementing Regulation (EU) 2023/1542 of the European Parliament **
  - 日期 2025-03-21　原文：http://publications.europa.eu/resource/cellar/5881a55e-5873-11f0-a9d0-01aa75ed71a1
- **Commission Delegated Regulation (EU) 2025/606 of 21 March 2025 supplementing Regulation (EU) 2023/1542 of the European Parliament **
  - 日期 2025-03-21　原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025R0606

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
- **EU-BATTERIES_REGULATION-ANX_I_VI_ART_13_5 - ECHA**　`黑粉线 ④`
  - 原文：https://echa.europa.eu/eu-batteries_regulation-anx_i_vi_art_13_5?p_p_id=eucleflegislationlist_WAR_euclefportlet&p_p_lifecycle=0

### 成员国法

**机构**：德国联邦法律门户（官方 XML）　**可信度**：100/100　**条目**：28　
**内容**：AltfahrzeugV 报废车法 / BattDG 电池法 / AVV 废物目录

#### 德国联邦法律门户（官方 XML）（4 条）

- **Verordnung über Anforderungen an die Behandlung von Elektro- und Elektronik-Altgeräten* [eag-behandv]**
  - 原文：https://www.gesetze-im-internet.de/eag-behandv/
- **Verordnung über die Überlassung, Rücknahme und umweltverträgliche Entsorgung von Altfahrzeugen [altautov]**
  - 原文：https://www.gesetze-im-internet.de/altautov/
- **Gesetz zur Durchführung der Verordnung (EU) 2023/1542 betreffend Batterien und Altbatterien [battdg]**
  - 原文：https://www.gesetze-im-internet.de/battdg/
- **Verordnung über das Europäische Abfallverzeichnis [avv]**　`黑粉线 ③`
  - 原文：https://www.gesetze-im-internet.de/avv/

#### 荷兰 KOOP BWB 基础法规库（官方 XML）（17 条）

- **Besluit stortplaatsen en stortverboden afvalstoffen [BWBR0009094] 2026-01-01**
  - 日期 2026-01-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0009094/2026-01-01_0/xml/BWBR0009094_2026-01-01_0.xml
- **Besluit melden bedrijfsafvalstoffen en gevaarlijke afvalstoffen [BWBR0017294] 2025-07-01**
  - 日期 2025-07-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0017294/2025-07-01_0/xml/BWBR0017294_2025-07-01_0.xml
- **Besluit inzamelen afvalstoffen [BWBR0016530] 2024-01-01**
  - 日期 2024-01-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0016530/2024-01-01_0/xml/BWBR0016530_2024-01-01_0.xml
- **Besluit beheer autowrakken [BWBR0013707] 2024-01-01**
  - 日期 2024-01-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0013707/2024-01-01_0/xml/BWBR0013707_2024-01-01_0.xml
- **Regeling beheer batterijen en accu’s 2008 [BWBR0024492] 2024-01-01**
  - 日期 2024-01-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0024492/2024-01-01_0/xml/BWBR0024492_2024-01-01_0.xml
- **Verzamelbesluit wijziging bestaande UPV’s [BWBR0048234] 2023-07-01**
  - 日期 2023-07-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0048234/2023-07-01_0/xml/BWBR0048234_2023-07-01_0.xml
- **Regeling meldingsformulier batterijen en accu’s [BWBR0024500] 2023-07-01**
  - 日期 2023-07-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0024500/2023-07-01_0/xml/BWBR0024500_2023-07-01_0.xml
- **Besluit beheer batterijen en accu’s 2008 [BWBR0024491] 2023-01-01**
  - 日期 2023-01-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0024491/2023-01-01_0/xml/BWBR0024491_2023-01-01_0.xml
- **Wijzigingsbesluit Besluit beheer autobanden, enz. (aanpassing van de meldings- en mededelingstermijn (onbeperkte geldigheid meldin**
  - 日期 2008-04-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0023036/2008-04-01_0/xml/BWBR0023036_2008-04-01_0.xml
- **Besluit beheer batterijen [BWBR0007227] 2008-04-01**
  - 日期 2008-04-01　原文：https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0007227/2008-04-01_0/xml/BWBR0007227_2008-04-01_0.xml
  - …另有 7 条（共 17 条，见 `outputs/eol_*.jsonl`）

#### 西班牙官方公报 BOE（立法整合库 REST API）（7 条）

- **Orden INT/1920/2011, de 1 de julio, por la que se refuerza el control respecto al comercio del cobre para los centros gestores de **
  - 日期 2011-07-12　原文：https://www.boe.es/buscar/act.php?id=BOE-A-2011-11947
- **Real Decreto 1619/2005, de 30 de diciembre, sobre la gestión de neumáticos fuera de uso. [BOE-A-2006-41]**
  - 日期 2006-01-03　原文：https://www.boe.es/buscar/act.php?id=BOE-A-2006-41
- **Real Decreto 1093/2024 —— 废物管理 [BOE-A-2024-21709]**　`待复核`
  - 原文：https://www.boe.es/buscar/act.php?id=BOE-A-2024-21709
- **Real Decreto 846/2011 —— 报废车辆（VFU）处理设施的条件 [BOE-A-2011-11827]**
  - 原文：https://www.boe.es/buscar/act.php?id=BOE-A-2011-11827
- **Real Decreto 106/2008 —— 电池与蓄电池及其废物的环境管理（西班牙实施欧盟电池指令的国内法） [BOE-A-2008-2387]**
  - 原文：https://www.boe.es/buscar/act.php?id=BOE-A-2008-2387
- **Real Decreto 993/2022 —— 电池相关的控制措施 [BOE-A-2022-19914]**
  - 原文：https://www.boe.es/buscar/act.php?id=BOE-A-2022-19914
- **Ley 7/2022 —— 废物与污染土壤（循环经济）国家基础法 [BOE-A-2022-5809]**
  - 原文：https://www.boe.es/buscar/act.php?id=BOE-A-2022-5809

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
- **REP - VHU - TRR et TRV des CVHU depuis 2018**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-trr-et-trv-des-cvhu-en-2018
- **REP - VHU - Performances cumulées depuis 2018**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-performances-cumulees-en-2018
- **REP - VHU - Liste des producteurs enregistrés à SYDEREP**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-liste-des-societes-inscrites-a-syderep
- **Page non trouvée**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-tonnages-collectes-cvhu-depuis-2018
- **Page non trouvée**
  - 原文：https://data.ademe.fr/datasets/rep-vhu-tonnages-collectes-broyeurs-depuis-2018
  - …另有 2 条（共 12 条，见 `outputs/eol_*.jsonl`）

#### Stichting OPEN（电池/电子生产者责任组织）（7 条）

- **Stichting OPEN - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/
- **Producenten & importeurs - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/producenten-importeurs/
- **Inzamelpartners, zoals gemeenten, retailers en metaalrecyclers - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/inzamelpartners-retailers/
- **Onze kerntaken - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/onze-organisatie/onzekerntaken/
- **Stichting OPEN draagt met recordinzameling elektrisch afval bij aan grondstoffenzekerheid - Stichting OPEN**　`待复核`
  - 原文：https://www.stichting-open.org/2026/05/26/stichting-open-draagt-met-recordinzameling-elektrisch-afval-bij-aan-grondstoffenzekerheid/
- **Peperzeel opent nieuwe sorteerlijn voor batterijen - Stichting OPEN**
  - 原文：https://www.stichting-open.org/2026/07/15/peperzeel-opent-nieuwe-sorteerlijn-voor-batterijen/
- **Humberto Tan verzorgt aftrap landelijke inlevercampagne batterijen ‘Doe maar apart’ - Stichting OPEN**
  - 原文：https://www.stichting-open.org/2026/06/16/humberto-tan-verzorgt-aftrap-landelijke-inlevercampagne-batterijen-doe-maar-apart/

### 美国联邦

**机构**：美国联邦公报（Federal Register）　**可信度**：100/100　**条目**：244　
**内容**：DOE / EPA / IRS / DOT 的法规、通知与征询

#### 美国联邦公报（Federal Register）（236 条）

- **Securing the United States Bulk-Power System**　`待复核`
  - 日期 2026-09-09　原文：https://www.federalregister.gov/documents/2026/09/09/2026-18370/securing-the-united-states-bulk-power-system
- **Superfund Tax on Chemical Substances; Request To Modify List of Taxable Substances; Notice of Filing for Butadiene-acrylonitrile-m**　`待复核`
  - 日期 2026-09-09　原文：https://www.federalregister.gov/documents/2026/09/09/2026-18264/superfund-tax-on-chemical-substances-request-to-modify-list-of-taxable-substances-notice-of-filing
- **Repeal of Fossil Fuel Restrictions for New Federal Buildings and Major Renovations of Federal Buildings**　`待复核`
  - 日期 2026-09-02　原文：https://www.federalregister.gov/documents/2026/09/02/2026-17979/repeal-of-fossil-fuel-restrictions-for-new-federal-buildings-and-major-renovations-of-federal
- **Rescission of Production Incentives for Cellulosic Biofuels**　`待复核`
  - 日期 2026-09-01　原文：https://www.federalregister.gov/documents/2026/09/01/2026-17872/rescission-of-production-incentives-for-cellulosic-biofuels
- **Foreign-Trade Zone (FTZ) 126, Notification of Proposed Production Activity; Panasonic Energy Corporation of North America; (Lithiu**　`待复核`
  - 日期 2026-08-26　原文：https://www.federalregister.gov/documents/2026/08/26/2026-17358/foreign-trade-zone-ftz-126-notification-of-proposed-production-activity-panasonic-energy-corporation
- **Agency Information Collection Activities; Submission to the Office of Management and Budget (OMB) for Review and Approval; Comment**　`待复核`
  - 日期 2026-08-25　原文：https://www.federalregister.gov/documents/2026/08/25/2026-17323/agency-information-collection-activities-submission-to-the-office-of-management-and-budget-omb-for
- **Nominations Request for the Good Neighbor Environmental Board**　`待复核`
  - 日期 2026-08-20　原文：https://www.federalregister.gov/documents/2026/08/20/2026-16931/nominations-request-for-the-good-neighbor-environmental-board
- **Secretary of Energy Advisory Board**　`待复核`
  - 日期 2026-08-18　原文：https://www.federalregister.gov/documents/2026/08/18/2026-16801/secretary-of-energy-advisory-board
- **Notice of Intent To Prepare an Environmental Impact Statement for the Proposed Issuance of an Exploration License to The Metals Co**　`待复核`
  - 日期 2026-08-17　原文：https://www.federalregister.gov/documents/2026/08/17/2026-16722/notice-of-intent-to-prepare-an-environmental-impact-statement-for-the-proposed-issuance-of-an
- **Agency Information Collection Activities; Comment Request on U.S. Trust and Estate Income Tax Returns and Related Forms, Schedules**　`待复核`
  - 日期 2026-08-10　原文：https://www.federalregister.gov/documents/2026/08/10/2026-16243/agency-information-collection-activities-comment-request-on-us-trust-and-estate-income-tax-returns
  - …另有 226 条（共 236 条，见 `outputs/eol_*.jsonl`）

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
- **Used Household Batteries | US EPA**
  - 原文：https://www.epa.gov/recycle/used-household-batteries
- **Safety Advisory Notice for the Transportation of Lithium Batteries for Disposal or Recycling | PHMSA**
  - 日期 May 17, 20　原文：https://www.phmsa.dot.gov/training/hazmat/safety-advisory-notice-transportation-lithium-batteries-disposal-or-recycling
- **Green Job Hazards - Recycling: Batteries | Occupational Safety and Health Administration**
  - 原文：https://www.osha.gov/green-jobs/recycling/batteries

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
- **New Study Confirms Lead Batteries Are America's Most Recycled Consumer Product, With a 98% Recycling Rate**
  - 原文：https://batterycouncil.org/news/responsible-lead-battery-recycling-growth-through-continuous-improvement/
- **New Study Confirms Lead Batteries Are America's Most Recycled Consumer Product, With a 98% Recycling Rate**
  - 原文：https://batterycouncil.org/news/new-study-confirms-lead-batteries-are-americas-most-recycled-consumer-product-with-a-98-recycling-rate/
- **Lead Battery Recycling | Battery Council International**
  - 原文：https://batterycouncil.org/battery-facts-and-applications/battery-recycling/

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

## 五、法规变更时间线

> **「什么时候改了什么」比「现在是什么」更有情报价值。**
> 频繁的更正意味着条文尚不稳定、执行口径仍在变 —— 这本身就是要监测的信号。

### Regulation (EU) 2023/1542 of the European Parliament and of the Council of 12 July 2023 concerni

主体 CELEX `32023R1542`　共 30 个版本（更正 28 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 1001-01-01 | 本体 | `32023R1542` |
| 1001-01-01 | 本体 | `32023R1542` |
| 2023-08-03 | 更正 | `32023R1542R(01)` |
| 2023-08-03 | 更正 | `32023R1542R(01)` |
| 2023-11-15 | 更正 | `32023R1542R(02)` |
| 2023-11-15 | 更正 | `32023R1542R(02)` |
| 2023-12-22 | 更正 | `32023R1542R(03)` |
| 2023-12-22 | 更正 | `32023R1542R(03)` |
| 2024-03-12 | 更正 | `32023R1542R(04)` |
| 2024-03-12 | 更正 | `32023R1542R(04)` |
| 2024-04-17 | 更正 | `32023R1542R(05)` |
| 2024-04-17 | 更正 | `32023R1542R(05)` |
| 2024-04-23 | 更正 | `32023R1542R(06)` |
| 2024-04-23 | 更正 | `32023R1542R(06)` |
| … | 另有 16 个版本 | |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542

### Regulation (EU) 2024/1157 of the European Parliament and of the Council of 11 April 2024 on ship

主体 CELEX `32024R1157`　共 12 个版本（更正 10 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2020-08-20 | 本体 | `32024R1157` |
| 2020-08-20 | 本体 | `32024R1157` |
| 2024-09-20 | 更正 | `32024R1157R(01)` |
| 2024-09-20 | 更正 | `32024R1157R(01)` |
| 2024-12-09 | 更正 | `32024R1157R(02)` |
| 2024-12-09 | 更正 | `32024R1157R(02)` |
| 2025-01-21 | 更正 | `32024R1157R(03)` |
| 2025-01-21 | 更正 | `32024R1157R(03)` |
| 2025-12-11 | 更正 | `32024R1157R(04)` |
| 2025-12-11 | 更正 | `32024R1157R(04)` |
| 2025-12-12 | 更正 | `32024R1157R(05)` |
| 2025-12-12 | 更正 | `32024R1157R(05)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1157

### Regulation (EU) 2024/1252 of the European Parliament and of the Council of 11 April 2024 establi

主体 CELEX `32024R1252`　共 12 个版本（更正 10 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2024-05-23 | 本体 | `32024R1252` |
| 2024-05-23 | 本体 | `32024R1252` |
| 2024-06-03 | 更正 | `32024R1252R(01)` |
| 2024-06-03 | 更正 | `32024R1252R(01)` |
| 2024-10-01 | 更正 | `32024R1252R(02)` |
| 2024-10-01 | 更正 | `32024R1252R(02)` |
| 2025-02-14 | 更正 | `32024R1252R(03)` |
| 2025-02-14 | 更正 | `32024R1252R(03)` |
| 2025-11-14 | 更正 | `32024R1252R(04)` |
| 2025-11-14 | 更正 | `32024R1252R(04)` |
| 2026-02-11 | 更正 | `32024R1252R(05)` |
| 2026-02-11 | 更正 | `32024R1252R(05)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1252

### EU legislation CELEX 32000L0053

主体 CELEX `32000L0053`　共 8 个版本（更正 6 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2000-10-21 | 本体 | `32000L0053` |
| 2000-10-21 | 本体 | `32000L0053` |
| 2015-04-11 | 更正 | `32000L0053R(01)` |
| 2015-04-11 | 更正 | `32000L0053R(01)` |
| 2016-06-11 | 更正 | `32000L0053R(02)` |
| 2016-06-11 | 更正 | `32000L0053R(02)` |
| 2019-02-01 | 更正 | `32000L0053R(03)` |
| 2019-02-01 | 更正 | `32000L0053R(03)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32000L0053

### EU legislation CELEX 32006L0066

主体 CELEX `32006L0066`　共 5 个版本（更正 4 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2006-09-26 | 本体 | `32006L0066` |
| 2006-11-10 | 更正 | `32006L0066R(01)` |
| 2006-12-06 | 更正 | `32006L0066R(02)` |
| 2007-05-31 | 更正 | `32006L0066R(03)` |
| 2007-05-31 | 更正 | `32006L0066R(04)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006L0066

### Directive (EU) 2025/1892 of the European Parliament and of the Council of 10 September 2025 amen

主体 CELEX `32025L1892`　共 3 个版本（更正 2 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2025-10-16 | 本体 | `32025L1892` |
| 2026-05-21 | 更正 | `32025L1892R(01)` |
| 2026-06-25 | 更正 | `32025L1892R(02)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025L1892

### Commission Implementing Regulation (EU) 2024/1866 of 3 July 2024 imposing a provisional counterv

主体 CELEX `32024R1866`　共 2 个版本（更正 1 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2024-07-03 | 本体 | `32024R1866` |
| 2024-07-30 | 更正 | `32024R1866R(01)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1866

### Commission Delegated Decision (EU) 2025/934 of 5 March 2025 amending Decision 2000/532/EC as reg

主体 CELEX `32025D0934`　共 2 个版本（更正 1 次）

| 日期 | 版本 | CELEX |
|---|---|---|
| 2025-03-05 | 本体 | `32025D0934` |
| 2025-08-19 | 更正 | `32025D0934R(01)` |

- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0934

---

## 六、企业情报（与政策分开看）

> 企业侧信息（产能、投融资、并购）对竞对分析的价值**独立于政策**。
> 混在政策清单里，要翻几百条公报才能找到一条「某回收商新开分选线」。

| 类型 | 标题 | 原文 |
|---|---|---|
| 合作 | Battery Policy & Initiatives / Battery Council International | https://batterycouncil.org/policy-initiatives/ |
| 产能指标、扩产 | New Study Confirms Lead Batteries Are America's Most Recycled Consumer Product, With | https://batterycouncil.org/news/responsible-lead-battery-recycling-growth-through-continuous-improvement/ |
| 产能扩张 | Peperzeel opent nieuwe sorteerlijn voor batterijen - Stichting OPEN | https://www.stichting-open.org/2026/07/15/peperzeel-opent-nieuwe-sorteerlijn-voor-batterijen/ |
| 投融资 | Onze kerntaken - Stichting OPEN | https://www.stichting-open.org/onze-organisatie/onzekerntaken/ |
| 合作 | Product Stewardship and Extended Producer Responsibility (EPR) - CalRecycle Home Pag | https://calrecycle.ca.gov/epr/ |

> 共 5 条含企业动态信号；识别规则见 `COMPANY_SIGNALS`（可按需扩充）

---

## 七、其他已下载的原始文档

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

## 八、数据源健康度

| 源 | 层级 | 机构 | 相关条目 |
|---|---|---|---:|
| `us_federal_register` | 美国联邦 | 美国联邦公报（Federal Register） | 236 |
| `eu_eurlex_battery_reg` | EU 一级立法 | 欧盟官方公报（EUR-Lex） | 42 |
| `nl_bwb` | 成员国法 | 荷兰 KOOP BWB 基础法规库（官方 XML） | 17 |
| `browser_france` | 成员国数据 | ADEME 开放数据门户 | 12 |
| `eu_eurlex_keyword` | EU 一级立法 | 欧盟官方公报（EUR-Lex 关键词检索） | 8 |
| `browser_bci` | 美国行业 | Battery Council International（铅电池协会） | 8 |
| `browser_phmsa` | 美国联邦 | DOT 管道与危险材料安全管理局（PHMSA） | 8 |
| `browser_netherlands` | 成员国数据 | Stichting OPEN（电池/电子生产者责任组织） | 7 |
| `es_boe` | 成员国法 | 西班牙官方公报 BOE（立法整合库 REST API） | 7 |
| `browser_echa` | EU 机构文件 | 欧洲化学品管理局（ECHA） | 6 |
| `de_gesetze` | 成员国法 | 德国联邦法律门户（官方 XML） | 4 |
| `browser_calrecycle` | 美国州级 | CalRecycle | 3 |

> 命中率口径说明：不同通道的采集方式不同（API 精准查询 vs 全文检索），
> 跨通道比较命中率没有意义，故此处不列。同类通道内的命中率见 `outputs/eol_summary_*.md`。

---

## 九、已知覆盖缺口（截至本次更新）

| 缺口 | 状态 | 说明 |
|---|---|---|
| 法国法规正文 | ✅ 已闭环 | DILA 开放数据（日增量 0.9~1.8MB）已接入；另 JORF 数据集打通——**新法规发布**与**法规被修订**是两个不同信号，分别由 JORF 与 LEGI 承载 |
| 荷兰法规正文 | ✅ 已闭环 | KOOP BWB 官方 XML 已接入（见第十章）；《报废车辆管理令》20,790 字符，含 22 个历史版本 |
| 西班牙法规正文 | ✅ 已闭环 | BOE 官方 REST API 已接入（见第十章） |
| 意大利法规正文 | ❌ 未接 | `normattiva.it` 可达但为 JS 门户；无公开结构化 API |
| 其他成员国（波/比/奥/丹…） | ❌ 未接 | 入口清单已备（N-Lex 27 国，见第十章），逐个接入即可 |
| 美国州级立法 | ⚠️ 部分 | 仅加州 CalRecycle；华盛顿/缅因等州的电池 EPR 法案未覆盖 |
| 国际公约 | ❌ 未接 | 巴塞尔公约站点直连返回**同一个壳页**（连 PDF 路径都返回首页 125,948 字节），需走浏览器通道 |
| 行业数据库 | ⚠️ 成本 | Fastmarkets / Benchmark 等付费源未接入 |
| 回收企业 | ⚠️ 偏薄 | 企业侧仍是最薄一层；欧洲主要回收商（Umicore / Accurec / Duesenfeld）未系统覆盖 |

> 成员国源的选择方法（重要）：**看有没有专业机构或结构化 API，而不是看有没有开放数据门户。**
> 实测通用国家门户（govdata.de / dane.gov.pl）的全文搜索是**单字 OR 匹配**，搜"报废车"会返回"职业介绍所登记册"，垂直检索不可用。
> 反例是德国 `gesetze-im-internet` 与荷兰 `KOOP BWB`、西班牙 `BOE`：都是**本国官方法规库的官方接口**，不是开放数据门户，一次接通整层可用。

---

## 十、缺口攻坚记录

> 本章记录每个缺口**具体怎么试的、结论是什么、证据是什么**。
> 失败项同样保留——本章里过半的"旧结论"后来被证明是错的。

### 10.1 本轮关闭的缺口

| 缺口 | 关键突破 | 证据 |
|---|---|---|
| 荷兰法规正文 | **SRU 参数名与索引名反直觉**：连接名必须是 `BWB`；版本参数是 `version`（不是 `x-version`）；索引名不能猜，要问 `operation=explain` | 该接口返回 14 个索引、库容 **148,242 条** |
| 荷兰正文取法 | **作品级 XML 不含法条**：`/bwb/{ID}` 是 `<work>` WTI 元数据（6,090 字符，`autowrak` 出现 **0 次**）；必须用 `locatie_toestand` 版本级 XML（20,191 字符，`autowrak` **26 次**） | 两种取法实测对比 |
| 法国新法规发布 | DILA `JORF/` 目录打通；由**瞬时失败**误判为不可用 | 重试后 200 / 133,698 B，共 **781 个增量包，每天两批** |
| 西班牙法规正文 | **严格内容协商**：不带 `Accept: application/xml` 一律 400（不是反爬） | 带对头后 200；全量目录 **12,395 部**，单部法正文 2 万~64 万字符 |
| 成员国入口全景 | **N-Lex 是 27 国国家法规库的官方目录** | `/n-lex/legis_{cc}/…_form` 共 **27 个**入口 |

### 10.2 旧结论被推翻（本轮的反复）

| 旧结论 | 实际情况 | 教训 |
|---|---|---|
| 荷兰"需 BWB 编号才行" | 编号有现成检索 API，只是参数名差一个 `x-` | **参数名猜不得**，先找 `explain` 一类的自描述入口 |
| 法国 DILA "不好用" | 用户级误判来自拿"全量 1.17GB"评估；**监测要的是日增量（0.9~1.8MB）** | 用错粒度评估一个源，会把它判死 |
| 巴塞尔公约"可达" | 三个不同 URL 返回**字节数完全一致**（125,948），连 PDF 路径都返回首页 | **HTTP 200 ≠ 拿到内容**；要比较响应指纹 |
| 西班牙"有开放数据门户" | BOE 有完整 REST API（19 个端点），但**网页检索结果不在 HTML 里** | 门户 ≠ API；先找 API 帮助页 |

### 10.3 本轮新发现的操作陷阱

| 陷阱 | 表现 | 处置 |
|---|---|---|
| 索引做**精确词匹配** | 荷兰 `titel=autowrak` → **0 条**，`titel=autowrakken` → **44 条** | 荷兰语/德语复合词必须逐词形检索 |
| 目录**顺序任意**，局部扫描碰不到目标 | BOE 前 2,000 部里电池专法命中 **0**（而语料共 10k~15k 部） | 建目录要**建全**，不能扫一段就下结论 |
| **不能猜编号** | 猜的 BOE 编号全 404（真值 `BOE-A-2008-2387`，猜的是 `-2981`）；德国 `AltfahrzeugV` 的真实 slug 是 `altautov` | 先拿目录/清单，再取记录 |
| 单部法规可达 20~48 万字符 | 若沿用"摘要即内容"会把关键条文截断 | 正文入库前**不做摘要截断** |
| 关键词**分级**不能一视同仁 | 西班牙只用 `residuos?` 会把自治区通用废物法（25~48 万字符/部）全部捞进来 | 专有词 / 中等 / 通用 三级打分 |
| 失败 **≠** 源不可用 | DILA 首次请求返回空（curl code 0），重试即 200 | 瞬时失败必须重试后再下结论 |
| 索引的"失效标记"**不可靠** | 西班牙 RD 846/2011 与 RD 1619/2005 在索引里 `vigencia_agotada=N`（未失效），但**正文第一行写着 `Norma derogada`（已废止）** | 不能信索引标志，要**读正文抬头**；且**废止本身是情报**——说明监管已转移 |

### 10.3.1 本轮入库的成员国核心法规

| 国 | 编号 | 法规 | 正文体量 |
|---|---|---|---:|
| 🇩🇪 | `altautov` | AltfahrzeugV 报废车法（转化 ELV 指令 2000/53/EC） | 54,439 字符 |
| 🇩🇪 | `battdg` | BattDG 电池法（实施 EU 2023/1542） | 127,617 字符 |
| 🇩🇪 | `avv` | AVV 欧洲废物目录（危废分类 → 黑粉定性） | 77,588 字符 |
| 🇳🇱 | `BWBR0013707` | Besluit beheer autowrakken 报废车辆管理令 | 20,790 字符 / 22 版本 |
| 🇳🇱 | `BWBR0014293` | Regeling beheer autowrakken 报废车管理条例 | 7,125 字符 / 10 版本 |
| 🇳🇱 | `BWBR0048234` | UPV 生产者延伸责任修订令（含电池） | 2,976 字符 |
| 🇪🇸 | `BOE-A-2008-2387` | RD 106/2008 电池与蓄电池废物环境管理 ★ | 202,213 字符 |
| 🇪🇸 | `BOE-A-2022-5809` | Ley 7/2022 废物与污染土壤国家基础法 ★ | 641,728 字符 |
| 🇪🇸 | `BOE-A-2022-19914` | RD 993/2022 电池相关控制措施 | 46,687 字符 |
| 🇪🇸 | `BOE-A-2024-21709` | RD 1093/2024 废物管理 | 117,827 字符 |
| 🇪🇸 | `BOE-A-2011-11827` | RD 846/2011 报废车（VFU）处理设施条件 ⚠️已废止 | 16,871 字符 |
| 🇫🇷 | DILA `LEGI` | 法律/法令日增量（法规被修订） | 日增 0.9~1.8 MB |
| 🇫🇷 | DILA `JORF` | 官方公报日增量（新法规发布） | 每天 2 批 |

> ★ = 该层核心法规；⚠️ = 已废止（保留但标记，因为废止本身说明监管转移）

### 10.3.2 ⭐ 同一类缺陷在本轮出现了三次：**记录存在，但内容为空**

| # | 位置 | 现象 | 后果 |
|---|---|---|---|
| 1 | 荷兰 BWB | `/bwb/{ID}` 返回 `<work>` WTI 元数据（6,090 字符，`autowrak` 出现 **0 次**） | 记录"采集成功"但一个字法条都没有 |
| 2 | EUR-Lex `Q_CELEX` | 早期漏 select `expression_title`，raw_text 里只有占位符 `EU legislation CELEX 32024R1157` | 黑粉①线《废物运输条例》被相关性判定丢弃——**不是规则错，是没内容可判** |
| 3 | EUR-Lex 元数据 | 正文早已落盘 `sources/eurlex-fulltext/32000L0053.txt`，但 jsonl 里那条记录只有 CELEX 号 | **报废车指令 2000/53/EC（ELV 主干法）被判为不相关** |

**这三个的共性**：采集层、存储层、判定层各自看起来都正常，
坏在"交出去的东西是空的"。没有报错、没有丢数据、指标也正常，
只是整条内容在判定那一刻等于不存在。

**修复后的实测影响**（`py scripts/measure_fulltext_fix.py`）：

```
欧盟 CELEX 记录（去重）   37
  · 原本已相关           18
  · 翻转（此前被静默丢弃） 15   ← 占 40%
  · 仍不相关              4
```

翻转回来的包括：

| CELEX | 法规 | 黑粉线 |
|---|---|---|
| `32000L0053` | **报废车指令 2000/53/EC**（ELV 主干法） | — |
| `32024R1157` + 5 个更正 | 废物运输条例 | ①废物跨境转移 |
| `32024R1252` + 5 个更正 | 关键原材料法 | ④战略价值认定 |
| `52023PC0451` | 报废车条例提案（取代指令） | ① + ④ |

**对策（已落地）**：
1. 连接器里加**根标签/内容形态防护**——BWB 取到 `<work>` 直接报错，不允许静默入库；
2. 判定前**并入已落盘的正文快照**（`EurLexConnector._with_fulltext`）；
3. 新增回归测试 `tests/test_member_state_patterns.py`，用真实法规原文锁住"成员国层必须能过判定"这个不变量；
4. **英语 ELV 词族补齐**——本轮发现英语模式里只有 battery 侧的词、**没有 vehicle 侧**：`end-of-life vehicle` / `2000/53/EC` / `certificate of destruction` / `dismantlers` / `shredder light fraction` 一个都没有。ELV 指令此前只是靠着法语模式里的 `depollution` 才勉强命中——**一个偶然**。

### 10.4 欧美覆盖面的本轮扩充（优先欧美政策法规采集）

#### 🇪🇺 欧盟：从精确跟踪 5 部法 → 46 部法案

**问题**：核心法（电池法 / ELV 指令）只是**框架**。真正落地义务的是它们的
**授权法案与实施法案**——碳足迹计算方法、再生料含量核算、尽职调查、
电池护照、回收效率……这些一部都没被跟踪。
结果是「知道有法规，不知道具体要做什么」。

**方法**：这类法案的标题里**必然写明**所依据的基础法号
（如 `Commission Delegated Regulation (EU) 2025/606 supplementing
Regulation (EU) 2023/1542`），所以按**标题锚点**检索最稳。锚点：
`2023/1542` · `2000/53/EC` · `2024/1157` · `2024/1252` · `2006/66/EC` · `2008/98/EC`

```
候选 96 个  →  筛选后固化 43 个（29 立法 + 14 提案）
剔除 44 个程序性文件：SC 员工工作报告 21 · AP 议会决议 9 ·
                       DC 报告 6 · AE 意见 5 · AG 理事会立场 2 · XC 1
```

**发现的高价值法案**（`sources/eu-acts-tracked.yaml`）：

| CELEX | 内容 | 对本专题的意义 |
|---|---|---|
| `32024R1781` | 生态设计法规 ESPR | 数字产品护照的母法（电池护照的上位依据） |
| `32026R1738` | 2026-07-08 新条例 | 同时出现在电池法与 ELV 两个锚点下 |
| `32024R2571` | 授权条例补充 2024/1157 | 黑粉跨境运输的**实施细则** |
| `32024R3230` | 授权条例修订 2024/1157 | 同上 |
| `32025R1290` | 实施条例（废物运输） | 同上 |
| `32026D0681` | 委托 OLAF 欧洲反欺诈办公室 | 废物运输的**执法**安排 |
| `32025D0840` / `32025D1174` | 委员会决定：承认某些关键原材料 | 直接决定黑粉的**战略价值认定** |
| `32025R2194` | 实施条例（关键原材料） | 单一机制 |
| `32020L0362` / `32020L0363` / `32023L0544` | 授权指令修订 ELV 附件 II | 报废车**拆解与去污**的具体要求 |
| `52025PC0501` / `52025PC0258` | 修订电池法的提案 | 立法前预警信号 |
| `32018L0849` / `32018L0851` | 修订 ELV 指令 / 废物框架指令 | 上轮循环经济一揽子 |

⚠️ **查询形状的坑（代价约 20 分钟）**：我在这条查询上「顺手改进」了三处——
加 `FILTER(LANG(?title)="en")`、把日期/类型改成 `OPTIONAL`、`DISTINCT` 多投影一个变量。
结果查询**直接超时**（curl 60s / 150s 均无响应），而端点本身 1 秒就答。
回退成与已验证可用的 `Q_KEYWORD` **完全同形**后，21 秒返回。
→ **在慢查询引擎上，不要把工作版本的形状顺手改好。**

#### 🇺🇸 美国：机构 4 → 15 个，关键词 20 → 27 个，配对 30 → 37 组

**机构 slug 全部取自联邦公报自己的官方机构表**
（`GET /api/v1/agencies.json`，472 个机构含子机构）。

> ⚠️ slug 猜错**不会报错，只会静默返回 0 条**。所以每个都要用常见词做对照验证：
> `py scripts/verify_fr_agencies.py`（实测剔除 `customs-service`、
> `council-on-environmental-quality`、`environment-office-energy-department`）。

**⭐ 一个被推翻的重要假设**：用「black mass」逐机构实测，命中分布是

```
industry-and-security-bureau   (BIS 出口管制)       2 条
state-department               (国务院 / 巴塞尔公约) 2 条
commerce-department            (商务部 / 关键矿产)   2 条
justice-department             (司法部 / 执法)       2 条
environmental-protection-agency / transportation-department / energy-department
                                                     0 条
```

> **黑粉在美国的真实监管不在 EPA / DOT / DOE，而在
> 出口管制 + 巴塞尔公约 + 关键矿产 + 执法 四条线上。**
> 原配置只查 EPA/DOE/DOT，**这四条全漏了**。

**扩充带来的噪声，以及它是什么**：机构与词表一扩，「待人工复核」从个位数冲到 **180 条**。
抽样发现绝大多数来自联邦公报的**批量行政文书**：

| 文书类型 | 条数 |
|---|---:|
| `Agency Information Collection Activities`（信息收集公告） | 64 |
| `Notice of Applications / Actions on Special Permits`（PHMSA 许可通告） | 23 |
| `... State Hazardous Waste Program`（州级 RCRA 授权） | 18 |
| `Foreign-Trade Zone (FTZ) ...`（对外贸易区通知） | 36 |

> ⚠️ 这与本项目早先踩过的坑是**同一类**：那时是「不要加 `shippers?`」——
> 每份危险货物文件都含 shipper，64 条命中里绝大多数是 Special Permits 通告。
> **现在换个词，又从一个新门进来了。**

**正解不是收窄关键词**（会漏真政策），而是**按文档类型过滤**：
新增 `BATCH_DOC_NOISE`（只看标题——这类文书标题是固定模板；
正文里出现相同短语可能是合法的政策引用，不能一概而论）。
效果：总 **510 → 450**，待人工复核 **180 → 140**。

> ❗ `foreign-trade zone` **刻意不列入**过滤表：FTZ 的生产活动通知
> （如 `FTZ 193; Authorization of Production Activity; Lithionics Battery`）
> 虽是行政文书，但它是**真实的产能信号**，应归企业情报而不是丢弃。

### 10.5 已备好、尚未接入的入口

**N-Lex 全成员国法规库入口（27 个，实测可达）**

```
at 奥地利  be 比利时  bg 保加利亚  cy 塞浦路斯  cz 捷克
de 德国    dk 丹麦    ee 爱沙尼亚  es 西班牙    fi 芬兰
fr 法国    gr 希腊    hr 克罗地亚  hu 匈牙利    ie 爱尔兰
it 意大利  lt 立陶宛  lu 卢森堡    lv 拉脱维亚  mt 马耳他
nl 荷兰    pl 波兰    pt 葡萄牙    ro 罗马尼亚  sk 斯洛伐克
sl 斯洛文尼亚  sv 瑞典
```

> 路径形如 `https://n-lex.europa.eu/n-lex/legis_{cc}/{库名}_form`，
> 另有 `/n-lex/aggregated-search` 可跨成员国聚合检索。
> 接入时**优先找该国官方库自己的 API**（德/荷/西三国的经验：都能直接拿结构化数据），
> 把 N-Lex 当作入口清单用，而不是当作数据源用。

**法国 DILA 其他数据集（40+）**

| 数据集 | 内容 |
|---|---|
| `LEGI` | 法律与法令整合库（法规被修订）✅ 已接 |
| `JORF` | 官方公报（新法规发布）✅ 已接 |
| `JADE` | 行政判例 |
| `CIRCULAIRES` | 部委通函（执法口径，实践中常先于法规变化） |
| `BODACC` | 商事与破产公告（← 企业侧：回收商并购/倒闭信号） |
| `KALI` / `CONSTIT` / `CAPP` … | 集体协议 / 宪法 / 等 |

> ⭐ 其中 `BODACC` 值得优先——它是**企业情报**目前最薄的那一层，
> 而破产/并购公告恰好是回收行业产能出清的直接信号。

---

_本报告由 `scripts/make_report.py` 生成，数据源为 `outputs/*.jsonl`。_
_重新生成：`py scripts/make_report.py`_
