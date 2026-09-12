# -*- coding: utf-8 -*-
"""检查 NIM 丢弃条目的语言覆盖盲区（用已下载的缓存页）。"""
from __future__ import annotations

import html as html_mod
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

BATT_RE = re.compile(
    r"batt|bater|patarei|\bakku|accumul|acumul|akumul|"
    r"\bpiles?\b|pilha|\belem\b|\btelep\b|μπαταρ|συσσωρευτ|"
    r"батери|акумулат", re.I)
ELV_RE = re.compile(
    r"end.of.life vehicle|v[eé]hicule.{0,12}hors|hors\s+d.?usage|\bvhu\b|vfu|"
    r"autowrak|afgedankte?\s+(?:voertuig|auto)|altfahrzeug|"
    r"fahrzeug|voertuig|v[eé]hicule|veicol|vozidl|vozil|j[aá]rmű|pojazd|"
    r"transporto priemon|transportlīdzek|sõiduk|ajoneuvo|k[øo]ret[øo]j|"
    r"fordon|veh[ií]culo|fuori uso|[όο]χημα|vettur|karozz|превозн|автомобил|"
    r"utranger|opušt|kasser|romu|elocast|dismantl|demolition|sloperij|"
    r"broyeur|schredder|schroot|shredder", re.I)
WASTE_RE = re.compile(
    r"afval|abfall|d[eé]chet|waste|residu|rifiut|odpad|j[aä]te|avfall|"
    r"hullad[eé]k|recikl|recyc|recycl|verwertung|valorisation|smalti|"
    r"отпад|jäätm|atkritum|επεξεργασ|ανακύκλ", re.I)


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


TARGETS = {"LT", "HR", "DK", "FI", "SE", "CZ", "GR", "PT"}

for fname, celex in [("_nim_elv.html", "32000L0053"),
                     ("_nim_batt.html", "32006L0066")]:
    html = (ROOT / "outputs" / fname).read_text(encoding="utf-8", errors="replace")
    markers = [(m.start(), m.group(1))
               for m in re.finditer(r'id="([A-Z]{3})_transposition"', html)]
    print(f"===== {celex} =====")
    for i, (pos, alpha3) in enumerate(markers):
        if alpha3 not in {"LTU", "HRV", "DNK", "FIN", "SWE", "CZE", "GRC", "PRT"}:
            continue
        end = markers[i + 1][0] if i + 1 < len(markers) else len(html)
        seg = html[pos:end]
        drops = []
        for m in re.finditer(r'href="[^"]*uri=NIM:(\d+)"[^>]*>([\s\S]*?)</a>', seg):
            title = clean_text(m.group(2))
            if not title:
                continue
            if BATT_RE.search(title) or ELV_RE.search(title) or WASTE_RE.search(title):
                continue
            drops.append((m.group(1), title))
        print(f"\n--- {alpha3} 丢弃 {len(drops)} 条（抽样 8）---")
        for nim, t in drops[:8]:
            print(f"  NIM:{nim}  {t[:130]}")
