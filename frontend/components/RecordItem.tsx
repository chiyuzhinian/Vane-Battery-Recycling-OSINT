"use client";

/**
 * 单条记录 —— 展开阅读 + 三态裁决。
 *
 * ⭐ 为什么裁决按钮放在**展开区**而不是列表行里：
 *    用户明确说「**需要逐个查看之后判定是不是**」。
 *    列表密集时行内按钮极易误点，而且无法做到「看完再判」。
 *    所以行内只显示状态与摘要，**展开后才能裁决**。
 *
 * 展开区给的三样东西，正是人工判断所需的最小信息集：
 *   · 正文摘要（text）      —— 看内容本身对不对
 *   · 命中模式 / 拒绝原因    —— 看机器为什么这么判（hits / rejected_by）
 *   · 原文链接              —— 需要深读时跳出去
 */
import type { RecordBrief, Verdict } from "@/lib/api";

type Props = {
  record: RecordBrief;
  expanded: boolean;
  checked: boolean;
  onToggle: () => void;
  onCheck: (checked: boolean) => void;
  onVerdict: (evidenceId: string, verdict: Verdict) => void;
};

const VERDICT_BTNS: {
  v: Verdict;
  label: string;
  idle: string;
  active: string;
}[] = [
  {
    v: "relevant",
    label: "相关",
    idle: "border-sky-900 text-sky-400 hover:bg-sky-950",
    active: "border-sky-500 bg-sky-600 text-white",
  },
  {
    v: "uncertain",
    label: "待定",
    idle: "border-amber-900 text-amber-400 hover:bg-amber-950",
    active: "border-amber-500 bg-amber-600 text-white",
  },
  {
    v: "irrelevant",
    label: "不相关",
    idle: "border-slate-700 text-slate-400 hover:bg-slate-800",
    active: "border-slate-500 bg-slate-600 text-white",
  },
];

export default function RecordItem({
  record: r,
  expanded,
  checked,
  onToggle,
  onCheck,
  onVerdict,
}: Props) {
  const verdict = (r.review_verdict ?? null) as Verdict | null;

  return (
    <li
      className={`rounded border bg-slate-950/50 transition ${
        r.reviewed ? "border-sky-900/70" : "border-slate-800"
      }`}
    >
      {/* ---------- 行头 ---------- */}
      <div className="flex items-start gap-2 p-2.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          className="mt-1 shrink-0 accent-sky-500"
          aria-label="选择此条"
        />

        <span
          className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] ${
            r.effective_relevant
              ? "bg-sky-900/70 text-sky-300"
              : "bg-slate-800 text-slate-500"
          }`}
          title={
            r.reviewed
              ? `人工改判（机器原判：${r.machine_relevant ? "相关" : "拒绝"}）`
              : "机器判定"
          }
        >
          {r.effective_relevant ? "相关" : "拒绝"}
          {r.reviewed && " ✎"}
        </span>

        <div className="min-w-0 flex-1">
          <button
            onClick={onToggle}
            className="block w-full text-left text-xs leading-snug text-slate-200 hover:text-sky-400"
          >
            {r.title || r.url}
          </button>
          <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] text-slate-500">
            <span className="font-mono">{r.source_id}</span>
            {r.publish_date && <span>{r.publish_date.slice(0, 10)}</span>}
            {r.cluster_hint && <span>{r.cluster_hint}</span>}
            <span>分 {r.relevance_score}</span>
            {r.needs_human_review && (
              <span className="text-amber-500">待复核</span>
            )}
          </div>
        </div>

        <button
          onClick={onToggle}
          className="shrink-0 px-1 text-xs text-slate-500 hover:text-slate-300"
          aria-label={expanded ? "收起" : "展开"}
        >
          {expanded ? "▲" : "▼"}
        </button>
      </div>

      {/* ---------- 展开区：看完再判 ---------- */}
      {expanded && (
        <div className="space-y-3 border-t border-slate-800 px-3 pb-3 pt-3">
          {/* 正文摘要 */}
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
              正文摘要
            </div>
            <p className="max-h-48 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">
              {r.text || "（该记录没有正文文本）"}
            </p>
          </div>

          {/* 判定依据 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                命中模式
              </div>
              <div className="flex flex-wrap gap-1">
                {r.hits.length ? (
                  r.hits.map((h) => (
                    <code
                      key={h}
                      className="rounded bg-sky-950/60 px-1.5 py-0.5 text-[10px] text-sky-300"
                    >
                      {h}
                    </code>
                  ))
                ) : (
                  <span className="text-[10px] text-slate-600">—</span>
                )}
              </div>
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                拒绝原因
              </div>
              {r.rejected_by ? (
                <code className="rounded bg-red-950/50 px-1.5 py-0.5 text-[10px] text-red-300">
                  {r.rejected_by}
                </code>
              ) : (
                <span className="text-[10px] text-slate-600">—</span>
              )}
            </div>
          </div>

          {/* 三态裁决 */}
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
            <span className="text-[11px] text-slate-500">我的裁决：</span>
            {VERDICT_BTNS.map((b) => (
              <button
                key={b.v}
                onClick={() => onVerdict(r.evidence_id, b.v)}
                className={`rounded border px-2.5 py-1 text-[11px] transition ${
                  verdict === b.v ? b.active : b.idle
                }`}
              >
                {b.label}
              </button>
            ))}
            <a
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-[11px] text-slate-400 hover:text-sky-400"
            >
              打开原文 ↗
            </a>
          </div>
        </div>
      )}
    </li>
  );
}
