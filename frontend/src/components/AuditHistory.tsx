import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  Search,
  History,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { api, host } from "../lib";
import { Empty } from "./Shared";
type Entry = {
  audit_id: string;
  website: string;
  created_at: string;
  status: string;
  score: number | null;
  pages: number | null;
  issues: number | null;
};
export function AuditHistory({
  openAudit,
  busy,
}: {
  openAudit: (id: string) => void;
  busy: boolean;
}) {
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: Entry[]; total: number }>({
    items: [],
    total: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = setTimeout(() => {
      api<{ items: Entry[]; total: number }>(
        `/api/audits?q=${encodeURIComponent(query)}&offset=${offset}&limit=20`,
        { signal: controller.signal },
      )
        .then(setData)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, offset, version]);
  return (
    <section className="history-view view-enter">
      <div className="section-heading">
        <div>
          <h2>Previous audits</h2>
          <p>Reopen results, compare dates, and pick up where you left off.</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => setVersion((v) => v + 1)}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
      <div className="card table-card">
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              aria-label="Search audit history"
              placeholder="Search by website…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <span className="count-chip">{data.total} saved audits</span>
        </div>
        {error ? (
          <div className="error-banner" role="alert">
            {error}
            <button
              className="text-button"
              onClick={() => setVersion((v) => v + 1)}
            >
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="history-loading" role="status">
            Loading your audits…
          </div>
        ) : data.items.length ? (
          <div className="history-list">
            {data.items.map((item) => (
              <button
                className="history-row"
                key={item.audit_id}
                disabled={busy}
                onClick={() => openAudit(item.audit_id)}
                aria-label={`Open audit for ${item.website} from ${item.created_at}`}
              >
                <span className="history-site-icon">
                  <History size={21} />
                </span>
                <div className="history-site">
                  <strong>{host(item.website)}</strong>
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                </div>
                <div className="history-numbers">
                  <strong>
                    {item.score ?? "—"}
                    <small>/100</small>
                  </strong>
                  <span>
                    {item.pages ?? "—"} pages · {item.issues ?? "—"} findings
                  </span>
                </div>
                <span
                  className={`badge ${item.status === "failed" ? "high" : item.status === "completed" ? "passing" : "neutral"}`}
                >
                  {item.status}
                </span>
                <ArrowUpRight size={18} />
              </button>
            ))}
          </div>
        ) : (
          <Empty
            title={
              query
                ? "No matching audits"
                : "Your history starts with your first audit"
            }
          >
            Run an audit above. Completed reports and failed attempts are saved
            automatically, including after a server restart.
          </Empty>
        )}
        <div className="table-footer">
          <span>
            {data.total
              ? `${offset + 1}–${Math.min(offset + 20, data.total)} of ${data.total}`
              : "No audits yet"}
          </span>
          <div>
            <button
              className="icon-button"
              aria-label="Previous history page"
              disabled={offset === 0 || loading}
              onClick={() => setOffset((v) => Math.max(0, v - 20))}
            >
              <ChevronLeft size={17} />
            </button>
            <button
              className="icon-button"
              aria-label="Next history page"
              disabled={offset + 20 >= data.total || loading}
              onClick={() => setOffset((v) => v + 20)}
            >
              <ChevronRight size={17} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
