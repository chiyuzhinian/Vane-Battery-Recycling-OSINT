"""一次性探针：看清 DILA 增量包里 XML 的真实结构。

背景：fr_dila 落盘的 8 条记录全部判定不相关（分数 0.0），
正文头是 `LEGITEXT... LEGI texte/version/... DECRET JORFTEXT...`，
怀疑 _scan() 把「XML 元数据头」当成了「法律正文」。

本脚本回答三个问题：
  1. XML 根元素 / 主要节点是什么？（正文到底在哪个标签里）
  2. 剥标签后前 4000 字符里，元数据占多少、正文占多少？
  3. 关键词命中的是**正文**还是**元数据**？

用法：py scripts/probe_dila_xml.py
"""
from __future__ import annotations

import io
import re
import sys
import tarfile

import httpx

sys.path.insert(0, ".")

BASE = "https://echanges.dila.gouv.fr/OPENDATA"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
HREF_RE = re.compile(r'href="([^"]+)"')

# 只看这几个节点：DILA 的正文容器候选
CONTENT_TAGS = ("BLOC_TEXTUEL", "CONTENU", "TEXTE", "TEXTE_VERSION")


# ⚠️ 本机 urllib 对 echanges.dila.gouv.fr 报 SSL UNEXPECTED_EOF（同 git push 那类抖动），
#    但 curl 实测 200 —— 换 httpx 走系统 TLS 栈即可。
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OSINT-research/1.0)"}


def _get(url: str, timeout: float = 180.0) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True,
                      headers=HEADERS) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def list_latest(dataset: str, n: int = 3) -> list[str]:
    html = _get(f"{BASE}/{dataset}/", timeout=60).decode("utf-8", "replace")
    names = [h for h in HREF_RE.findall(html)
             if h.endswith(".tar.gz") and not h.startswith("?")]
    return sorted(names, reverse=True)[:n]


def probe(dataset: str, name: str, limit: int = 400) -> None:
    url = f"{BASE}/{dataset}/{name}"
    print(f"\n{'=' * 78}\n📦 {dataset}/{name}")
    blob = _get(url)
    print(f"   下载 {len(blob) / 1024:.0f} KB")

    tar = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    members = [m for m in tar.getmembers()
               if m.isfile() and m.name.lower().endswith(".xml")]
    print(f"   包内 XML 文件：{len(members)} 个")
    # 按大小排序，看最大的几个（正文最可能在里面）
    members.sort(key=lambda m: m.size, reverse=True)
    print(f"   最大的 5 个：")
    for m in members[:5]:
        print(f"      {m.size:>9,} B  {m.name}")

    # 取一个较大的文件做结构分析
    for m in members[:limit]:
        raw = tar.extractfile(m)
        if raw is None:
            continue
        content = raw.read().decode("utf-8", "replace")
        if len(content) < 3000:
            continue

        print(f"\n   ── 样本：{m.name}（{len(content):,} 字符）")
        # 1) 根元素 / 前 3 行
        head = content.lstrip()[:600]
        print(f"   XML 头 600 字符：\n{head}\n")

        # 2) 每个候选正文标签出现情况
        for tag in CONTENT_TAGS:
            n_open = len(re.findall(rf"<{tag}[ >]", content))
            if n_open:
                seg = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", content, re.S)
                seglen = len(seg.group(1)) if seg else 0
                print(f"   · <{tag}> 出现 {n_open} 次，首段内长 {seglen:,} 字符")

        # 3) 剥标签后的前 4000 字符（模拟 _scan 的产物）
        stripped = WS_RE.sub(" ", TAG_RE.sub(" ", content)).strip()
        print(f"\n   剥标签后总长 {len(stripped):,} 字符；前 4000 的构成：")
        print(f"   {stripped[:4000][:700]}...")

        # 4) 关键词命中的位置：正文 vs 元数据
        low = content.lower()
        for kw in ("batterie", "véhicule hors d'usage", "déchet", "recyclage"):
            pos = low.find(kw)
            if pos < 0:
                continue
            # 该关键词是否落在正文标签内？
            inside = any(
                (m.start() < pos < m.end())
                for m in re.finditer(rf"<{t}[^>]*>.*?</{t}>", content, re.S)
                for t in CONTENT_TAGS
            )
            print(f"   · 「{kw}」位置 {pos:,}  在正文标签内={inside}  "
                  f"上下文: {content[max(0, pos - 60):pos + 80]!r}")
        break


if __name__ == "__main__":
    for ds in ("JORF", "LEGI"):
        try:
            names = list_latest(ds, 1)
            if not names:
                print(f"⚠️ {ds}: 未列出增量包")
                continue
            probe(ds, names[0])
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ {ds} 探测失败: {type(exc).__name__}: {exc}")
