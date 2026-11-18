import { useState } from "react";
import {
  Bot,
  Network,
  Check,
  AlertTriangle,
  CircleHelp,
  Share2,
  ArrowUpRight,
  FileText,
  Globe2,
  Link2,
} from "lucide-react";
import type { Report, SiteStatus } from "../types";
import { pagePath } from "../lib";
import { CopyButton, Empty, ExternalLink, Notice } from "./Shared";

export function CheckStatus({
  status,
  label,
}: {
  status: SiteStatus;
  label?: string;
}) {
  const Icon =
    status === "passed"
      ? Check
      : status === "unknown"
        ? CircleHelp
        : AlertTriangle;
  return (
    <span className={`check-badge ${status}`}>
      <Icon size={13} />
      {label ??
        {
          passed: "Passed",
          warning: "Warning",
          error: "Failed",
          unknown: "Review",
        }[status]}
    </span>
  );
}

export function SiteEssentials({ report }: { report: Report }) {
  const [agent, setAgent] = useState("Googlebot");
  const checks = report.site_checks;
  if (!checks)
    return (
      <section className="card">
        <Empty title="Site checks aren’t in this report">
          Run a new audit to inspect robots.txt and sitemap.xml.
        </Empty>
      </section>
    );
  const { robots_txt: robots, sitemap } = checks;
  const permissions = robots.permissions.filter((item) => item.agent === agent);
  return (
    <div className="view-enter site-essentials">
      <Notice>
        {report.metrics.site_health ? "Robots and sitemap evidence contribute to the site health metric. HTTPS, social metadata and llms.txt are additional diagnostics." : "This saved audit treats site files as additional diagnostics."}
      </Notice>
      {checks.https && (
        <section className="card coverage-notes">
          <h3>HTTPS & secure transport</h3>
          <p>{checks.https.summary}</p>
          {report.pages.some(p=>p.supplemental?.mixed_content?.length) && <details><summary>Mixed content on HTTPS pages</summary>{report.pages.filter(p=>p.supplemental?.mixed_content?.length).map(p=><div key={p.url}><ExternalLink url={p.url}/><ul>{p.supplemental!.mixed_content!.map((url,i)=><li key={i}>{url}</li>)}</ul></div>)}</details>}
          <details>
            <summary>Connection evidence</summary>
            <pre className="evidence-json">
              {JSON.stringify(checks.https, null, 2)}
            </pre>
          </details>
        </section>
      )}
      {checks.llms_txt?.summary && <section className="card coverage-notes"><h3>Optional llms.txt</h3><p>{checks.llms_txt.status} · {checks.llms_txt.summary}</p>{checks.llms_txt.preview && <details><summary>File preview</summary><pre className="evidence-json">{checks.llms_txt.preview}</pre></details>}</section>}
      <div className="file-summary-grid">
        <section className="card file-summary">
          <span className="essential-icon">
            <Bot size={25} />
          </span>
          <div>
            <span className="overline">CRAWLER ACCESS</span>
            <h2>robots.txt</h2>
          </div>
          <CheckStatus status={robots.status} />
          <p>{robots.summary}</p>
          <ExternalLink
            url={robots.url || new URL("/robots.txt", report.website).href}
          />
          <div className="file-stats">
            <span>
              <strong>{robots.status_code ?? "—"}</strong>HTTP status
            </span>
            <span>
              <strong>{robots.rules.length}</strong>Rules found
            </span>
            <span>
              <strong>{robots.sitemap_urls.length}</strong>Sitemaps declared
            </span>
          </div>
        </section>
        <section className="card file-summary">
          <span className="essential-icon">
            <Network size={25} />
          </span>
          <div>
            <span className="overline">URL DISCOVERY</span>
            <h2>sitemap.xml</h2>
          </div>
          <CheckStatus status={sitemap.status} />
          <p>{sitemap.summary}</p>
          <span className="microcopy">
            Declared sitemaps first; /sitemap.xml when none are declared.
          </span>
          <div className="file-stats">
            <span>
              <strong>{sitemap.files.length}</strong>File records
            </span>
            <span>
              <strong>{sitemap.urls_discovered}</strong>URLs discovered
            </span>
            <span>
              <strong>
                {sitemap.scanned_pages_listed}
                <small>/{report.pages_crawled}</small>
              </strong>
              Scanned pages listed
            </span>
          </div>
        </section>
      </div>
      <section className="card robots-detail">
        <div className="panel-heading">
          <div>
            <h2>Inside your robots.txt</h2>
            <p>The retrieved file and its effect on checked URLs.</p>
          </div>
          <span className="category-tag">
            {robots.content_truncated ? "Preview truncated" : "File evidence"}
          </span>
        </div>
        <div className="robots-columns">
          <div className="robots-source">
            <div>
              <FileText size={15} />
              robots.txt{" "}
              <span>
                {robots.content
                  ? `${robots.content.split("\n").length} preview lines`
                  : "No file content"}
              </span>
            </div>
            <pre>
              {robots.content ||
                "No robots.txt content is available for this audit.\nSee the status and request evidence above."}
            </pre>
          </div>
          <div className="crawler-access">
            <div className="access-heading">
              <h3>Crawler permissions</h3>
              <select
                aria-label="Select search crawler"
                value={agent}
                onChange={(e) => setAgent(e.target.value)}
              >
                {Array.from(new Set([agent,...robots.permissions.map(p=>p.agent)])).map(a=><option key={a}>{a}</option>)}
              </select>
            </div>
            <p className="microcopy">
              For the audit URL and analyzed pages only.
            </p>
            <div className="permission-list">
              {permissions.length ? (
                permissions.map((item) => (
                  <div key={item.page_url}>
                    <span title={item.page_url}>
                      {pagePath(item.page_url)}
                      {item.matched_rule && <small>{item.matched_rule}</small>}
                    </span>
                    <CheckStatus
                      status={item.allowed ? "passed" : "warning"}
                      label={item.allowed ? "Allowed" : "Blocked"}
                    />
                  </div>
                ))
              ) : (
                <p className="no-evidence">
                  Permissions were not evaluated.{" "}
                  {robots.status_code === 404 || robots.status_code === 410
                    ? "A missing file declares no crawl restrictions."
                    : "A reliable robots file is required."}
                </p>
              )}
            </div>
          </div>
        </div>
        {robots.warnings.map((note, i) => (
          <Notice key={i}>{note}</Notice>
        ))}
      </section>
      <section className="card sitemap-details">
        <div className="panel-heading">
          <div>
            <h2>Sitemap inspection</h2>
            <p>
              Validate file structure, follow indexes, and check URL coverage.
            </p>
          </div>
          <span className="category-tag">Up to {sitemap.file_limit} files</span>
        </div>
        {sitemap.visited != null && <p className="microcopy sitemap-counts">{sitemap.declared} declared · {sitemap.visited} visited · {sitemap.nested} nested discovered · {sitemap.successful} passed · {sitemap.failed} failed · {sitemap.pending} queued</p>}
        {!!sitemap.page_coverage?.length && <details className="evidence-disclosure"><summary>Coverage by scanned page</summary>{sitemap.page_coverage.map(p=><p key={p.url}><ExternalLink url={p.url}/> · {p.status}<br/>{p.reason}</p>)}</details>}
        {sitemap.external_hosts && Object.keys(sitemap.external_hosts).length > 0 && <p>Outside-scope entries by hostname: {Object.entries(sitemap.external_hosts).map(([h,n])=>h+" ("+n+")").join(", ")}</p>}
        {sitemap.files.length ? (
          <div className="sitemap-files">
            {sitemap.files.map((file, i) => (
              <div className="sitemap-file" key={`${file.url}-${i}`}>
                <span className="file-icon">
                  <Network size={21} />
                </span>
                <div>
                  <ExternalLink url={file.url} />
                  <p>{file.message}</p>
                  <span className="microcopy">
                    HTTP {file.status_code ?? "unknown"}
                    {file.kind &&
                      ` · ${file.kind === "index" ? "Sitemap index" : "URL sitemap"} · ${file.entries} entries`}
                  </span>
                </div>
                <CheckStatus status={file.status} />
              </div>
            ))}
          </div>
        ) : (
          <div className="no-evidence">{sitemap.summary}</div>
        )}
        {!!sitemap.url_sample.length && (
          <details className="evidence-disclosure">
            <summary>
              Discovered URLs{" "}
              <span>
                {sitemap.urls_discovered > 50
                  ? "First 50 shown"
                  : sitemap.urls_discovered}
              </span>
            </summary>
            <div className="url-list">
              {sitemap.url_sample.map((url) => (
                <ExternalLink key={url} url={url}>
                  {pagePath(url)}
                </ExternalLink>
              ))}
            </div>
          </details>
        )}
        {!!sitemap.scanned_pages_missing.length && (
          <details className="evidence-disclosure">
            <summary>
              Scanned URLs not found in inspected sitemaps{" "}
              <span>{sitemap.scanned_pages_missing.length}</span>
            </summary>
            <p className="microcopy">
              {sitemap.complete
                ? "Not every page needs to be in a sitemap. Check whether these are important canonical URLs."
                : "Inspection is incomplete; these URLs may appear in files we could not verify."}
            </p>
            <div className="url-list">
              {sitemap.scanned_pages_missing.map((url) => (
                <ExternalLink key={url} url={url}>
                  {pagePath(url)}
                </ExternalLink>
              ))}
            </div>
          </details>
        )}
        {sitemap.warnings.map((note, i) => (
          <Notice key={i}>{note}</Notice>
        ))}
      </section>
    </div>
  );
}

