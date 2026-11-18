import {
  ArrowRight,
  ArrowUpRight,
  FileText,
  Link2,
  ShieldCheck,
  Heading1,
  Braces,
  CircleHelp,
  AlertTriangle,
  Files,
  Sparkles,
  Network,
  Bot,
  Share2,
} from "lucide-react";
import type { Report, MetricKey, View } from "../types";
import { METRICS, reportKeys, CATEGORIES, pagePath } from "../lib";
import { Badge } from "./Shared";
import { CheckStatus } from "./SiteChecks";

export const metricIcons = {
  performance: AlertTriangle, canonical: Link2, site_health: Network, geo: Bot, media: Files,
  metadata: FileText,
  broken_links: Link2,
  indexability: ShieldCheck,
  headings: Heading1,
  structured_data: Braces,
};

export function Overview({
  report,
  navigate,
  selectMetric,
  methodology,
  showEvidence,
}: {
  report: Report;
  navigate: (view: View) => void;
  selectMetric: (key: MetricKey) => void;
  methodology: () => void;
  showEvidence: (ids: string[]) => void;
}) {
  const high = report.issues.filter(
    (issue) => issue.severity === "high",
  ).length;
  const score = report.overall_score;
  const checks = report.site_checks;
  return (
    <div className="view-enter overview">
      <div className="summary-grid">
        <section className="score-card">
          <div className="score-copy">
            <span className="overline">WEBSITE HEALTH</span>
            <h2>
              {score === null
                ? "More evidence needed."
                : report.classification === "Excellent"
                  ? "Looking good."
                  : report.classification === "Good"
                    ? "A solid foundation."
                    : "Room to grow."}
            </h2>
            <p>
              {report.executive_summary || (high
                ? `${high} high-priority findings need a closer look. Let’s start there.`
                : "Explore your measured checks and the opportunities ahead.")}
            </p>
            <button onClick={() => navigate("issues")}>
              Explore findings <ArrowRight size={16} />
            </button>
          </div>
          <div
            className="score-ring"
            role="img"
            aria-label={`SEO health score: ${score ?? "unknown"} out of 100`}
          >
            <svg viewBox="0 0 160 160" aria-hidden="true">
              <circle cx="80" cy="80" r="67" className="ring-track" />
              <circle
                cx="80"
                cy="80"
                r="67"
                className="ring-value"
                strokeDasharray={`${((score ?? 0) / 100) * 421} 421`}
              />
            </svg>
            <div>
              <strong>
                {score ?? "—"}
                <span>/100</span>
              </strong>
              <span>{report.classification}</span>
            </div>
          </div>
          <div className="score-card-footer">
            <span>
              <span className="status-dot" />
              {report.score_status === "partial"
                ? "Partial evidence · review coverage"
                : "Complete within audit scope"}
            </span>
            <button
              aria-label="How your score is calculated"
              onClick={methodology}
            >
              <CircleHelp size={15} />
            </button>
          </div>
        </section>
        <div className="summary-stats">
          <button className="stat-tile" onClick={() => navigate("pages")}>
            <span className="stat-icon">
              <Files size={19} />
            </span>
            <ArrowUpRight className="stat-arrow" size={16} />
            <strong>{report.pages_crawled}</strong>
            <span>Pages analyzed</span>
            <small>of {report.coverage.page_limit} page crawl limit</small>
          </button>
          <button className="stat-tile" onClick={() => navigate("issues")}>
            <span className="stat-icon orange">
              <AlertTriangle size={19} />
            </span>
            <ArrowUpRight className="stat-arrow" size={16} />
            <strong>
              {report.issues.length}
              <span className="stat-sub">{high} high</span>
            </strong>
            <span>Issues to review</span>
            <small>{(["critical","high","medium","low"] as const).map(level => report.issues.filter(i=>i.severity===level).length + " " + level).join(" · ")}</small>
          </button>
          <button
            className="stat-tile wide-stat"
            onClick={() => navigate("coverage")}
          >
            <span className="stat-icon">
              <Link2 size={19} />
            </span>
            <div>
              <strong>
                {report.coverage.links_verified}
                <span className="stat-denominator">
                  {" "}
                  / {report.coverage.links_discovered}
                </span>
              </strong>
              <span>Internal destinations verified</span>
            </div>
            <ArrowUpRight size={17} />
          </button>
        </div>
      </div>
      <div className="insights-grid">
        <section className="card breakdown-card">
          <div className="panel-heading">
            <div>
              <h2>SEO breakdown</h2>
              <p>{reportKeys(report).length} metrics · {Object.values(report.metrics).filter(m => m.evaluated > 0).length} measured</p>
            </div>
            <button
              className="icon-button"
              onClick={methodology}
              aria-label="View metric definitions"
            >
              <CircleHelp size={18} />
            </button>
          </div>
          <div className="metric-column-labels">
            <span>CATEGORY</span>
            <span>PASS RATE</span>
          </div>
          {reportKeys(report).map((key) => {
            const metric = report.metrics[key];
            const Icon = metricIcons[key];
            return (
              <button
                className="metric-row"
                key={key}
                onClick={() => selectMetric(key)}
                aria-label={`View ${METRICS[key].short} findings`}
              >
                <span className="metric-icon">
                  <Icon size={19} />
                </span>
                <div className="metric-info">
                  <strong>{METRICS[key].name}</strong>
                  <span>
                    {metric.passing} of {metric.evaluated}{" "}
                    {metric.unit ?? (key === "broken_links" ? "links" : "pages")} passing
                    {metric.unknown ? ` · ${metric.unknown} unknown` : ""}
                    {metric.not_applicable
                      ? ` · ${metric.not_applicable} N/A`
                      : ""}
                    {metric.review_required
                      ? ` · ${metric.review_required} review`
                      : ""}
                  </span>
                </div>
                <div className="metric-rate">
                  <strong>
                    {metric.score === null ? "—" : `${metric.score}%`}
                  </strong>
                  <div className="meter">
                    <span style={{ width: `${metric.score ?? 0}%` }} />
                  </div>
                </div>
                <ArrowUpRight size={15} />
              </button>
            );
          })}
          <button className="panel-footnote" onClick={methodology}>
            <ShieldCheck size={14} />
            {report.coverage.measured_weight != null ? `${report.coverage.measured_weight}% of configured weight measured · View calculation` : "Scores are calculated from observed evidence."}
          </button>
        </section>
        <section className="card priorities-card">
          <div className="panel-heading">
            <div>
              <h2>Start here</h2>
              <p>Your highest-priority findings.</p>
            </div>
            <span className="orange-icon">
              <Sparkles size={20} />
            </span>
          </div>
          {report.issues.length ? (
            <div className="priority-list">
              {report.issues.slice(0, 3).map((issue, index) => (
                <button
                  className="priority-item"
                  key={issue.id}
                  onClick={() => showEvidence([issue.id])}
                >
                  <span className="priority-index">0{index + 1}</span>
                  <div>
                    <div className="priority-meta">
                      <span>{CATEGORIES[issue.metric].short}</span>
                      <Badge severity={issue.severity} />
                    </div>
                    <h3>{issue.title}</h3>
                    <span className="priority-path">
                      {pagePath(issue.target_url || issue.page_url)}
                    </span>
                  </div>
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <p className="clear-findings">
              No failed checks in the measured scope. Review coverage for any
              unknown results.
            </p>
          )}
          <button className="plan-cta" onClick={() => navigate("plan")}>
            <span>
              <Sparkles size={16} />
              Your next steps, organized
            </span>
            <ArrowRight size={18} />
          </button>
        </section>
      </div>
      <div className="section-heading essentials-heading">
        <div>
          <h2>Beyond the page</h2>
          <p>The foundations that help people and crawlers find you.</p>
        </div>

      </div>
      <div className="essentials-grid">
        {(
          [
            {
              title: "robots.txt",
              description: "Control search crawler access",
              icon: Bot,
              key: "robots_txt",
            },
            {
              title: "sitemap.xml",
              description: "Help search engines discover URLs",
              icon: Network,
              key: "sitemap",
            },
          ] as const
        ).map((item) => {
          const Icon = item.icon;
          const check = checks?.[item.key];
          return (
            <button
              className="card essential-preview"
              key={item.key}
              onClick={() => navigate("essentials")}
            >
              <div>
                <span className="essential-icon">
                  <Icon size={22} />
                </span>
                <CheckStatus status={check?.status ?? "unknown"} />
              </div>
              <h3>
                {item.title}
                <ArrowUpRight size={17} />
              </h3>
              <p>{item.description}</p>
              <span className="essential-bottom">
                {item.key === "robots_txt"
                  ? checks?.robots_txt.status_code
                    ? `HTTP ${checks.robots_txt.status_code} · View crawler rules`
                    : "View file evidence"
                  : checks?.sitemap.urls_discovered
                    ? `${checks.sitemap.urls_discovered} URLs discovered`
                    : "View sitemap evidence"}
                <ArrowRight size={15} />
              </span>
            </button>
          );
        })}
        <button
          className="card essential-preview"
          onClick={() => navigate("social")}
        >
          <div>
            <span className="essential-icon">
              <Share2 size={22} />
            </span>
            <CheckStatus
              status={
                checks?.social.status === "found"
                  ? "passed"
                  : checks?.social.status === "not_found"
                    ? "warning"
                    : "unknown"
              }
              label={
                checks?.social.status === "found"
                  ? `${checks.social.profiles.length} profiles`
                  : checks?.social.status === "not_found"
                    ? "None found"
                    : "Not checked"
              }
            />
          </div>
          <h3>
            Social presence
            <ArrowUpRight size={17} />
          </h3>
          <p>Connect your website to your profiles</p>
          <span className="essential-bottom">
            {checks?.social.profiles.length
              ? checks.social.profiles
                  .map((p) => p.platform)
                  .filter((p, i, a) => a.indexOf(p) === i)
                  .slice(0, 3)
                  .join(" · ")
              : "Discover linked social profiles"}
            <ArrowRight size={15} />
          </span>
        </button>
      </div>
    </div>
  );
}
