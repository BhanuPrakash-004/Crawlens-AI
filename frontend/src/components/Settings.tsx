import {
  Check,
  Circle,
  RefreshCw,
  ExternalLink as ExternalIcon,
  ShieldCheck,
} from "lucide-react";
import type { Health, Report } from "../types";
import { Modal, Notice } from "./Shared";
import { METRICS, reportKeys, DEFAULT_WEIGHTS } from "../lib";

export function Settings({
  health,
  refresh,
  close,
  refreshing,
}: {
  health: Health | null;
  refresh: () => void;
  close: () => void;
  refreshing: boolean;
}) {
  return (
    <Modal title="Workspace connections" close={close}>
      <p className="modal-description">
        Connect your crawler and preferred AI provider to run live audits.
      </p>
      <div className="connection-list">
        {[
          {
            name: "Backend API",
            ok: !!health,
            detail: health
              ? "Connected to your local audit service"
              : "Start the backend with npm run dev",
          },
          {
            name: "Firecrawl",
            ok: health?.crawler_configured,
            detail: health?.crawler_configured
              ? "API key configured · ready for a live crawl"
              : "Add FIRECRAWL_API_KEY to .env",
          },
          {
            name: "AI recommendations",
            ok: health?.ai_configured,
            detail: health?.ai_configured
              ? `Configured model: ${health.model}`
              : "Rule-based action plans are available now",
          },
        ].map((item) => (
          <div className="connection" key={item.name}>
            <span className={`connection-icon ${item.ok ? "connected" : ""}`}>
              {item.ok ? <Check size={17} /> : <Circle size={17} />}
            </span>
            <div>
              <strong>{item.name}</strong>
              <p>{item.detail}</p>
            </div>
            <span className={`badge ${item.ok ? "passing" : "neutral"}`}>
              {item.ok ? "Configured" : "Not configured"}
            </span>
          </div>
        ))}
      </div>
      <div className="config-help">
        <h3>Your provider, your choice.</h3>
        <p>
          Edit the root <code>.env</code> file and restart the backend. Use the
          API base URL, including its version prefix.
        </p>
        <pre>
          <code>{`FIRECRAWL_API_KEY=your-firecrawl-key\n\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_API_KEY=your-provider-key\nOPENAI_MODEL=your-model-name\nOPENAI_JSON_MODE=true`}</code>
        </pre>
        <p className="microcopy">
          Compatible with providers that implement Chat Completions. For local
          providers, use a local base URL and a placeholder key if required. Set
          JSON mode to false if unsupported.
        </p>
      </div>
      <Notice>
        <ShieldCheck size={14} className="inline-icon" />
        API keys stay on the backend and are never sent to this interface.
      </Notice>
      <div className="modal-footer">
        <a
          className="text-button"
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
        >
          API documentation
          <ExternalIcon size={14} />
        </a>
        <button
          className="secondary-button"
          disabled={refreshing}
          onClick={refresh}
        >
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
          Refresh connection status
        </button>
      </div>
    </Modal>
  );
}

export function Methodology({ close, report }: { close: () => void; report?: Report | null }) {
  const [excellent, good, improvement] = report?.classification_bands ?? [90,75,50];
  const keys = reportKeys(report);
  const measured = keys.filter(k => report?.metrics[k].evaluated);
  return (
    <Modal title="A score you can explain" close={close} wide>
      <p className="modal-description">
        Every number comes from measured page or link evidence. AI is used only
        to help explain what to do next.
      </p>
      <div className="formula">
        Overall score = 100 × Σ (passing / evaluated × weight) / measured weight
        {report && <p>{measured.length ? <>100 × ({measured.map(k => { const m=report.metrics[k]; return `${m.passing}/${m.evaluated} × ${m.weight}`; }).join(" + ")}) / {measured.reduce((n,k)=>n+report.metrics[k].weight,0)} ≈ {report.overall_score}</> : "No measured observations"}</p>}
      </div>
      {keys.map((key) => (
        <div className="method-row" key={key}>
          <span className="method-weight">
            {report?.metrics[key]?.weight ?? DEFAULT_WEIGHTS[key]}
            <small>%</small>
          </span>
          <div>
            <h3>{METRICS[key].name}</h3>
            <p>{report?.pages.find(p=>p.checks[key])?.checks[key]?.expected ?? METRICS[key].rule}</p>
            {!!report?.metrics[key]?.evidence?.length && <details><summary>Calculation evidence</summary><ul>{report.metrics[key].evidence.map((row,i)=><li key={i}><strong>{row.status}</strong> {row.rule} {row.url} · {row.observed}</li>)}</ul></details>}
          </div>
        </div>
      ))}
      <Notice>
        Unknown checks, N/A pages and exclusions awaiting intent review are excluded from the denominator. Metrics without measured observations are omitted.
        If every metric is unknown, the score is unknown. The overall
        calculation uses unrounded pass rates and rounds the final result to the
        nearest integer.
      </Notice>
      <div className="score-legend">
        <span>
          <i className="green-bg" />
          {excellent}–100 Excellent
        </span>
        <span>
          <i className="lime-bg" />
          {good}–{excellent-1} Good
        </span>
        <span>
          <i className="amber-bg" />
          {improvement}–{good-1} Needs improvement
        </span>
        <span>
          <i className="red-bg" />
          0–{improvement-1} Critical
        </span>
      </div>
      <p className="microcopy">
        The report retains the weights and evidence recorded when the audit ran.
      </p>
      <p className="microcopy">
        These weights and categories are product decisions, not official
        search-engine scores. Partial coverage, failed fetches, and unknown
        checks are always disclosed.
      </p>
    </Modal>
  );
}
