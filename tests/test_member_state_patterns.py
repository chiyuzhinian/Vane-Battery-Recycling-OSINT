"""成员国语言相关性回归测试 —— py tests/test_member_state_patterns.py

为什么必须存在
--------------
2026-09-11 踩过的坑：**数据采到了，但系统不认。**

    德国 AltfahrzeugV（报废车法，5.4 万字符）  → ❌ 未命中必修词
    德国 AVV（欧洲废物目录，危废分类依据）      → ❌ 未命中必修词
    法国 ADEME REP-VHU（122 条破碎厂数据）      → ❌ 未命中必修词

采集日志一切正常，只是**入不了库**。这类 bug 最危险：
它不报错、不掉数据，只是整层静默消失。

这个测试用**真实法规原文片段**锁住"成员国层必须能过判定"这个不变量。
每新增一个国家通道，就补一组用例。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


# ============================================================
# 正例：真实法规原文（截取），必须判为相关
# ============================================================
MUST_PASS: list[tuple[str, str, str, str]] = [
    (
        "NL",
        "BWBR0013707 Besluit beheer autowrakken",
        "Besluit van 24 mei 2002, houdende implementatie van richtlijn nr. 2000/53/EG "
        "van het Europees Parlement en de Raad van de Europese Unie van 18 september "
        "2000 betreffende autowrakken (PbEG L 269). Wijziging van het Besluit beheer "
        "autowrakken in verband met een verbetering van de implementatie van richtlijn.",
        "autowrak",
    ),
    (
        "NL",
        "BWBR0048234 Verzamelbesluit wijziging bestaande UPV's",
        "Besluit van 30 mei 2023, houdende wijziging van het Besluit beheer autowrakken. "
        "Uitgebreide producentenverantwoordelijkheid voor batterijen.",
        "producentenverantwoordelijkheid / batterij",
    ),
    (
        "DE",
        "AltfahrzeugV",
        "Verordnung über die Überlassung, Rücknahme und umweltverträgliche Entsorgung "
        "von Altfahrzeugen. Der Letztbesitzer hat ein Altfahrzeug einer anerkannten "
        "Annahmestelle zu überlassen; es besteht eine Rücknahmepflicht.",
        "altfahrzeug / rücknahmepflicht",
    ),
    (
        "FR",
        "Arrêté VHU / broyeurs",
        "Arrêté du 2 mai 2012 relatif aux agréments des exploitants des centres VHU et "
        "des installations de broyage. Les opérations de dépollution du véhicule hors "
        "d'usage précédant sa destruction, la filière à responsabilité élargie du producteur.",
        "vhu / broyeur / dépollution",
    ),
    (
        "ES",
        "BOE-A RD pilas y acumuladores",
        "Real Decreto 106/2008, sobre pilas y acumuladores y la gestión ambiental de "
        "sus residuos. Se regula la recogida y el tratamiento de las baterías usadas y "
        "la masa negra obtenida en su valorización.",
        "pilas / acumulador / batería / masa negra",
    ),
    (
        "ES",
        "BOE-A normativa VFU",
        "Por el que se regula el tratamiento de los vehículos fuera de uso. Las "
        "instalaciones de descontaminación y fragmentación deberán cumplir los "
        "requisitos sobre residuos peligrosos y chatarra.",
        "fuera de uso / descontaminación / fragmentación",
    ),
]


# ============================================================
# 反例：长得像但不是本领域的，必须判为不相关
# ============================================================
MUST_FAIL: list[tuple[str, str, str, str]] = [
    (
        "NL",
        "Uitvoeringsregeling loonbelasting",
        "Regeling van de Staatssecretaris van Financiën houdende wijziging van de "
        "Uitvoeringsregeling loonbelasting 2011 in verband met de aanpassing van "
        "enige bedragen voor de vrije vergoedingen en verstrekkingen.",
        "与电池/报废车无关的财税规定",
    ),
    (
        "ES",
        "Ley sobre Tráfico y Seguridad Vial",
        "Real Decreto Legislativo 6/2015, por el que se aprueba el texto refundido de "
        "la Ley sobre Tráfico, Circulación de Vehículos a Motor y Seguridad Vial. "
        "Se regulan las sanciones por exceso de velocidad.",
        "车辆交通法——含“vehículos”但不是报废车",
    ),
    (
        "EN",
        "battery charger product page",
        "This battery charger is compatible with all battery-powered devices. "
        "Battery operated tools not included.",
        "消费电子噪声——必须被 REJECT_IF_MATCH 拦下",
    ),
]


# ============================================================
# 第三类：**相关但必须标记人工复核**
# ------------------------------------------------------------
# ⚠️ 这类**不能**断言为不相关。设计意图是“宁可多审，不可漏政策”：
#    税优/能源条款类文档标题里常不出现 battery，但正文/适用范围
#    往往直接决定电池供应链能不能拿到激励。所以判相关 + 标复核。
#    本测试锁住的是“它必须被标记”，而不是“它必须被丢弃”。
# ============================================================
MUST_REVIEW: list[tuple[str, str, str, str]] = [
    (
        "EN",
        "Clean vehicle credit (税优类)",
        "This document describes the clean vehicle credit under section 30D and "
        "the energy property rules for renewable generation facilities.",
        "税优/能源类——应相关但需人工复核",
    ),
]


def main() -> int:
    print("=" * 74)
    print("成员国语言相关性回归测试")
    print("=" * 74)
    print()

    ok = 0
    print("【正例】成员国法规原文必须被判为相关")
    for region, title, text, why in MUST_PASS:
        v = judge_policy(text, title)
        good = bool(getattr(v, "relevant", False))
        ok += good
        mark = "✅" if good else "❌"
        print(f"  {mark} [{region}] {title[:46]:<48} ← 依赖 {why}")
        if not good:
            print(f"       判定={v}  ← **整层会被静默丢弃**")
    print(f"  → {ok}/{len(MUST_PASS)}")
    print()

    print("【反例】形似但无关的文本不得被判为相关")
    bad_ok = 0
    for region, title, text, why in MUST_FAIL:
        v = judge_policy(text, title)
        not_rel = not getattr(v, "relevant", False)
        bad_ok += not_rel
        mark = "✅" if not_rel else "⚠️"
        print(f"  {mark} [{region}] {title[:46]:<48} {why}")
        if not not_rel:
            print(f"       判定={v}")
    print(f"  → {bad_ok}/{len(MUST_FAIL)}")
    print()

    print("【第三类】税优/能源类必须“相关 + 标记人工复核”（不得静默丢弃）")
    rev_ok = 0
    for region, title, text, why in MUST_REVIEW:
        v = judge_policy(text, title)
        good = bool(getattr(v, "relevant", False)) and bool(
            getattr(v, "needs_human_review", False))
        rev_ok += good
        mark = "✅" if good else "❌"
        print(f"  {mark} [{region}] {title[:46]:<48} {why}")
    print(f"  → {rev_ok}/{len(MUST_REVIEW)}")
    print()
    print("-" * 74)
    total_ok = ok + bad_ok + rev_ok
    total = len(MUST_PASS) + len(MUST_FAIL) + len(MUST_REVIEW)
    print(f"  通过 {total_ok}/{total}")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
