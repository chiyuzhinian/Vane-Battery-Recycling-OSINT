"""覆盖率与召回验证 —— 回答"搜索范围内是不是全部都有"。

核心思想
--------
把"搜索边界"拆成**格子**（企业 × 维度），逐格判定三件事：
    ① 数量够不够   verified_claims >= 该维度阈值
    ② 质量过不过   avg_quality_score >= 70
    ③ 时效新不新   latest_claim_age_days <= 该维度时效上限
三项全过 = 🟢 覆盖；有数据未过 = 🟡 弱；一条没有 = ⚪ 空。

再对每个空格子做**根因分类**，因为"没数据"的原因不同，补法完全不同：
    no_source     没有源覆盖     → 补数据源
    no_connector  有源但只能人工  → 写 Connector
    blocked       源被反爬       → Playwright 或换入口
    no_query      查询词没写对    → 调查询模板
    filtered_out  被相关性规则误杀 → 修规则
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 与 sources/search-boundary.yaml 的 boundary.dimensions 保持一致
DIMENSION_RULES: dict[str, dict] = {
    "hr":         {"name": "人力资源",     "min_claims": 3, "min_quality": 70, "freshness_days": 180},
    "feedstock":  {"name": "废料量及来源", "min_claims": 5, "min_quality": 70, "freshness_days": 180},
    "operation":  {"name": "经营现状",     "min_claims": 5, "min_quality": 70, "freshness_days": 365},
    "strategy":   {"name": "战略规划",     "min_claims": 3, "min_quality": 70, "freshness_days": 90},
    "technology": {"name": "工艺技术",     "min_claims": 3, "min_quality": 70, "freshness_days": 730},
}

STATE_ICON = {"covered": "🟢", "weak": "🟡", "empty": "⚪", "out_of_scope": "⚫"}


@dataclass
class Cell:
    company_id: str
    dimension: str
    n_claims: int = 0
    avg_quality: float = 0.0
    latest_age_days: int | None = None
    out_of_scope: bool = False
    # 诊断用：这一格都用了哪些源、失败在哪
    sources_tried: list[str] = field(default_factory=list)
    sources_hit: list[str] = field(default_factory=list)
    blocked_sources: list[str] = field(default_factory=list)
    filtered_out: int = 0
    queries_used: list[str] = field(default_factory=list)

    @property
    def rule(self) -> dict:
        return DIMENSION_RULES[self.dimension]

    @property
    def state(self) -> str:
        if self.out_of_scope:
            return "out_of_scope"
        if self.n_claims == 0:
            return "empty"
        if (self.n_claims >= self.rule["min_claims"]
                and self.avg_quality >= self.rule["min_quality"]
                and self.latest_age_days is not None
                and self.latest_age_days <= self.rule["freshness_days"]):
            return "covered"
        return "weak"

    @property
    def gaps(self) -> list[str]:
        """未达标的具体原因（用于报告里精确说明差在哪）。"""
        if self.out_of_scope or self.state == "covered":
            return []
        out: list[str] = []
        if self.n_claims < self.rule["min_claims"]:
            out.append(f"数量 {self.n_claims}/{self.rule['min_claims']}")
        if self.avg_quality < self.rule["min_quality"]:
            out.append(f"质量 {self.avg_quality:.0f}/{self.rule['min_quality']}")
        if self.latest_age_days is None:
            out.append("无时效数据")
        elif self.latest_age_days > self.rule["freshness_days"]:
            out.append(f"时效 {self.latest_age_days}天 > {self.rule['freshness_days']}天")
        return out

    @property
    def root_cause(self) -> str | None:
        """缺口根因分类 —— 决定下一步该做什么。"""
        if self.state in ("covered", "out_of_scope"):
            return None
        if self.blocked_sources:
            return "blocked"
        if self.filtered_out >= 3 and self.n_claims == 0:
            return "filtered_out"
        if not self.sources_tried:
            return "no_source"
        if self.sources_tried and not self.sources_hit:
            return "no_connector" if not self.queries_used else "no_query"
        return "no_query"


@dataclass
class CoverageReport:
    generated_at: datetime
    cells: list[Cell]

    @property
    def total(self) -> int:
        return len([c for c in self.cells if not c.out_of_scope])

    @property
    def counts(self) -> Counter:
        return Counter(c.state for c in self.cells)

    @property
    def rate(self) -> float:
        return round(self.counts["covered"] / self.total * 100, 1) if self.total else 0.0

    def by_company(self) -> dict[str, Counter]:
        out: dict[str, Counter] = {}
        for c in self.cells:
            out.setdefault(c.company_id, Counter())[c.state] += 1
        return out

    def top_gaps(self, n: int = 10) -> list[Cell]:
        priority = {"empty": 0, "weak": 1, "covered": 2, "out_of_scope": 3}
        return sorted(self.cells, key=lambda c: (priority[c.state], c.n_claims))[:n]

    def root_cause_summary(self) -> Counter:
        return Counter(c.root_cause for c in self.cells if c.root_cause)

    def render(self) -> str:
        lines = [
            f"【覆盖率报告】{self.generated_at:%Y-%m-%d %H:%M}",
            f"边界：{len(set(c.company_id for c in self.cells))} 企业 × "
            f"{len(DIMENSION_RULES)} 维度 = {self.total} 格",
            "",
            f"{'企业':<14}{'🟢':>4}{'🟡':>4}{'⚪':>4}   覆盖率",
            "─" * 46,
        ]
        for cid, cnt in sorted(self.by_company().items(),
                               key=lambda kv: kv[1]["covered"], reverse=True):
            total = sum(cnt.values())
            rate = cnt["covered"] / total * 100 if total else 0
            lines.append(f"{cid:<14}{cnt['covered']:>4}{cnt['weak']:>4}{cnt['empty']:>4}   {rate:>5.0f}%")
        c = self.counts
        lines += [
            "─" * 46,
            f"{'合计':<14}{c['covered']:>4}{c['weak']:>4}{c['empty']:>4}   {self.rate:>5.1f}%",
            "",
            "🔍 缺口根因分布：",
        ]
        causes = self.root_cause_summary()
        if not causes:
            lines.append("  （无缺口）")
        for cause, n in causes.most_common():
            lines.append(f"  · {cause:<14} {n} 格")
        lines += ["", "🚨 优先补齐（前 10 格）："]
        for cell in self.top_gaps(10):
            if cell.state == "covered":
                continue
            lines.append(
                f"  {STATE_ICON[cell.state]} {cell.company_id}/{cell.dimension}"
                f"  根因={cell.root_cause}  差距={'; '.join(cell.gaps) or '无数据'}"
            )
        return "\n".join(lines)


def build_cells(
    companies: list[str],
    claims: list[dict],
    *,
    out_of_scope: set[tuple[str, str]] | None = None,
    sources_tried: dict[tuple[str, str], list[str]] | None = None,
    sources_hit: dict[tuple[str, str], list[str]] | None = None,
    blocked_sources: dict[tuple[str, str], list[str]] | None = None,
    filtered_out: dict[tuple[str, str], int] | None = None,
    queries_used: dict[tuple[str, str], list[str]] | None = None,
) -> list[Cell]:
    """由 claim 清单生成覆盖率格子。

    claims: [{"company_id","dimension","quality_score","published_at"(datetime|iso)}]
    """
    oos = out_of_scope or set()
    cells: dict[tuple[str, str], Cell] = {}
    now = datetime.now(timezone.utc)

    for cid in companies:
        for dim in DIMENSION_RULES:
            key = (cid, dim)
            cells[key] = Cell(
                company_id=cid,
                dimension=dim,
                out_of_scope=key in oos,
                sources_tried=(sources_tried or {}).get(key, []),
                sources_hit=(sources_hit or {}).get(key, []),
                blocked_sources=(blocked_sources or {}).get(key, []),
                filtered_out=(filtered_out or {}).get(key, 0),
                queries_used=(queries_used or {}).get(key, []),
            )

    for cl in claims:
        key = (cl["company_id"], cl["dimension"])
        cell = cells.get(key)
        if cell is None:
            continue
        cell.n_claims += 1
        cell.avg_quality += float(cl.get("quality_score") or 0)
        pub = cl.get("published_at")
        if isinstance(pub, str):
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                pub = None
        if isinstance(pub, datetime):
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age = (now - pub).days
            cell.latest_age_days = min(cell.latest_age_days or 10**6, age)

    for cell in cells.values():
        if cell.n_claims:
            cell.avg_quality = round(cell.avg_quality / cell.n_claims, 1)

    return list(cells.values())


def make_report(cells: list[Cell]) -> CoverageReport:
    return CoverageReport(generated_at=datetime.now(timezone.utc), cells=cells)


if __name__ == "__main__":
    demo_companies = ["gemm", "brunp", "jinsheng"]
    demo_claims = (
        [{"company_id": "gemm", "dimension": d, "quality_score": 88,
          "published_at": "2026-06-01"} for d in DIMENSION_RULES] * 5
        + [{"company_id": "brunp", "dimension": "hr", "quality_score": 75,
            "published_at": "2026-05-01"}] * 3
        + [{"company_id": "brunp", "dimension": "feedstock", "quality_score": 62,
            "published_at": "2024-01-01"}] * 2
    )
    cells = build_cells(
        demo_companies, demo_claims,
        sources_tried={("jinsheng", "feedstock"): ["eia"]},
        blocked_sources={("jinsheng", "technology"): ["cnipa"]},
        filtered_out={("jinsheng", "hr"): 5},
    )
    print(make_report(cells).render())
