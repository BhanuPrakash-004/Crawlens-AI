import { MeasuredEvidence, outcome } from "./MeasuredEvidence";
import { useDeferredValue, useState } from "react";
import {
  Search,
  SlidersHorizontal,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Check,
  X,
  FileText,
  Sparkles,
  ShieldCheck,
  Link2,
  Info,
  Download,
  AlertTriangle,
} from "lucide-react";
import type { Report, IssueCategory, Severity, Issue, Page } from "../types";
import {
  METRICS,
  reportKeys,
  CATEGORIES,
  CATEGORY_KEYS,
  pagePath,
  downloadReport,
} from "../lib";
import {
  Badge,
  CopyButton,
  Empty,
  ExternalLink,
  Modal,
  Notice,
} from "./Shared";
import { metricIcons } from "./Overview";

function Pagination({
  page,
  count,
  size = 10,
  setPage,
}: {
  page: number;
  count: number;
  size?: number;
  setPage: (page: number) => void;
}) {
  return (
    <div className="table-footer">
      <span>
        {count
          ? `${page * size + 1}–${Math.min((page + 1) * size, count)} of ${count}`
          : "0"}{" "}
        results
      </span>
      <div>
        <button
          className="icon-button"
          onClick={() => setPage(page - 1)}
          disabled={page === 0}
          aria-label="Previous page"
        >
          <ChevronLeft size={17} />
        </button>
        <span>
          Page {page + 1} of {Math.max(1, Math.ceil(count / size))}
        </span>
        <button
          className="icon-button"
          onClick={() => setPage(page + 1)}
          disabled={(page + 1) * size >= count}
          aria-label="Next page"
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </div>
  );
}