const PLATFORM_MARKS: Record<string, string> = {
  LinkedIn: "in",
  Instagram: "ig",
  Facebook: "f",
  X: "𝕏",
  YouTube: "▶",
  TikTok: "♪",
  Pinterest: "P",
  Threads: "@",
  Bluesky: "b",
  GitHub: "gh",
};
export function SocialPresence({
  report,
  toast,
}: {
  report: Report;
  toast: (message: string) => void;
}) {
  const social = report.site_checks?.social;
  const profiles = social?.profiles ?? [];
  return (
    <div className="view-enter social-view">
      <section className="social-banner">
        <div className="social-banner-icon">
          <Share2 size={28} />
        </div>
        <div>
          <span className="overline">CONNECTED PRESENCE</span>
          <h2>
            {profiles.length
              ? `${profiles.length} social profiles. One website.`
              : "Find the profiles connected to your website."}
          </h2>
          <p>
            {social?.summary ?? "Run a new audit to discover linked profiles."}
          </p>
        </div>
        <Globe2 className="social-watermark" size={150} strokeWidth={0.7} />
      </section>
      {report.pages.some(p=>p.supplemental?.social_metadata) && <section className="card coverage-notes"><h3>Social sharing metadata</h3><p>Open a page to inspect its Open Graph and Twitter/X Card fields.</p>
        {report.pages.filter(p=>p.supplemental?.social_metadata).map(p=><details key={p.url}><summary>{pagePath(p.url)}</summary><dl>{Object.entries(p.supplemental!.social_metadata!).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value || "Missing"}</dd></div>)}</dl></details>)}</section>}
      <div className="social-stats">
        <div>
          <strong>{profiles.length}</strong>
          <span>Profiles discovered</span>
        </div>
        <div>
          <strong>{new Set(profiles.map((p) => p.platform)).size}</strong>
          <span>Social platforms</span>
        </div>
        <div>
          <strong>
            {social?.pages_with_profiles ?? 0}
            <small> / {social?.pages_checked ?? 0}</small>
          </strong>
          <span>Pages linking to profiles</span>
        </div>
      </div>
      <div className="section-heading">
        <div>
          <h2>Linked profiles</h2>
          <p>Profile links found in page HTML and structured data.</p>
        </div>
        <span className="subtle-label">ADDITIONAL CHECK · NOT SCORED</span>
      </div>
      {profiles.length ? (
        <div className="social-grid">
          {profiles.map((profile) => (
            <article className="card social-card" key={profile.url}>
              <div className="social-card-heading">
                <span className="platform-mark">
                  {PLATFORM_MARKS[profile.platform] ??
                    profile.platform.slice(0, 2)}
                </span>
                <div>
                  <h3>{profile.platform}</h3>
                  <span className="microcopy">Discovered on your website</span>
                </div>
                <a
                  href={profile.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="icon-button"
                  aria-label={`Open ${profile.platform} profile`}
                >
                  <ArrowUpRight size={19} />
                </a>
              </div>
              <a
                className="profile-url"
                href={profile.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {profile.url.replace("https://", "")}
                <ArrowUpRight size={14} />
              </a>
              <div className="social-evidence-tags">
                {profile.evidence_types.map((type) => (
                  <span className="category-tag" key={type}>
                    <Link2 size={12} />
                    {type === "sameAs"
                      ? "JSON-LD sameAs"
                      : type === "anchor"
                        ? "Page link"
                        : type}
                  </span>
                ))}
              </div>
              <details className="evidence-disclosure">
                <summary>
                  Source pages<span>{profile.source_pages.length}</span>
                </summary>
                <div className="url-list">
                  {profile.source_pages.map((url) => (
                    <ExternalLink key={url} url={url}>
                      {pagePath(url)}
                    </ExternalLink>
                  ))}
                </div>
              </details>
              <div className="social-card-footer">
                <span>Profile destination</span>
                <CopyButton text={profile.url} onCopy={toast} />
              </div>
            </article>
          ))}
        </div>
      ) : (
        <section className="card">
          <Empty
            title={
              social?.status === "not_found"
                ? "No social profiles found"
                : "Social presence hasn’t been verified"
            }
          >
            {social?.status === "not_found"
              ? "Add links to your official profiles in your header, footer, or contact page. Only the analyzed HTML pages were checked."
              : "Run an audit with accessible HTML pages to discover social links."}
          </Empty>
        </section>
      )}
      <Notice>
        Discovery does not verify account ownership, activity, or destination
        availability. Share buttons and content links are excluded where
        recognizable; only supported platforms and profile URL patterns are
        detected.
      </Notice>
    </div>
  );
}
