"use client";

/**
 * 主页面 —— 世界地图 + 国家详情 + 记录列表。
 *
 * 交互链路：
 *   地图点国家 → 拉 /api/country/{code} 看画像（源分布/相关率/关键词簇）
 *              → 拉 /api/records?country={code} 看记录列表
 *              → （后续阶段）在列表里做审核
 */
import { useCallback, useEffect, useState } from "react";
import WorldMap from "@/components/WorldMap";
import {
  api,
  type CountryDetail,
  type Facets,
  type RecordBrief,
  type Region,
} from "@/lib/api";

export default function Home() {
  const [regions, setRegions] = useState<Region[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<CountryDetail | null>(null);
  const [records, setRecords] = useState<RecordBrief[]>([]);
  const [onlyRelevant, setOnlyRelevant] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // ---- 初始化：地图数据 + 全局统计
  useEffect(() => {
    (async () => {
      try {
        const [m, f] = await Promise.all([api.map(), api.facets()]);
        setRegions(m.regions);
        setFacets(f);
      } catch (e) {
        setErr(`无法连接后端 API（${String(e)}）。请先运行：py scripts/serve_panel.py`);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ---- 选中国家后拉详情 + 记录
  const loadCountry = useCallback(
    async (code: string | null, rel: boolean) => {
      if (!code) {
        setDetail(null);
        setRecords([]);
        return;
      }
      try {
        const [d, r] = await Promise.all([
          api.country(code),
          api.records({
            country: code,
            relevant: rel ? true : undefined,
            page_size: 50,
            sort: "score",
          }),
        ]);
        setDetail(d);
        setRecords(r.items);
      } catch (e) {
        setErr(String(e));
      }
    },
    [],
  );

  useEffect(() => {
    void loadCountry(selected, onlyRelevant);
  }, [selected, onlyRelevant, loadCountry]);

  return (
    <main className="mx-auto max-w-7xl p-6">
      {/* 标题 */}
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            退役电池回收 OSINT 面板
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            全球采集地图 · 点击国家查看采集情况与记录
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          {facets && (
            <>
              <div>
                共 <span className="text-slate-300">{facets.counts.total}</span> 条
                · 相关{" "}
                <span className="text-sky-400">{facets.counts.relevant}</span>
              </div>
              <div>待复核 {facets.counts.needs_review}</div>
            </>
          )}
        </div>
      </header>

      {err && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-300">
          {err}
        </div>
      )}

      {loading && (
        <div className="py-20 text-center text-sm text-slate-500">加载中…</div>
      )}

      {!loading && !err && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
          {/* 左：地图 */}
          <section>
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
              <WorldMap
                regions={regions}
                selected={selected}
                onSelect={setSelected}
              />
            </div>

            {/* 区域概览卡片 */}
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {regions.map((r) => (
                <button
                  key={r.code}
                  onClick={() =>
                    setSelected(selected === r.code ? null : r.code)
                  }
                  className={`rounded-lg border p-3 text-left transition ${
                    selected === r.code
                      ? "border-sky-600 bg-sky-950/40"
                      : "border-slate-800 bg-slate-900/40 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{r.name}</span>
                    <span className="font-mono text-xs text-slate-500">
                      {r.code}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-400">
                    相关 <span className="text-sky-400">{r.relevant}</span> /{" "}
                    {r.total}
                    <span className="ml-1">
                      ({Math.round(r.relevance_rate * 100)}%)
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* 右：详情抽屉 */}
          <aside className="lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)] lg:overflow-y-auto">
            {!selected && (
              <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">
                点击地图上的国家或左侧卡片
                <br />
                查看该区域的采集详情
              </div>
            )}

            {selected && detail?.found && (
              <div className="space-y-4">
                {/* 概览 */}
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
                  <h2 className="text-lg font-semibold">{detail.name}</h2>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <Stat label="总条数" value={detail.total} />
                    <Stat label="相关" value={detail.relevant} accent />
                    <Stat label="待复核" value={detail.needs_review} />
                    <Stat label="已审核" value={detail.reviewed} />
                  </div>
                  {detail.children.length > 0 && (
                    <div className="mt-3 text-xs text-slate-400">
                      子区域：
                      {detail.children.map((c) => (
                        <span key={c.code} className="ml-1 rounded bg-slate-800 px-1.5 py-0.5">
                          {c.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* 源分布（批量审核的入口） */}
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
                  <h3 className="mb-2 text-sm font-medium text-slate-300">
                    数据源分布
                    <span className="ml-2 text-xs font-normal text-slate-500">
                      （下一步：在这里按源批量审核）
                    </span>
                  </h3>
                  <div className="space-y-1.5">
                    {detail.sources.map((s) => (
                      <div
                        key={s.source_id}
                        className="flex items-center justify-between rounded bg-slate-950/60 px-2.5 py-1.5 text-xs"
                      >
                        <span className="font-mono text-slate-300">
                          {s.source_id}
                        </span>
                        <span className="text-slate-400">
                          {s.relevant}/{s.total}
                          <span className="ml-2 text-slate-500">
                            {Math.round(s.relevance_rate * 100)}%
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 记录列表 */}
                <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-medium text-slate-300">
                      记录（{records.length}）
                    </h3>
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
                      <input
                        type="checkbox"
                        checked={onlyRelevant}
                        onChange={(e) => setOnlyRelevant(e.target.checked)}
                        className="accent-sky-500"
                      />
                      只看相关
                    </label>
                  </div>
                  <ul className="space-y-2">
                    {records.map((r) => (
                      <li
                        key={r.evidence_id}
                        className="rounded border border-slate-800 bg-slate-950/50 p-2.5"
                      >
                        <div className="flex items-start gap-2">
                          <span
                            className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] ${
                              r.effective_relevant
                                ? "bg-sky-900/70 text-sky-300"
                                : "bg-slate-800 text-slate-500"
                            }`}
                          >
                            {r.effective_relevant ? "相关" : "拒绝"}
                          </span>
                          <div className="min-w-0">
                            <a
                              href={r.url}
                              target="_blank"
                              rel="noreferrer"
                              className="line-clamp-2 text-xs text-slate-200 hover:text-sky-400"
                            >
                              {r.title || r.url}
                            </a>
                            <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] text-slate-500">
                              <span className="font-mono">{r.source_id}</span>
                              {r.publish_date && <span>{r.publish_date}</span>}
                              {r.cluster_hint && <span>{r.cluster_hint}</span>}
                              <span>分 {r.relevance_score}</span>
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div className="rounded bg-slate-950/60 px-2.5 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div
        className={`text-lg font-semibold ${accent ? "text-sky-400" : "text-slate-200"}`}
      >
        {value}
      </div>
    </div>
  );
}