export function IssueExplorer({
  report,
  metric,
  setMetric,
  selectedIds,
  clearIds,
}: {
  report: Report;
  metric: IssueCategory | "all";
  setMetric: (metric: IssueCategory | "all") => void;
  selectedIds: string[] | null;
  clearIds: () => void;
}) {
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");
  const search = useDeferredValue(query.toLowerCase());
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Issue | null>(null);
  const filtered = report.issues.filter(
    (issue) =>
      (metric === "all" || issue.metric === metric) &&
      (severity === "all" || issue.severity === severity) &&
      (!selectedIds || selectedIds.includes(issue.id)) &&
      `${issue.title} ${issue.page_url} ${issue.observed} ${issue.target_url ?? ""}`
        .toLowerCase()
        .includes(search),
  );
  const currentPage = Math.min(
    page,
    Math.max(0, Math.ceil(filtered.length / 10) - 1),
  );
  return (
    <div className="view-enter">
      <div className="section-heading">
        <div>
          <h2>All findings</h2>
          <p>
            Filter by category or priority, then open a finding to see the
            evidence.
          </p>
        </div>
        <button
          className="secondary-button"
          onClick={() => downloadReport(report, "csv")}
        >
          <Download size={16} />
          Export CSV
        </button>
      </div>
      <div className="filter-pills" aria-label="Metric filters">
        <button
          className={metric === "all" ? "selected" : ""}
          onClick={() => {
            setMetric("all");
            setPage(0);
          }}
        >
          All issues<span>{report.issues.length}</span>
        </button>
        {CATEGORY_KEYS.filter(k => k !== "site_health" && (k in report.metrics || k === "robots_txt" || k === "sitemap")).map((key) => (
          <button
            key={key}
            className={metric === key ? "selected" : ""}
            onClick={() => {
              setMetric(key);
              setPage(0);
            }}
          >
            {CATEGORIES[key].short}
            <span>{report.issues.filter((i) => i.metric === key).length}</span>
          </button>
        ))}
      </div>
      {selectedIds && (
        <div className="evidence-filter">
          <Link2 size={15} />
          Showing evidence for the selected recommendation
          <button className="text-button" onClick={clearIds}>
            Clear filter
            <X size={14} />
          </button>
        </div>
      )}
      {metric !== "all" && <Notice>{CATEGORIES[metric].rule}</Notice>}
      <section className="card table-card">
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              aria-label="Search issues"
              placeholder="Search pages, issues, or evidence…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <label className="select-field">
            <SlidersHorizontal size={15} />
            <select
              aria-label="Filter by severity"
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value as Severity | "all");
                setPage(0);
              }}
            >
              <option value="all">All priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High priority</option>
              <option value="medium">Medium priority</option>
              <option value="low">Low priority</option>
            </select>
          </label>
        </div>
        {filtered.length ? (
          <div className="table-scroll">
            <table className="interactive-table issues-table">
              <thead>
                <tr>
                  <th>Issue / affected page</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Observed evidence</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered
                  .slice(currentPage * 10, currentPage * 10 + 10)
                  .map((issue) => (
                    <tr key={issue.id}>
                      <td>
                        <button
                          className="table-title"
                          onClick={() => setSelected(issue)}
                        >
                          {issue.title}
                        </button>
                        <span className="table-url" title={issue.page_url}>
                          {pagePath(issue.page_url)}
                        </span>
                      </td>
                      <td>
                        <span className="category-tag">
                          {CATEGORIES[issue.metric].short}
                        </span>
                      </td>
                      <td>
                        <Badge severity={issue.severity} />
                      </td>
                      <td className="evidence-cell">{issue.observed}</td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`View issue ${issue.id}`}
                          onClick={() => setSelected(issue)}
                        >
                          <ArrowUpRight size={17} />
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              report.issues.length
                ? "No matching findings"
                : "All clear in this audit scope"
            }
          >
            {report.issues.length
              ? "Try a different category, priority, or search term."
              : "No checks failed. Review coverage for anything that could not be verified."}
          </Empty>
        )}
        <Pagination
          count={filtered.length}
          page={currentPage}
          setPage={setPage}
        />
      </section>
      {selected && (
        <Modal title="A closer look" close={() => setSelected(null)}>
          <div className="detail-tags">
            <Badge severity={selected.severity} /> {selected.outcome}
            <span className="category-tag">
              {CATEGORIES[selected.metric].short}
            </span>
          </div>
          <h3 className="detail-title">{selected.title}</h3>
          <div className="detail-field">
            <label>AFFECTED PAGE</label>
            <ExternalLink url={selected.page_url} />
          </div>
          {selected.target_url && (
            <div className="detail-field">
              <label>
                {selected.metric === "broken_links"
                  ? "LINK DESTINATION"
                  : "FILE URL"}
              </label>
              <ExternalLink url={selected.target_url} />
              {selected.affected_source_pages != null && (
                <p>
                  Referenced by {selected.affected_source_pages} source page(s).
                </p>
              )}
            </div>
          )}
          <div className="evidence-box">
            <div>
              <label>Observed</label>
              <p>{selected.observed}</p>
            </div>
            <div>
              <label>Expected</label>
              <p>{selected.expected}</p>
            </div>
          </div>
          {selected.impact && <p><strong>Business impact</strong><br/>{selected.impact}</p>}
          <MeasuredEvidence metric={selected.metric} data={selected.evidence}/>
          {selected.evidence && <details className="evidence-disclosure"><summary>Supporting evidence</summary><pre className="evidence-json">{JSON.stringify(selected.evidence,null,2)}</pre></details>}
          {selected.manual_review && (
            <Notice>
              This may be an authentication or bot restriction. Verify manually
              before changing the link.
            </Notice>
          )}
          <div className="fix-box">
            <span>
              <Sparkles size={16} />
              Suggested next step
            </span>
            <p>{selected.suggested_action}</p>
          </div>
          <p className="microcopy">
            Evidence ID: {selected.id}.{" "}
            Measured by the Python rule engine.
          </p>
        </Modal>
      )}
    </div>
  );
}

