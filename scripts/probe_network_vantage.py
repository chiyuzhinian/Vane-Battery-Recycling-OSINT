# -*- coding: utf-8 -*-
"""probe_network_vantage.py —— Phase 4B-2B Batch 1R §A1：分层访问观测。

对 Batch 1 的 7 个 blocked 辖区主端点 + 官方替代端点 + 7 个 CONNECTED
对照端点，分层观测：DoH DNS → TCP → TLS → HTTP(httpx) → curl 兜底；
经 app.policy.network_vantage.classify_access 分类后输出矩阵：

  outputs/audit/network_vantage_matrix.json / .csv

字段（规格 §A1）：runner_id / egress_region / network_type / jurisdiction /
source_role / endpoint / dns_status / tcp_status / tls_status / http_status /
content_length / content_type / access_status / failure_reason / checked_at
"""
from __future__ import annotations

import asyncio
import csv
import json
import socket
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.network_vantage import classify_access  # noqa: E402

AUDIT = ROOT / "outputs" / "audit"
RUNNER_ID = "runner-local-dev-1"
EGRESS_REGION = "local-cn"          # 如实：无独立云 Runner（Batch 1R §A2 结论）
NETWORK_TYPE = "dev-workstation"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}

TARGETS: list[tuple[str, str, str, str]] = [
    # (jurisdiction, role, endpoint, kind)
    ("AT", "MS_LEGISLATION_DATABASE", "https://www.ris.bka.gv.at/Bundesrecht/", "main"),
    ("AT", "MS_LEGISLATION_DATABASE", "https://data.bka.gv.at/ris/api/v2.6/", "official_alt"),
    ("HU", "MS_LEGISLATION_DATABASE", "https://njt.hu/", "main"),
    ("HU", "MS_OFFICIAL_GAZETTE", "https://magyarkozlony.hu/", "official_alt"),
    ("BE", "MS_LEGISLATION_DATABASE", "https://www.ejustice.just.fgov.be/cgi_loi/loi_a.pl", "main"),
    ("US-MI", "STATE_LEGISLATURE", "https://www.legislature.mi.gov/", "main"),
    ("US-MI", "STATE_ENVIRONMENT", "https://www.michigan.gov/egle", "main"),
    ("US-GA", "STATE_ENVIRONMENT", "https://epd.georgia.gov/", "main"),
    ("US-GA", "STATE_ENVIRONMENT", "https://georgia.gov/", "official_alt"),
    ("US-OH", "STATE_STATUTES", "https://codes.ohio.gov/", "main"),
    ("US-OH", "STATE_LEGISLATURE", "https://www.legislature.ohio.gov/", "official_alt"),
    ("US-CO", "STATE_ENVIRONMENT", "https://cdphe.colorado.gov/", "main"),
    ("US-CO", "STATE_ENVIRONMENT", "https://colorado.gov/", "official_alt"),
    # CONNECTED 对照
    ("IT", "MS_LEGISLATION_DATABASE", "https://www.normattiva.it/", "main"),
    ("SK", "MS_LEGISLATION_DATABASE", "https://www.slov-lex.sk/", "main"),
    ("CZ", "MS_LEGISLATION_DATABASE", "https://www.psp.cz/", "main"),
    ("US-IL", "STATE_ENVIRONMENT", "https://epa.illinois.gov/", "main"),
    ("US-TN", "STATE_ENVIRONMENT", "https://www.tn.gov/environment.html", "main"),
    ("US-TX", "STATE_STATUTES", "https://statutes.capitol.texas.gov/", "main"),
    ("US-NV", "STATE_ENVIRONMENT", "https://ndep.nv.gov/", "main"),
]

JS_MARKERS = ("__NEXT_DATA__", 'id="root"', "ng-app", "window.__NUXT__",
              "vue.js", "react-dom")


def doh_resolve(host: str) -> str:
    """DoH 解析（阿里/Google 官方 DoH API）→ ok | nxdomain | local_ok | error。"""
    for tpl in ("https://dns.alidns.com/resolve?name={}&type=A",
                "https://dns.google/resolve?name={}&type=A"):
        try:
            r = httpx.get(tpl.format(host), timeout=6)
            if r.status_code == 200:
                st = r.json().get("Status")
                if st is not None:
                    return {0: "ok", 3: "nxdomain"}.get(st, "error")
        except Exception:  # noqa: BLE001
            continue
    try:  # 本地解析兑底（观测层：本地 DNS）
        socket.getaddrinfo(host, 443)
        return "local_ok"
    except socket.gaierror:
        return "error"


