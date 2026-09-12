"use client";

/**
 * 国家详情抽屉 —— 从右侧滑出的浮层面板。
 *
 * ⭐ 为什么用「浮层」而不是「左右分栏」：
 *    分栏会永久占掉约 420px 横向空间，地图被挤压；
 *    浮层覆盖在上层，关掉就回到纯地图，**地图始终占满全屏**。
 *
 * 三级审核入口都在这里：
 *   ① 源级批量 —— 「数据源分布」每行两个按钮
 *   ② 记录级   —— 展开条目后三态裁决（核心，对应「逐个查看」）
 *   ③ 多选批量 —— 列表顶部全选 + 底部操作栏
 */
import { useCallback, useEffect, useState } from "react";
import RecordItem from "@/components/RecordItem";
import {
  api,
  type CountryDetail,
  type RecordBrief,
  type Verdict,
} from "@/lib/api";

type Props = {
  code: string | null;
  onClose: () => void;
  onToast: (msg: string, undo?: () => void) => void;
  onDataChanged: () => void;
};

const PAGE_SIZE = 50;

export default function CountryDrawer({
  code,
  onClose,
  onToast,
  onDataChanged,
}: Props) {
  const [detail, setDetail] = useState<CountryDetail | null>(null);
  const [records, setRecords] = useState<RecordBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [onlyRelevant, setOnlyRelevant] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  // ---------- 加载 ----------
  const load = useCallback(async () => {
    if (!code) return;
    try {
      const [d, r] = await Promise.all([
        api.country(code),
        api.records({
          country: code,
          relevant: onlyRelevant ? true : undefined,
          page,
          page_size: PAGE_SIZE,
          sort: "score",
        }),
      ]);
      setDetail(d);
      setRecords(r.items);
      setTotal(r.total);
    } catch (e) {
      onToast(`加载失败：${String(e)}`);
    }
  }, [code, onlyRelevant, page, onToast]);

  useEffect(() => {
    void load();
  }, [load]);

  // 切换国家时重置交互状态
  useEffect(() => {
    setExpanded(new Set());
    setChecked(new Set());
    setPage(1);
  }, [code]);

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const open = !!code;

  // ---------- ① 单条裁决（乐观更新）----------
  // note: 备注（拒绝原因 / 收录理由）—— 可选，随裁决写入 review_decisions.jsonl，
  //       后端据此校准判定规则（用户要求："你收到这些后端可以调整"）
  async function handleVerdict(evidenceId: string, verdict: Verdict,
                               note?: string) {
    if (!evidenceId) return;
    const prev = records;
    setRecords((rs) =>
      rs.map((r) =>
        r.evidence_id === evidenceId
          ? {
              ...r,
              reviewed: true,
              review_verdict: verdict,
              review_note: note ?? r.review_note ?? null,
              effective_relevant: verdict === "relevant",
            }
          : r,
      ),
    );
    try {
      const res = await api.review.submit([
        {
          target_type: "record", target_id: evidenceId, verdict,
          reason: note ?? "", country: code,
        },
      ]);
      const ids = res.decisions.map((d) => d.decision_id);
      onToast(`已标记为「${verdictLabel(verdict)}」${note ? "（含备注）" : ""}`, async () => {
        await api.review.revoke(ids);
        setRecords(prev);
        onDataChanged();
      });
      onDataChanged();
    } catch (e) {
      setRecords(prev); // 回滚
      onToast(`保存失败：${String(e)}`);
    }
  }

  // ---------- ③ 批量裁决 ----------
  async function handleBatch(verdict: Verdict) {
    const ids = [...checked];
    if (!ids.length) return;
    const prev = records;
    setBusy(true);
    setRecords((rs) =>
      rs.map((r) =>
        ids.includes(r.evidence_id)
          ? {
              ...r,
              reviewed: true,
              review_verdict: verdict,
              effective_relevant: verdict === "relevant",
            }
          : r,
      ),
    );
    try {
      const res = await api.review.submit(
        ids.map((id) => ({
          target_type: "record" as const,
          target_id: id,
          verdict,
          country: code,
        })),
      );
      const dIds = res.decisions.map((d) => d.decision_id);
      onToast(`已批量标记 ${ids.length} 条为「${verdictLabel(verdict)}」`, async () => {
        await api.review.revoke(dIds);
        setRecords(prev);
        onDataChanged();
      });
      setChecked(new Set());
      onDataChanged();
    } catch (e) {
      setRecords(prev);
      onToast(`批量保存失败：${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  // ---------- ① 源级批量 ----------
  async function handleSourceBatch(sourceId: string, verdict: Verdict, count: number) {
    const label = verdictLabel(verdict);
    // ⭐ 源级会影响该源全部记录，必须二次确认
    if (
      !window.confirm(
        `将「${sourceId}」在当前国家的全部 ${count} 条记录批量标记为「${label}」。\n\n` +
          `此操作可在顶部提示中撤销。确认继续？`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await api.review.submit([
        { target_type: "source", target_id: sourceId, verdict, country: code },
      ]);
      onToast(`已把「${sourceId}」标为「${label}」（${count} 条）`);
      await load();
      onDataChanged();
    } catch (e) {
      onToast(`源级批量失败：${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const toggleExpand = (id: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const toggleCheck = (id: string, on: boolean) =>
    setChecked((s) => {
      const n = new Set(s);
      on ? n.add(id) : n.delete(id);
      return n;
    });

  const allChecked = records.length > 0 && checked.size === records.length;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      {/* 遮罩 */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-30 bg-black/50 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      {/* 抽屉 */}
      <aside
        className={`fixed inset-y-0 right-0 z-40 flex w-[600px] max-w-[92vw] flex-col border-l border-slate-800 bg-slate-950 shadow-2xl transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-hidden={!open}
      >
        {!detail ? (
          <div className="p-8 text-center text-sm text-slate-500">加载中…</div>
        ) : (
          <>
            {/* 头部 */}
            <header className="flex shrink-0 items-start justify-between border-b border-slate-800 px-4 py-3">
              <div>
                <h2 className="text-base font-semibold">{detail.name}</h2>
                <div className="mt-1 flex gap-3 text-[11px] text-slate-400">
                  <span>
                    相关 <b className="text-sky-400">{detail.relevant}</b> /{" "}
                    {detail.total}
                  </span>
                  <span>待复核 {detail.needs_review}</span>
                  <span>已审核 {detail.reviewed}</span>
                </div>
              </div>
              <button
                onClick={onClose}
                className="rounded px-2 py-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
                aria-label="关闭"
              >
                ✕
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-4 py-3">
              {/* ① 源分布 + 源级批量 */}
              <section className="mb-4">
                <h3 className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                  数据源分布
                  <span className="ml-2 normal-case text-slate-600">
                    （可整源批量裁决）
                  </span>
                </h3>
                <div className="space-y-1.5">
                  {detail.sources.map((s) => (
                    <div
                      key={s.source_id}
                      className="flex items-center gap-2 rounded bg-slate-900/60 px-2.5 py-1.5 text-[11px]"
                    >
                      <span className="min-w-0 flex-1 truncate font-mono text-slate-300">
                        {s.source_id}
                      </span>
                      <span className="shrink-0 text-slate-400">
                        {s.relevant}/{s.total}
                        <span className="ml-1 text-slate-500">
                          {Math.round(s.relevance_rate * 100)}%
                        </span>
                      </span>
                      <button
                        disabled={busy}
                        onClick={() =>
                          handleSourceBatch(s.source_id, "relevant", s.total)
                        }
                        className="shrink-0 rounded border border-sky-900 px-1.5 py-0.5 text-sky-400 hover:bg-sky-950 disabled:opacity-40"
                      >
                        全批通过
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          handleSourceBatch(s.source_id, "irrelevant", s.total)
                        }
                        className="shrink-0 rounded border border-slate-700 px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 disabled:opacity-40"
                      >
                        全批否决
                      </button>
                    </div>
                  ))}
                </div>
              </section>

              {/* ② 记录列表 */}
              <section>
                <div className="mb-2 flex items-center gap-3 text-[11px]">
                  <label className="flex cursor-pointer items-center gap-1.5 text-slate-400">
                    <input
                      type="checkbox"
                      checked={allChecked}
                      onChange={(e) =>
                        setChecked(
                          e.target.checked
                            ? new Set(records.map((r) => r.evidence_id))
                            : new Set(),
                        )
                      }
                      className="accent-sky-500"
                    />
                    全选本页
                  </label>
                  {checked.size > 0 && (
                    <span className="text-sky-400">已选 {checked.size} 条</span>
                  )}
                  <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-slate-400">
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
                    <RecordItem
                      key={r.evidence_id}
                      record={r}
                      expanded={expanded.has(r.evidence_id)}
                      checked={checked.has(r.evidence_id)}
                      onToggle={() => toggleExpand(r.evidence_id)}
                      onCheck={(on) => toggleCheck(r.evidence_id, on)}
                      onVerdict={handleVerdict}
                    />
                  ))}
                </ul>

                {records.length === 0 && (
                  <p className="py-8 text-center text-xs text-slate-500">
                    没有匹配的记录
                  </p>
                )}

                {/* 分页 */}
                {totalPages > 1 && (
                  <div className="mt-3 flex items-center justify-center gap-3 text-[11px] text-slate-400">
                    <button
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                      className="rounded border border-slate-800 px-2 py-1 hover:bg-slate-800 disabled:opacity-30"
                    >
                      上一页
                    </button>
                    <span>
                      {page} / {totalPages}（共 {total} 条）
                    </span>
                    <button
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                      className="rounded border border-slate-800 px-2 py-1 hover:bg-slate-800 disabled:opacity-30"
                    >
                      下一页
                    </button>
                  </div>
                )}
              </section>
            </div>

            {/* ③ 批量操作栏（选中时出现） */}
            {checked.size > 0 && (
              <footer className="flex shrink-0 items-center gap-2 border-t border-slate-800 bg-slate-900/80 px-4 py-2.5 text-[11px] backdrop-blur">
                <span className="text-slate-300">已选 {checked.size} 条</span>
                <button
                  disabled={busy}
                  onClick={() => handleBatch("relevant")}
                  className="rounded border border-sky-700 bg-sky-900/50 px-2.5 py-1 text-sky-300 hover:bg-sky-800/60 disabled:opacity-40"
                >
                  批量相关
                </button>
                <button
                  disabled={busy}
                  onClick={() => handleBatch("uncertain")}
                  className="rounded border border-amber-800 bg-amber-950/40 px-2.5 py-1 text-amber-300 hover:bg-amber-900/40 disabled:opacity-40"
                >
                  批量待定
                </button>
                <button
                  disabled={busy}
                  onClick={() => handleBatch("irrelevant")}
                  className="rounded border border-slate-700 px-2.5 py-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  批量不相关
                </button>
                <button
                  onClick={() => setChecked(new Set())}
                  className="ml-auto text-slate-500 hover:text-slate-300"
                >
                  清空选择
                </button>
              </footer>
            )}
          </>
        )}
      </aside>
    </>
  );
}

function verdictLabel(v: Verdict): string {
  return v === "relevant" ? "相关" : v === "irrelevant" ? "不相关" : "待定";
}