export function PagesView({ report }: { report: Report }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Page | null>(null);
  const [page, setPage] = useState(0);
  const pages = report.pages.filter((item) =>
    item.url.toLowerCase().includes(query.toLowerCase()),
  );
  const checks = reportKeys(report).filter((key) => key !== "broken_links" && key !== "site_health");
  const pageIndex = Math.min(
    page,
    Math.max(0, Math.ceil(pages.length / 10) - 1),
  );
  return (
    <div className="view-enter">
      <div className="section-heading">
        <div>
          <h2>Page inventory</h2>
          <p>
            Explore extracted metadata, heading structure, and individual check
            results.
          </p>
        </div>
        <span className="count-chip">
          {report.pages_crawled} pages analyzed
        </span>
      </div>
      <section className="card table-card">
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              aria-label="Search analyzed pages"
              placeholder="Find a page…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <span className="microcopy">
            ✓ Passing<span className="inline-dot">·</span>× Needs attention
            <span className="inline-dot">·</span>— Unknown
          </span>
        </div>
        <div className="table-scroll">
          <table className="interactive-table">
            <thead>
              <tr>
                <th>Page</th>
                <th>HTTP</th>
                {checks.map((key) => (
                  <th key={key}>{METRICS[key].short}</th>
                ))}
                <th>
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {pages.slice(pageIndex * 10, pageIndex * 10 + 10).map((item) => (
                <tr key={item.url}>
                  <td>
                    <button
                      className="table-title"
                      onClick={() => setSelected(item)}
                    >
                      {pagePath(item.url)}
                    </button>
                    <span className="table-url">
                      {String(
                        item.checks.metadata?.details.title || "No page title",
                      )}
                    </span>
                  </td>
                  <td>
                    <span className="http-code">{item.status_code ?? "—"}</span>
                  </td>
                  {checks.map((key) => (
                    <td key={key}>
                      <span
                        className={`check-status ${outcome(item.checks[key]) === "Passed" ? "pass" : outcome(item.checks[key]) === "Failed" ? "fail" : "unknown"}`}
                        aria-label={`${METRICS[key].short}: ${outcome(item.checks[key])}`}
                      >
                        {outcome(item.checks[key]) === "Passed" ? <Check size={15}/> : outcome(item.checks[key]) === "Failed" ? <X size={15}/> : outcome(item.checks[key])}
                      </span>
                    </td>
                  ))}
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Inspect page ${pagePath(item.url)}`}
                      onClick={() => setSelected(item)}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!pages.length && (
          <Empty title="No pages found">Try a different page path.</Empty>
        )}
        <Pagination page={pageIndex} count={pages.length} setPage={setPage} />
      </section>
      {selected && (
        <Modal title="Page evidence" close={() => setSelected(null)} wide>
          <ExternalLink url={selected.url} />
          {checks.map((key) => {
            const check = selected.checks[key];
            if (!check) return null;
            const Icon = metricIcons[key];
            return (
              <section className="page-check" key={key}>
                <div>
                  <Icon size={18} />
                  <h3>{METRICS[key].name}</h3>
                  <span
                    className={`badge ${check.passed === true ? "passing" : check.passed === false ? "high" : "neutral"}`}
                  >
                    {outcome(check)}
                  </span>
                </div>
                <p>{check.observed}</p>
                <p className="microcopy">{check.expected}</p>
                <MeasuredEvidence metric={key} data={check.details}/>
                <details>
                  <summary>Full measured evidence</summary>
                  <pre className="evidence-json">
                    {JSON.stringify(check.details, null, 2)}
                  </pre>
                </details>
                {key === "metadata" && (
                  <div className="metadata-original">
                    <label>
                      Title · {String(check.details.title_length)} characters
                    </label>
                    <p>{String(check.details.title || "(missing)")}</p>
                    <label>
                      Description · {String(check.details.description_length)}{" "}
                      characters
                    </label>
                    <p>{String(check.details.description || "(missing)")}</p>
                  </div>
                )}
                {key === "headings" && !check.details.headings && (
                  <p className="mono">
                    H1:{" "}
                    {Array.isArray(check.details.h1)
                      ? check.details.h1.join(" / ") || "(missing)"
                      : "(missing)"}
                  </p>
                )}
                {key === "structured_data" && (
                  <p className="mono">
                    Types:{" "}
                    {Array.isArray(check.details.types)
                      ? check.details.types.join(", ") || "(none)"
                      : "(none)"}
                  </p>
                )}
              </section>
            );
          })}
          {selected.supplemental && <details className="evidence-disclosure"><summary>Supplemental diagnostics and source links</summary><pre className="evidence-json">{JSON.stringify(selected.supplemental,null,2)}</pre></details>}
          {selected.diagnostics.map((note) => (
            <Notice key={note}>{note}</Notice>
          ))}
        </Modal>
      )}
    </div>
  );
}

export function ActionPlan({
  report,
  showEvidence,
  toast,
}: {
  report: Report;
  showEvidence: (ids: string[]) => void;
  toast: (text: string) => void;
}) {
  return (
    <div className="view-enter">
      <div className="plan-intro">
        <span className="plan-symbol">
          <Sparkles size={24} />
        </span>
        <div>
          <span className="eyebrow">THIS WEEK</span>
          <h2>Your weekly action plan</h2>
          <p>A focused plan, grounded in what we actually found.</p>
        </div>
        <span className="source-badge">
          <span className="status-dot" />
          {report.recommendation_source === "ai"
            ? "AI-assisted plan"
            : "Rule-based plan"}
        </span>
      </div>
      <Notice>{report.recommendation_note}</Notice>
      <div className="action-list">
        {report.recommendations.map((rec, index) => {
          const issues = report.issues.filter((issue) =>
            rec.issue_ids.includes(issue.id),
          );
          const pages = [...new Set(issues.flatMap(issue => Array.isArray(issue.evidence?.source_pages) ? issue.evidence.source_pages.map(String) : [issue.page_url]))];
          const original = rec.metadata
            ? report.pages.find((page) => page.url === rec.metadata?.page_url)
                ?.checks.metadata?.details
            : null;
          return (
            <section
              className="card action-card"
              key={`${rec.action}-${index}`}
            >
              <div className="action-number">0{index + 1}</div>
              <div className="action-main">
                <div className="action-heading">
                  <strong>{rec.priority === "critical" ? "P0" : rec.priority === "high" ? "P1" : "P2"}</strong> <Badge severity={rec.priority} />
                  <span className="microcopy">
                    {pages.length} affected page{pages.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <h3>{rec.action}</h3>
                <p>{rec.reason}</p>
                <div className="action-fix">
                  <label>THE NEXT STEP</label>
                  <p>{rec.suggested_fix}</p>
                </div>
                <div className="affected-pages">
                  {pages.slice(0, 4).map((url) => (
                    <span key={url}>
                      <FileText size={12} />
                      {pagePath(url)}
                    </span>
                  ))}
                  {pages.length > 4 && <span>+{pages.length - 4} more</span>}
                </div>
                {rec.metadata && (
                  <div className="metadata-proposal">
                    <div>
                      <h4>Suggested metadata</h4>
                      <span className="category-tag">
                        Proposal · review before publishing
                      </span>
                    </div>
                    <p className="microcopy">
                      {pagePath(rec.metadata.page_url)}
                    </p>
                    <label>Original title</label>
                    <p className="original-text">
                      {String(original?.title || "(missing)")}
                    </p>
                    <label>
                      Proposed title · {rec.metadata.title.length} characters
                    </label>
                    <div className="copy-row">
                      <p>{rec.metadata.title}</p>
                      <CopyButton text={rec.metadata.title} onCopy={toast} />
                    </div>
                    <label>Original description</label>
                    <p className="original-text">
                      {String(original?.description || "(missing)")}
                    </p>
                    <label>
                      Proposed description · {rec.metadata.description.length}{" "}
                      characters
                    </label>
                    <div className="copy-row">
                      <p>{rec.metadata.description}</p>
                      <CopyButton
                        text={rec.metadata.description}
                        onCopy={toast}
                      />
                    </div>
                  </div>
                )}
                <div className="action-footer">
                  <button
                    className="text-button"
                    onClick={() => showEvidence(rec.issue_ids)}
                  >
                    View {rec.issue_ids.length} linked finding
                    {rec.issue_ids.length !== 1 ? "s" : ""}
                    <ArrowUpRight size={14} />
                  </button>
                  <CopyButton
                    text={`${rec.action}\n\n${rec.reason}\n\n${rec.suggested_fix}\n\nAffected pages:\n${pages.join("\n")}`}
                    onCopy={toast}
                  />
                </div>
              </div>
            </section>
          );
        })}
      </div>
      {!report.recommendations.length && (
        <section className="card">
          <Empty title="Nothing to fix in the measured checks">
            Review your audit coverage, then come back after your next website
            update.
          </Empty>
        </section>
      )}
      <div className="plan-footnote">
        <ShieldCheck size={16} />
        Scores and priorities come from the SEO engine. AI can explain the
        evidence, but cannot change it.
      </div>
    </div>
  );
}

export function CoverageView({ report }: { report: Report }) {
  const coverage = report.coverage;
  const unknown = report.links.filter((link) => link.status === "unknown");
  return (
    <div className="view-enter">
      <div className="section-heading">
        <div>
          <h2>Know what’s behind the numbers</h2>
          <p>
            A transparent view of the scope, gaps, and limits of this audit.
          </p>
        </div>
        <span
          className={`badge ${report.score_status === "partial" ? "medium" : "passing"}`}
        >
          {report.score_status === "partial"
            ? "Partial coverage"
            : "Complete within scope"}
        </span>
      </div>
      <div className="coverage-stats">
        {[
          {
            label: "Pages analyzed",
            value: coverage.pages_analyzed,
            total: coverage.page_limit,
            note: "Configured crawl limit",
          },
          {
            label: "Links verified",
            value: coverage.links_verified,
            total: coverage.links_discovered,
            note: "Unique internal destinations",
          },
          {
            label: "Headers inspected",
            value: coverage.headers_checked,
            total: coverage.pages_analyzed,
            note: "X-Robots-Tag coverage",
          },
        ].map((stat) => (
          <section className="card coverage-stat" key={stat.label}>
            <span>{stat.label}</span>
            <strong>
              {stat.value}
              <small> / {stat.total}</small>
            </strong>
            <div className="meter">
              <span
                style={{
                  width: `${stat.total ? (stat.value / stat.total) * 100 : 0}%`,
                }}
              />
            </div>
            <p>{stat.note}</p>
          </section>
        ))}
      </div>
      <div className="coverage-grid">
        <section className="card coverage-notes">
          <h3>
            <Info size={18} />
            What this report covers
          </h3>
          <ul>
            <li>
              Up to {coverage.page_limit} HTML pages on the same hostname.
            </li>
            <li>
              {reportKeys(report).length} scoring categories. {coverage.link_occurrences != null && `${coverage.link_occurrences} internal link occurrences discovered.`}
            </li>
            <li>
              {coverage.links_verified} verified destinations;{" "}
              {coverage.links_unknown} unknown.
            </li>
            <li>{coverage.pages_failed} failed or restricted page fetches.</li>
            <li>
              {coverage.crawl_complete
                ? "Crawler finished its requested scope."
                : "Crawl ended before its full scope was completed."}
            </li>
          </ul>
        </section>
        <section className="card coverage-notes">
          <h3>
            <AlertTriangle size={18} />
            Keep in mind
          </h3>
          <ul>
            <li>This score reflects the scanned pages, not search rankings.</li>
            <li>
              Indexability is eligibility, not confirmation of Google indexing.
            </li>
            <li>One H1 is a consistency rule used by this project.</li>
            <li>
              JSON-LD uses a lightweight product-field check, not a rich-results
              guarantee.
            </li>
            <li>Unknown checks are excluded, never treated as passing.</li>
          </ul>
        </section>
      </div>
      {coverage.warnings.map((warning) => (
        <Notice key={warning}>{warning}</Notice>
      ))}
      {!!report.links.length && <details className="card coverage-notes"><summary>All internal destination evidence</summary>
        {report.links.map(link=><div key={link.url}><ExternalLink url={link.url}/><p>HTTP {link.status_code ?? "unverified"} · {link.final_url || "Final destination unverified"} · {link.reason || link.status}</p>
          <details><summary>Source links and redirects</summary><pre className="evidence-json">{JSON.stringify(link,null,2)}</pre></details></div>)}
      </details>}
      {!!unknown.length && (
        <section className="card table-card">
          <div className="table-toolbar">
            <h3>Unverified destinations</h3>
            <span className="count-chip">{unknown.length}</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Destination</th>
                  <th>Why it’s unknown</th>
                  <th>Source pages</th>
                </tr>
              </thead>
              <tbody>
                {unknown.map((link) => (
                  <tr key={link.url}>
                    <td>
                      <ExternalLink url={link.url}>
                        {pagePath(link.url)}
                      </ExternalLink>
                    </td>
                    <td>{link.reason}</td>
                    <td>
                      {link.source_pages.map((source) => (
                        <span className="table-url" key={source}>
                          {pagePath(source)}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {!!coverage.failures.length && (
        <section className="card coverage-notes">
          <h3>Failed or blocked pages</h3>
          {coverage.failures.map((failure, index) => (
            <div className="failure-row" key={`${failure.url}-${index}`}>
              <strong>{failure.url}</strong>
              <p>{failure.reason}</p>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
