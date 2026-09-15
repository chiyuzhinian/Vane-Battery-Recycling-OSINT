# PHASE 4B-2B · MODE B 批次 1 —— CZ/IT/HU/SK 通道化与 PLAN_V1 冻结

日期：2026-09-15 ｜ 分支：`phase4b2a`

## 一、结论
- **四辖区通道全部闭合**（MODE B 侦查 Round 1-9，全部实采验证）
- **4×PLAN_V1 冻结**：`CZ_PLAN_V1` / `IT_PLAN_V1` / `HU_PLAN_V1` / `SK_PLAN_V1`
- **端点注册**：+4 角色 / +12 端点（`source-endpoints.yaml`）
- **注册表**：+3 角色（CZ/IT/SK_NATIONAL_LEGISLATION，CONNECTED）+ HU 备注升级
- **测试 414 passed**；`config_status ok=True`；计划注册表 `errors=[]`

## 二、四通道（实测证据）
| 辖区 | 搜索通道 | 全文通道 | A 种子（实测存在） |
|---|---|---|---|
| **CZ** | `sbirka.sqw?r={年}` 年枚举（486 部/年） | `sbirka.sqw?cz={号}&r={年}`（84~229KB 静态） | 170/2010（电池专条）、383/2001、185/2001、541/2020、542/2020 |
| **IT** | `/ricerca/veloce/0?testoRicerca=`（142 命中/20 链接） | N2Ls URN（119KB/35KB/39KB） | D.Lgs. 188/2008（pile e accumulatori）等 ×6 |
| **HU** | `?content=` 真过滤（23/385 期命中）+ 年份/分页 | `letoltes` PDF → pypdf（130 页/139K 字符） | 2014/188-190、2023/194、2026/131 |
| **SK** | `static.slov-lex.sk` 年索引（分页） | `vyhlasene_znenie.html`（532K 字符）/ PDF（80~172 页） | 79/2015（废物法）、373/2015（batéri×90） |

## 三、攻防记录（为何 9 轮）
1. **SK**：原站全站 JS 壳（无 JS 时仅 614 字符文本）→ 静态镜像 `static.slov-lex.sk` 年索引→法案目录→全文 HTML/PDF 全通
2. **HU**：静态 `kereses?q=` 壳不过滤（乱码同结果）→ 从 `app.js`（637KB）挖出 `/api/v1/kozlonyok/*` 命名空间 → 定为 `?content=` 真参数 + `letoltes` PDF 实体
3. **IT**：`semplice` 表单为 JS 提交 → `veloce/0` 快速检索闭合 + `atto` 详情 + N2Ls 全文
4. **CZ**：e-Sbírka/MVČR 替代路径 404/JS → PSP `sbirka.sqw` 通道闭合（统计与全文双验证）
5. 本地连通抖动（ConnectError 多轮）按纪律记录为端点级瞬态，云 vantage（Batch 1R）与本地一致

## 四、产物清单
| 文件 | 说明 |
|---|---|
| `sources/search-plans/CZ_PLAN_V1.yaml` | hash `a79ce1e093c8…`（见注册表） |
| `sources/search-plans/IT_PLAN_V1.yaml` | hash `754fa7f36028…` |
| `sources/search-plans/HU_PLAN_V1.yaml` | hash `52086fc8df8d…` |
| `sources/search-plans/SK_PLAN_V1.yaml` | hash `a3b3d3c5889d…` |
| `sources/source-endpoints.yaml` | +CZ/IT/HU/SK 角色与端点（12 个） |
| `sources/jurisdiction-registry.yaml` | +3 角色 CONNECTED（PILOT_4B2A 节） |
| `sources/jurisdiction-sources/{CZ,IT,SK,HU}.yaml` | 契约刷新（MODE B 证据） |
| `outputs/audit/modeb_channel_probe.json` | Round 1 通道矩阵（端点级实测） |
| `outputs/_modeb_probe*_out.txt` | Round 1-9 原始记录（本地） |

## 五、下一步
- **MODE B 收敛轮**：streak 自各自 PLAN_V1 冻结起算（四辖区可并行；采集用 `run_jurisdiction_round.py` 适配器补齐 CZ/IT/HU/SK fetch/searcher）
- US 80% 门槛缺口（OH/MI 目标区 vantage）与 BATCH 2 待办保持不变
- 磁盘压缩一键脚本仍待管理员执行（`outputs\_compact_docker_admin.cmd`，预期回收 ~88GB）