def tcp_probe(host: str, port: int = 443, timeout: int = 8) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok"
    except socket.timeout:
        return "timeout"
    except ConnectionRefusedError:
        return "refused"
    except ConnectionResetError:
        return "reset"
    except OSError as exc:
        return "reset" if "reset" in str(exc).lower() else "error"


def tls_probe(host: str, port: int = 443, timeout: int = 8) -> str:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            with ctx.wrap_socket(s, server_hostname=host):
                return "ok"
    except Exception:  # noqa: BLE001
        return "error"


def _looks_js_shell(text: str) -> bool:
    if len(text) > 6000:
        return False
    low = text.lower()
    return any(m.lower() in low for m in JS_MARKERS)


async def http_probe(client: httpx.AsyncClient, url: str) -> dict:
    try:
        r = await client.get(url, headers=UA, timeout=15,
                             follow_redirects=True)
        return {"http_status": r.status_code, "content_len": len(r.content),
                "content_type": r.headers.get("content-type", "")[:60],
                "js_rendered": _looks_js_shell(r.text)}
    except httpx.ConnectTimeout:
        return {"http_status": None, "content_len": 0, "content_type": "",
                "js_rendered": False}
    except Exception:  # noqa: BLE001
        return {"http_status": None, "content_len": 0, "content_type": "",
                "js_rendered": False}


def curl_probe(url: str) -> dict:
    try:
        proc = subprocess.run(
            ["curl.exe", "-sS", "-L", "--max-time", "20", "-A", UA["User-Agent"],
             "-o", "NUL", "-w", "%{http_code} %{size_download}"],
            capture_output=True, timeout=30, text=True)
        parts = (proc.stdout or "").strip().split()
        if len(parts) == 2 and parts[0] != "000":
            return {"http_status": int(parts[0]), "content_len": int(parts[1])}
    except Exception:  # noqa: BLE001
        pass
    return {"http_status": None, "content_len": 0}


async def observe(client: httpx.AsyncClient, jid: str, role: str, url: str,
                  kind: str) -> dict:
    host = urlsplit(url).hostname or ""
    dns_status = await asyncio.to_thread(doh_resolve, host)
    tcp_status = await asyncio.to_thread(tcp_probe, host)
    tls_status = await asyncio.to_thread(tls_probe, host) \
        if tcp_status == "ok" else "skipped"
    http = await http_probe(client, url)
    if http["http_status"] is None and tcp_status == "ok":
        http2 = await asyncio.to_thread(curl_probe, url)
        if http2["http_status"] is not None:
            http.update(http2)
    cls = classify_access(
        dns_status=dns_status, doh_confirms=dns_status,
        tcp_status=tcp_status, tls_status=tls_status,
        http_status=http["http_status"], content_len=http["content_len"],
        js_rendered=http["js_rendered"],
        official_alt_used=(kind == "official_alt"
                           and http["http_status"] == 200))
    return {
        "runner_id": RUNNER_ID, "egress_region": EGRESS_REGION,
        "network_type": NETWORK_TYPE,
        "jurisdiction": jid, "source_role": role, "endpoint": url,
        "kind": kind,
        "dns_status": dns_status, "tcp_status": tcp_status,
        "tls_status": tls_status, "http_status": http["http_status"],
        "content_length": http["content_len"],
        "content_type": http["content_type"],
        "access_status": cls["access_status"],
        "failure_reason": cls["failure_reason"],
        "source_vs_runner": cls["source_vs_runner"],
        "awaiting_independent_runner": cls["awaiting_independent_runner"],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def main() -> int:
    rows: list[dict] = []
    async with httpx.AsyncClient() as client:
        for jid, role, url, kind in TARGETS:
            row = await observe(client, jid, role, url, kind)
            rows.append(row)
            print(f"  [{jid:6s}/{kind:12s}] {row['access_status']:24s} "
                  f"{row['failure_reason']:26s} {url[:60]}", flush=True)
            await asyncio.sleep(1.2)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner_id": RUNNER_ID, "egress_region": EGRESS_REGION,
        "note": ("Batch 1R §A1/§A2：独立云 Runner 当前不可用（无云凭据），"
                 "第二 vantage 走浏览器/官方替代路由；awaiting_independent_runner"
                 "= true 表示需云 Runner 复核出口层归因。"),
        "rows": rows,
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "network_vantage_matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cols = ["jurisdiction", "kind", "dns_status", "tcp_status", "tls_status",
            "http_status", "content_length", "access_status",
            "failure_reason", "source_vs_runner", "endpoint"]
    with (AUDIT / "network_vantage_matrix.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    print(f"→ network_vantage_matrix.json/.csv（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
