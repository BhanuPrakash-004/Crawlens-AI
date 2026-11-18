import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  LayoutDashboard,
  ListFilter,
  Files,
  Sparkles,
  ShieldCheck,
  Settings2,
  BookOpen,
  ChevronDown,
  Globe2,
  Plus,
  Download,
  X,
  Menu,
  RefreshCw,
  AlertCircle,
  Check,
  CircleHelp,
  LoaderCircle,
  Network,
  Share2,
  History,
} from "lucide-react";
import type {
  Health,
  Job,
  MetricKey,
  IssueCategory,
  Report,
  View,
} from "./types";
import { api, downloadReport, host } from "./lib";
import { Brand, Modal } from "./components/Shared";
import { AuditHistory } from "./components/AuditHistory";
import { Overview } from "./components/Overview";
import {
  IssueExplorer,
  PagesView,
  ActionPlan,
  CoverageView,
} from "./components/ReportViews";
import { AuditProgress } from "./components/AuditProgress";
import { Settings, Methodology } from "./components/Settings";
import { SiteEssentials, SocialPresence } from "./components/SiteChecks";

const NAV: { key: View; name: string; icon: typeof LayoutDashboard }[] = [
  { key: "history", name: "Audit history", icon: History },
  { key: "overview", name: "Overview", icon: LayoutDashboard },
  { key: "issues", name: "Issue explorer", icon: ListFilter },
  { key: "pages", name: "Analyzed pages", icon: Files },
  { key: "essentials", name: "Site essentials", icon: Network },
  { key: "social", name: "Social presence", icon: Share2 },
  { key: "plan", name: "Action plan", icon: Sparkles },
  { key: "coverage", name: "Audit coverage", icon: ShieldCheck },
];
const TITLE: Record<View, string> = {
  history: "Your audits, all in one place.",
  overview: "Your website. A clearer picture.",
  issues: "Find it. Understand it. Fix it.",
  pages: "A closer look at every page.",
  essentials: "Make your website discoverable.",
  social: "Your presence, beyond your site.",
  plan: "Turn your findings into progress.",
  coverage: "See the scope behind the score.",
};
function storedJob() {
  try {
    return sessionStorage.getItem("crawlens-job");
  } catch {
    return null;
  }
}
function storeJob(id: string | null) {
  try {
    if (id) sessionStorage.setItem("crawlens-job", id);
    else sessionStorage.removeItem("crawlens-job");
  } catch {
    /* Storage is optional. */
  }
}

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [report, setReport] = useState<Report | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [jobId, setJobId] = useState<string | null>(storedJob);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pollFailed, setPollFailed] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [metric, setMetric] = useState<IssueCategory | "all">("all");
  const [selectedIds, setSelectedIds] = useState<string[] | null>(null);
  const [dialog, setDialog] = useState<
    "settings" | "methodology" | "export" | null
  >(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);
  const previousView = useRef(view);
  const focusNewAudit = useRef(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busy =
    submitting ||
    (!!jobId && (!job || job.status === "queued" || job.status === "running"));

  useEffect(() => {
    if (previousView.current === view) return;
    previousView.current = view;
    window.scrollTo({ top: 0, behavior: "instant" });
    if (focusNewAudit.current) input.current?.focus({ preventScroll: true });
    else pageHeading.current?.focus({ preventScroll: true });
    focusNewAudit.current = false;
  }, [view]);

  useEffect(() => {
    if (!mobileNav) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebar.current?.querySelector<HTMLButtonElement>(".mobile-close")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (document.querySelector("dialog[open]")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNav(false);
      }
      if (event.key !== "Tab") return;
      const buttons = Array.from(
        sidebar.current?.querySelectorAll<HTMLButtonElement>(
          "button:not(:disabled)",
        ) ?? [],
      ).filter((el) => el.getClientRects().length);
      const first = buttons[0],
        last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    const resize = () => {
      if (window.innerWidth > 760) setMobileNav(false);
    };
    document.addEventListener("keydown", keydown);
    window.addEventListener("resize", resize);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      window.removeEventListener("resize", resize);
      if (
        !document.querySelector("dialog[open]") &&
        sidebar.current?.contains(document.activeElement)
      )
        menuButton.current?.focus();
    };
  }, [mobileNav]);

  useEffect(() => {
    if (dialog) setMobileNav(false);
  }, [dialog]);

  const refreshHealth = async () => {
    setRefreshing(true);
    try {
      setHealth(await api<Health>("/api/health"));
    } catch {
      setHealth(null);
    } finally {
      setRefreshing(false);
    }
  };
  useEffect(() => {
    void refreshHealth();
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    let stopped = false;
    setPollFailed(false);
    async function poll() {
      try {
        const result = await api<Job>(`/api/audits/${jobId}`, {
          signal: controller.signal,
        });
        if (stopped) return;
        setJob(result);
        failures = 0;
        if (result.status === "completed" && result.report) {
          setReport(result.report);
          setUrl(result.website);
          setJobId(null);
          setError("");
          setView("overview");
          setMetric("all");
          setSelectedIds(null);
        } else if (result.status === "failed") {
          setError(result.error ?? "The audit failed. Please try again.");
          setJobId(null);
          storeJob(null);
        } else timer = setTimeout(poll, 1800);
      } catch (error) {
        if (stopped) return;
        failures++;
        if (failures < 3) timer = setTimeout(poll, 2500);
        else {
          setPollFailed(true);
          setError(
            error instanceof Error
              ? error.message
              : "Could not load audit status.",
          );
        }
      }
    }
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, pollVersion]);

  function toast(message: string) {
    setToastMessage(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMessage(""), 3500);
  }
  function navigate(next: View) {
    setView(next);
    setMobileNav(false);
    if (next === "issues") {
      setSelectedIds(null);
      setMetric("all");
    }
  }
  function selectMetric(key: MetricKey) {
    if (key === "site_health") { navigate("essentials"); return; }
    setMetric(key);
    setSelectedIds(null);
    setView("issues");
  }
  function showEvidence(ids: string[]) {
    setMetric("all");
    setSelectedIds(ids);
    setView("issues");
  }
  function newAudit() {
    focusNewAudit.current = view !== "overview";
    setMobileNav(false);
    setView("overview");
    setReport(null);
    setUrl("");
    storeJob(null);
    input.current?.focus();
    input.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    let target = url.trim();
    if (!/^\w+:/.test(target)) target = "https://" + target;
    try {
      const parsed = new URL(target);
      if (
        !["http:", "https:"].includes(parsed.protocol) ||
        !parsed.hostname ||
        /\s/.test(target)
      )
        throw new Error();
    } catch {
      setError(
        "Enter a valid public website URL, such as https://example.com.",
      );
      input.current?.focus();
      return;
    }
    setSubmitting(true);
    setJob(null);
    try {
      const accepted = await api<{ audit_id: string }>("/api/audits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: target }),
      });
      setReport(null);
      setUrl(target);
      storeJob(accepted.audit_id);
      setJobId(accepted.audit_id);
      setView("overview");
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "The audit could not be started.",
      );
    } finally {
      setSubmitting(false);
    }
  }
  async function openAudit(id: string) {
    setError("");
    try {
      const saved = await api<Job>(`/api/audits/${id}`);
      setJob(saved);
      setUrl(saved.website);
      if (saved.status === "running" || saved.status === "queued") {
        setJobId(id);
        storeJob(id);
        setView("overview");
      } else if (saved.report) {
        setReport(saved.report);
        setView("overview");
        setMetric("all");
        setSelectedIds(null);
        storeJob(id);
        if (saved.error) setError(saved.error);
      } else
        setError(
          saved.error ||
            "This audit has no completed report. You can run it again using the URL above.",
        );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this audit.");
    }
  }
  function exportReport(format: "json" | "csv") {
    if (report) {
      downloadReport(report, format);
      toast(`${format.toUpperCase()} report downloaded`);
      setDialog(null);
    }
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {mobileNav && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside
        id="workspace-navigation"
        ref={sidebar}
        className={`sidebar ${mobileNav ? "open" : ""}`}
        aria-label="Workspace navigation"
      >
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-close"
            onClick={() => setMobileNav(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>
        <span className="nav-label">ANALYZE</span>
        <nav aria-label="Main navigation">
          {NAV.map(({ key, name, icon: Icon }) => (
            <button
              className={view === key ? "active" : ""}
              aria-current={view === key ? "page" : undefined}
              key={key}
              onClick={() => navigate(key)}
            >
              <Icon size={18} />
              <span>{name}</span>
              {key === "issues" && !!report?.issues.length && (
                <span className="nav-count">{report.issues.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button onClick={() => setDialog("methodology")}>
            <BookOpen size={18} />
            Scoring guide
            <ArrowUpRight size={13} />
          </button>
          <button onClick={() => setDialog("settings")}>
            <Settings2 size={18} />
            Settings
          </button>
        </div>
      </aside>
      <div className="main-shell" inert={mobileNav}>
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-toggle"
              aria-label="Open navigation"
              aria-controls="workspace-navigation"
              aria-expanded={mobileNav}
              ref={menuButton}
              onClick={() => setMobileNav(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{NAV.find((item) => item.key === view)?.name}</strong>
          </div>
          <div className="topbar-actions">
            <button
              className="api-status"
              onClick={() => setDialog("settings")}
            >
              <span className={`status-dot ${!health ? "offline" : ""}`} />
              {health ? "API connected" : "API offline"}
            </button>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label="Open scoring guide"
              onClick={() => setDialog("methodology")}
            >
              <CircleHelp size={19} />
            </button>
            <button
              className="icon-button"
              aria-label="Connection settings"
              onClick={() => setDialog("settings")}
            >
              <Settings2 size={19} />
            </button>
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                YOUR SEO WORKSPACE
              </div>
              <h1 ref={pageHeading} tabIndex={-1}>
                {TITLE[view]}
              </h1>
              <p>
                {view === "overview"
                  ? "Know what’s working, what needs attention, and exactly where to start."
                  : view === "essentials"
                    ? "Inspect crawler access and sitemap discovery, with the evidence behind each result."
                    : view === "social"
                      ? "Discover the social profiles linked from your website and where they appear."
                      : "Explore your audit evidence and make your next website update count."}
              </p>
            </div>
            <button
              className="secondary-button new-audit"
              onClick={newAudit}
              disabled={busy}
            >
              <Plus size={16} />
              New audit
            </button>
          </div>
          <section className="url-panel" aria-label="Start a website audit">
            <form onSubmit={submit}>
              <label className="url-input-wrap" htmlFor="website-url">
                <Globe2 size={20} />
                <input
                  ref={input}
                  id="website-url"
                  aria-label="Website URL"
                  inputMode="url"
                  autoComplete="url"
                  spellCheck={false}
                  placeholder="https://your-website.com"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={busy}
                  aria-describedby="url-hint"
                  aria-invalid={!!error && !busy}
                  required
                />
              </label>
              <button className="primary-button" type="submit" disabled={busy}>
                {busy ? (
                  <>
                    <LoaderCircle size={17} className="spin" />
                    Audit in progress
                  </>
                ) : (
                  <>
                    Analyze website
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </form>
            <div className="url-panel-footer">
              <span id="url-hint">
                <ShieldCheck size={13} />
                Up to {health?.page_limit ?? 20} pages
                <span className="inline-dot">·</span>SEO, site essentials &
                social links
              </span>
              <span className="history-hint">
                Reports are saved automatically
              </span>
            </div>
          </section>
          {error && (
            <div className="error-banner" role="alert">
              <AlertCircle size={19} />
              <div>
                <strong>
                  {busy
                    ? "We lost the connection"
                    : "Something needs your attention"}
                </strong>
                <p>{error}</p>
                {pollFailed && (
                  <div className="error-actions">
                    <button
                      onClick={() => {
                        setError("");
                        setPollVersion((value) => value + 1);
                      }}
                      className="text-button"
                    >
                      <RefreshCw size={14} />
                      Reconnect to audit
                    </button>
                    <button
                      className="text-button"
                      onClick={() => {
                        setJobId(null);
                        setJob(null);
                        storeJob(null);
                        setError("");
                        setPollFailed(false);
                      }}
                    >
                      Return to workspace
                    </button>
                  </div>
                )}
                {!busy && (
                  <button
                    className="text-button"
                    onClick={() => setDialog("settings")}
                  >
                    Check connection settings
                    <ArrowRight size={14} />
                  </button>
                )}
              </div>
              {!busy && (
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setError("")}
                >
                  <X size={17} />
                </button>
              )}
            </div>
          )}
          {view === "history" ? (
            <AuditHistory openAudit={openAudit} busy={busy} />
          ) : busy ? (
            <AuditProgress
              stage={job?.stage ?? "queued"}
              website={job?.website ?? url}
            />
          ) : report ? (
            <>
              <div className="report-heading">
                <div className="report-identity">
                  <span className="site-mark">
                    <Globe2 size={21} />
                  </span>
                  <div>
                    <h2>
                      {host(report.website)}
                      <span className="report-type live">
                        <Check size={12} />
                        Saved audit
                      </span>
                    </h2>
                    <p>
                      {`${new Date(report.completed_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · ${report.duration_seconds}s audit`}
                    </p>
                  </div>
                </div>
                <button
                  className="secondary-button export-button"
                  onClick={() => setDialog("export")}
                >
                  <Download size={15} />
                  Export report
                  <ChevronDown size={14} />
                </button>
              </div>
              {view === "overview" && (
                <Overview
                  report={report}
                  navigate={navigate}
                  selectMetric={selectMetric}
                  showEvidence={showEvidence}
                  methodology={() => setDialog("methodology")}
                />
              )}
              {view === "issues" && (
                <IssueExplorer
                  key={report.completed_at}
                  report={report}
                  metric={metric}
                  setMetric={setMetric}
                  selectedIds={selectedIds}
                  clearIds={() => setSelectedIds(null)}
                />
              )}
              {view === "pages" && <PagesView report={report} />}
              {view === "essentials" && <SiteEssentials report={report} />}
              {view === "social" && (
                <SocialPresence report={report} toast={toast} />
              )}
              {view === "plan" && (
                <ActionPlan
                  report={report}
                  showEvidence={showEvidence}
                  toast={toast}
                />
              )}
              {view === "coverage" && <CoverageView report={report} />}
              <footer className="page-footer">
                <span>
                  <span className="mini-brand">c.</span>Built on evidence. Made
                  for progress.
                </span>
                <span>
                  Stored in your local audit history
                  <span className="inline-dot">·</span>v1.2
                </span>
              </footer>
            </>
          ) : (
            <section className="card welcome-empty">
              <Globe2 size={36} />
              <h2>Your next insight starts here.</h2>
              <p>
                Enter a website URL to start. Your reports will be saved here,
                ready to revisit any time.
              </p>
              <button
                className="secondary-button"
                onClick={() => navigate("history")}
              >
                <History size={16} />
                View audit history
              </button>
            </section>
          )}
        </main>
      </div>
      {dialog === "settings" && (
        <Settings
          health={health}
          refreshing={refreshing}
          refresh={refreshHealth}
          close={() => setDialog(null)}
        />
      )}
      {dialog === "methodology" && (
        <Methodology report={report} close={() => setDialog(null)} />
      )}
      {dialog === "export" && report && (
        <Modal
          title="Take your insights with you"
          close={() => setDialog(null)}
        >
          <p className="modal-description">
            Download your saved audit for review or share the findings with your
            team.
          </p>
          <button
            className="export-option"
            onClick={() => exportReport("json")}
          >
            <span className="export-type">JSON</span>
            <span>
              <strong>Complete audit report</strong>
              <small>
                Scores, page evidence, link checks, and recommendations.
              </small>
            </span>
            <Download size={20} />
          </button>
          <button className="export-option" onClick={() => exportReport("csv")}>
            <span className="export-type csv">CSV</span>
            <span>
              <strong>Page-level issues</strong>
              <small>
                A spreadsheet-ready list of findings and suggested fixes.
              </small>
            </span>
            <Download size={20} />
          </button>
        </Modal>
      )}
      {toastMessage && (
        <div className="toast" role="status">
          <Check size={16} />
          {toastMessage}
          <button
            onClick={() => setToastMessage("")}
            aria-label="Dismiss notification"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
