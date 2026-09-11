"use client";

/**
 * 主页面 —— 全屏地图 + 浮层抽屉 + 撤销提示。
 *
 * 布局要点（对应「页面没撑满 / 地图太小」的修复）：
 *   · `h-screen flex flex-col` —— 撑满视口，**不做 max-w-7xl 限宽**
 *   · 地图容器 `flex-1 min-h-0` —— 占满顶栏之外的**全部**空间
 *     （`min-h-0` 必需，否则 flex 子项不会收缩，地图会被内容撑破）
 *   · 详情改为**浮层抽屉**，不再永久占用横向空间
 */
import { useCallback, useEffect, useRef, useState } from "react";
import CountryDrawer from "@/components/CountryDrawer";
import WorldMap from "@/components/WorldMap";
import { api, type Facets, type Region } from "@/lib/api";

export default function Home() {
  const [regions, setRegions] = useState<Region[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; undo?: () => void } | null>(
    null,
  );
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const loadMap = useCallback(async () => {
    try {
      const [m, f] = await Promise.all([api.map(), api.facets()]);
      setRegions(m.regions);
      setFacets(f);
      setErr(null);
    } catch (e) {
      setErr(
        `无法连接后端 API（${String(e)}）。请确认已运行：py scripts/serve_panel.py`,
      );
    }
  }, []);

  useEffect(() => {
    void loadMap();
  }, [loadMap]);

  const showToast = useCallback((msg: string, undo?: () => void) => {
    setToast({ msg, undo });
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 7000);
  }, []);

  const closeToast = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setToast(null);
  };

  return (
    <main className="flex h-screen w-full flex-col overflow-hidden bg-slate-950">
      {/* ---------------- 顶栏 ---------------- */}
      <header className="flex shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900/50 px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <h1 className="text-sm font-semibold tracking-tight">
            退役电池回收 OSINT 面板
          </h1>
          <span className="hidden text-[11px] text-slate-500 sm:inline">
            全球采集地图
          </span>
        </div>

        {facets && (
          <div className="hidden items-center gap-4 text-[11px] text-slate-400 md:flex">
            <span>
              共 <b className="text-slate-200">{facets.counts.total}</b> 条
            </span>
            <span>
              相关 <b className="text-sky-400">{facets.counts.relevant}</b>
            </span>
            <span>
              待复核{" "}
              <b className="text-amber-400">{facets.counts.needs_review}</b>
            </span>
            <span>
              已审核 <b className="text-emerald-400">{facets.counts.reviewed}</b>
            </span>
          </div>
        )}

        {/* 区域快捷入口：地图上小国家不好点中，这里补一条 */}
        <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
          {regions.map((r) => (
            <button
              key={r.code}
              onClick={() => setSelected(selected === r.code ? null : r.code)}
              className={`rounded border px-2 py-1 text-[11px] transition ${
                selected === r.code
                  ? "border-sky-500 bg-sky-950 text-sky-300"
                  : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
              title={`相关 ${r.relevant} / 共 ${r.total}（${Math.round(
                r.relevance_rate * 100,
              )}%）`}
            >
              {r.name}
              <span className="ml-1 text-slate-500">{r.relevant}</span>
            </button>
          ))}
        </div>
      </header>

      {err && (
        <div className="shrink-0 border-b border-red-900 bg-red-950/50 px-4 py-2 text-[11px] text-red-300">
          {err}
        </div>
      )}

      {/* ---------------- 地图（占满剩余空间）---------------- */}
      <div className="relative min-h-0 flex-1">
        <WorldMap regions={regions} selected={selected} onSelect={setSelected} />
      </div>

      {/* ---------------- 详情抽屉 ---------------- */}
      <CountryDrawer
        code={selected}
        onClose={() => setSelected(null)}
        onToast={showToast}
        onDataChanged={loadMap}
      />

      {/* ---------------- 撤销提示 ---------------- */}
      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-slate-700 bg-slate-900/95 px-4 py-2.5 text-xs shadow-2xl backdrop-blur">
          <span className="text-slate-200">{toast.msg}</span>
          {toast.undo && (
            <button
              onClick={async () => {
                await toast.undo?.();
                closeToast();
                showToast("已撤销");
              }}
              className="rounded border border-amber-700 px-2 py-0.5 text-amber-400 hover:bg-amber-950"
            >
              撤销
            </button>
          )}
          <button
            onClick={closeToast}
            className="text-slate-500 hover:text-slate-300"
            aria-label="关闭提示"
          >
            ✕
          </button>
        </div>
      )}
    </main>
  );
}
