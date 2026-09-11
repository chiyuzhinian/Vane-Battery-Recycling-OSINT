"use client";

/**
 * 世界地图 —— 按「相关条数」着色，点击国家看详情。
 *
 * ⭐ 为什么按 relevant 而非 total 着色：
 *    原始条数只反映「抓了多少」，相关条数才反映「有效产能」。
 *    美国 1458 条但相关率 17%，欧盟 134 条相关率 53% ——
 *    如果按 total 着色，会误以为美国贡献最大。
 *
 * 地图数据用本地文件（已从 world-atlas 复制到 public/），不依赖 CDN。
 */
import { useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import type { Region } from "@/lib/api";

const GEO_URL = "/countries-110m.json";

/** world-atlas 里的国家名 → 本项目的地理码 */
const NAME_TO_CODE: Record<string, string> = {
  "United States of America": "US",
  Germany: "DE",
  Netherlands: "NL",
  Spain: "ES",
  France: "FR",
};

const COLOR_EMPTY = "#1e293b"; // 无数据
const COLOR_BASE = "#0c4a6e"; // 有数据但相关=0

type Props = {
  regions: Region[];
  selected: string | null;
  onSelect: (code: string | null) => void;
};

export default function WorldMap({ regions, selected, onSelect }: Props) {
  const [hover, setHover] = useState<{ x: number; y: number; r: Region } | null>(
    null,
  );

  const byCode = useMemo(() => {
    const m = new Map<string, Region>();
    for (const r of regions) m.set(r.code, r);
    return m;
  }, [regions]);

  // 色阶以「最大相关条数」为基准（对数压缩，避免一档独大）
  const maxRel = useMemo(
    () => Math.max(1, ...regions.map((r) => r.relevant)),
    [regions],
  );

  function color(rel: number): string {
    if (rel <= 0) return COLOR_BASE;
    const t = Math.log1p(rel) / Math.log1p(maxRel); // 0..1
    if (t > 0.75) return "#38bdf8";
    if (t > 0.5) return "#0284c7";
    if (t > 0.25) return "#0369a1";
    return "#0c4a6e";
  }

  return (
    <div className="relative">
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 165 }}
        width={900}
        height={460}
        style={{ width: "100%", height: "auto" }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const name = String(geo.properties?.name ?? "");
              const code = NAME_TO_CODE[name];
              const region = code ? byCode.get(code) : undefined;
              const isSel = code && code === selected;

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  onClick={() => {
                    if (!region) return;
                    onSelect(isSel ? null : region.code);
                  }}
                  onMouseEnter={(e: React.MouseEvent) => {
                    if (!region) return;
                    setHover({
                      x: e.clientX,
                      y: e.clientY,
                      r: region,
                    });
                  }}
                  onMouseMove={(e: React.MouseEvent) => {
                    if (!region) return;
                    setHover({ x: e.clientX, y: e.clientY, r: region });
                  }}
                  onMouseLeave={() => setHover(null)}
                  style={{
                    default: {
                      fill: region ? color(region.relevant) : COLOR_EMPTY,
                      stroke: isSel ? "#f8fafc" : "#0f172a",
                      strokeWidth: isSel ? 1.6 : 0.5,
                      outline: "none",
                    },
                    hover: {
                      fill: region ? "#7dd3fc" : "#334155",
                      cursor: region ? "pointer" : "default",
                      outline: "none",
                    },
                    pressed: { outline: "none" },
                  }}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>

      {/* 悬停卡片 */}
      {hover && (
        <div
          className="pointer-events-none fixed z-50 rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs shadow-xl"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="font-semibold text-slate-100">
            {hover.r.name}{" "}
            <span className="font-mono text-slate-400">{hover.r.code}</span>
          </div>
          <div className="mt-1 space-y-0.5 text-slate-300">
            <div>
              相关 <span className="text-sky-400">{hover.r.relevant}</span> / 总{" "}
              {hover.r.total}
              <span className="ml-2 text-slate-400">
                ({Math.round(hover.r.relevance_rate * 100)}%)
              </span>
            </div>
            <div className="text-slate-400">
              {hover.r.source_count} 个源 · 待复核 {hover.r.needs_review}
            </div>
          </div>
        </div>
      )}

      {/* 图例 */}
      <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-400">
        <span>相关条数：</span>
        <span className="flex items-center gap-1">
          <i className="inline-block h-3 w-5 rounded-sm" style={{ background: COLOR_EMPTY }} />
          0
        </span>
        {["#0c4a6e", "#0369a1", "#0284c7", "#38bdf8"].map((c) => (
          <span key={c} className="flex items-center gap-1">
            <i className="inline-block h-3 w-5 rounded-sm" style={{ background: c }} />
          </span>
        ))}
        <span>{maxRel}</span>
        <span className="ml-3 text-slate-500">
          点击国家查看详情（当前阶段只有 EU / US 有数据）
        </span>
      </div>
    </div>
  );
}
