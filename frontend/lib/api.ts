/**
 * 后端 API 客户端 + 类型定义。
 *
 * 后端：FastAPI @ 127.0.0.1:8010（见 scripts/serve_panel.py）
 * 前端：本应用 @ 3100
 *
 * ⚠️ 不要改成 3000 —— 那是 Vane（本项目的通道 A）的端口。
 * ⚠️ 不要用 8000 —— 被另一个项目 lithium-intel 占用，且 Windows 上
 *    `localhost` 优先解析为 `::1`，请求会落到别人那边（接口全 404）。
 */

const API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8010";

// ---------------------------------------------------------------- 类型
export type Region = {
  code: string;
  name: string;
  total: number;
  relevant: number;
  needs_review: number;
  rejected: number;
  source_count: number;
  relevance_rate: number;
  channels: Record<string, number>;
};

export type GeoUnit = {
  code: string;
  name_zh: string;
  name_en: string;
  level: string;              // supranational | country | state | unknown
  parent: string | null;
  renderable: boolean;        // 州级不单独渲染，并入父国家
};

export type RecordBrief = {
  evidence_id: string;
  geo_code: string;
  geo_name: string;
  source_id: string;
  channel: string | null;
  cluster_hint: string | null;
  title: string;
  url: string;
  publish_date: string | null;
  machine_relevant: boolean;      // 机器判定
  effective_relevant: boolean;    // 叠加人工审核后的有效判定
  relevance_score: number;
  needs_human_review: boolean;
  reviewed: boolean;
  review_verdict: string | null;
  hits: string[];
  rejected_by: string | null;
  text: string;              // 正文摘要（供展开阅读后判定）
};

export type RecordPage = {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: RecordBrief[];
};

export type CountryDetail = {
  code: string;
  name: string;
  found: boolean;
  total: number;
  relevant: number;
  needs_review: number;
  reviewed: number;
  sources: {
    source_id: string;
    total: number;
    relevant: number;
    needs_review: number;
    relevance_rate: number;
    clusters: Record<string, number>;
  }[];
  clusters: Record<string, number>;
  children: { code: string; name: string }[];
  date_range: [string, string] | null;
};

export type Facets = {
  countries: { code: string; name: string; count: number }[];
  sources: { source_id: string; count: number }[];
  clusters: { cluster: string; count: number }[];
  counts: {
    total: number;
    relevant: number;
    needs_review: number;
    reviewed: number;
  };
};

// ---------------------------------------------------------------- 审核
export type Verdict = "relevant" | "irrelevant" | "uncertain";

export type DecisionIn = {
  target_type: "record" | "source";
  target_id: string;
  verdict: Verdict;
  reason?: string;
  country?: string | null;
};

export type Decision = Required<DecisionIn> & {
  decision_id: string;
  reviewer: string;
  decided_at: string;
};

export type ReviewStats = {
  total: number;
  by_verdict: Record<Verdict, number>;
  by_target: Record<string, number>;
  records_total: number;
  records_reviewed: number;
};

// ---------------------------------------------------------------- 请求
async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText} — ${path}`);
  }
  return (await r.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = "";
    try {
      detail = ((await r.json()) as { detail?: string }).detail ?? "";
    } catch {
      /* 保持空 */
    }
    throw new Error(detail || `${r.status} ${r.statusText} — ${path}`);
  }
  return (await r.json()) as T;
}

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  map: () => get<{ regions: Region[] }>("/api/map"),
  units: () =>
    get<{ units: GeoUnit[]; map_names: Record<string, string> }>("/api/units"),
  facets: () => get<Facets>("/api/facets"),
  country: (code: string) => get<CountryDetail>(`/api/country/${code}`),
  records: (params: {
    country?: string;
    source_id?: string;
    cluster?: string;
    relevant?: boolean;
    review_only?: boolean;
    unreviewed_only?: boolean;
    q?: string;
    page?: number;
    page_size?: number;
    sort?: "score" | "date";
  }) => get<RecordPage>(`/api/records${qs(params)}`),
  unmapped: () =>
    get<{ has_unmapped: boolean; sources: { source_id: string; count: number }[]; hint: string }>(
      "/api/unmapped",
    ),

  // ---- 审核（写入独立文件，不动原始数据）----
  review: {
    stats: () => get<ReviewStats>("/api/review/stats"),
    submit: (decisions: DecisionIn[]) =>
      post<{ saved: number; decisions: Decision[] }>("/api/review", { decisions }),
    revoke: (decision_ids: string[]) =>
      post<{ removed: number }>("/api/review/revoke", { decision_ids }),
    undoLast: (n = 1) =>
      post<{ removed: number; decision_ids: string[] }>("/api/review/undo-last", { n }),
  },
};
