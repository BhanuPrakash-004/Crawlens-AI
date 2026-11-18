import type { Issue, IssueCategory, MetricKey, Report } from "./types";
export const METRICS: Record<
  MetricKey,
  { name: string; short: string; description: string; rule: string }
> = {
  performance: {name:"Core Web Vitals", short:"Performance", description:"Mobile load and interactivity.", rule:"Each measured vital is compared with its configured limit. INP requires URL-level field data."},
  canonical: {name:"Canonical & duplicate content", short:"Canonicals", description:"Preferred URLs and repeated content.", rule:"Declared canonical targets should resolve directly to an indexable page. Missing declarations and similarity findings require context."},
  site_health: {name:"Sitemaps & robots.txt", short:"Site health", description:"Discovery file health.", rule:"Checks the robots policy and the inspected sitemap tree. Incomplete inspection is shown as Review."},
  media: {name:"Image & video SEO", short:"Media", description:"Media accessibility and availability.", rule:"Checks image alternatives, video labels and captions, and media destinations. Decorative images can have empty alt text."},
  geo: {name:"AI search readiness", short:"AI readiness", description:"Technical content discovery.", rule:"Checks crawler access, extractable text and page headings. Actual citations and rankings are outside this assessment."},
  metadata: {
    name: "Titles & descriptions",
    short: "Metadata",
    description: "Make the right first impression in search.",
    rule: "Title: 30–60 characters. Description: 70–160 characters. Both must pass.",
  },
  broken_links: {
    name: "Internal links",
    short: "Internal links",
    description: "Keep every path to your content working.",
    rule: "Verified destinations with no HTTP 4xx or 5xx. Unverified links are excluded.",
  },
  indexability: {
    name: "Indexability & crawl access",
    short: "Indexability",
    description: "Help search engines discover your pages.",
    rule: "Search landing pages should be accessible with verified indexing directives. Utility paths are excluded and restrictions require intent review.",
  },
  headings: {
    name: "Heading structure",
    short: "Headings",
    description: "Give every page a clear sense of direction.",
    rule: "A descriptive main heading is required. Additional H1 headings, empty sections and hierarchy gaps prompt editorial review.",
  },
  structured_data: {
    name: "Structured data",
    short: "Structured data",
    description: "Add useful context for search engines.",
    rule: "Eligible product pages need valid Schema.org Product JSON-LD, a name, and valid offers, review or aggregateRating fields. Invalid JSON fails; unrelated or unsupported pages are N/A. This does not guarantee rich results.",
  },
};
export const METRIC_KEYS = Object.keys(METRICS) as MetricKey[];
export const DEFAULT_WEIGHTS: Record<MetricKey, number> = {metadata:12,broken_links:12,indexability:16,performance:13,headings:8,site_health:7,canonical:10,structured_data:10,media:7,geo:5};
export function reportKeys(report?: Report | null) {
  return report ? (Object.keys(report.metrics) as MetricKey[]) : (Object.keys(DEFAULT_WEIGHTS) as MetricKey[]);
}
export const CATEGORIES = {
  ...METRICS,
  robots_txt: {
    short: "robots.txt",
    rule: "Controls crawler access. A missing file does not prevent indexing; blocked pages may be intentional.",
  },
  sitemap: {
    short: "Sitemap",
    rule: "Valid sitemap XML helps discovery. It does not guarantee indexing. Inspection limits and unchecked files appear in site essentials.",
  },
};
export const CATEGORY_KEYS = Object.keys(CATEGORIES) as IssueCategory[];
export function host(url: string) {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
export function pagePath(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.pathname + parsed.search;
  } catch {
    return url;
  }
}
export function tone(score: number | null) {
  return score === null
    ? "neutral"
    : score >= 90
      ? "green"
      : score >= 75
        ? "lime"
        : score >= 50
          ? "amber"
          : "red";
}
export function csvCell(value: unknown) {
  let text = String(value ?? "");
  if (/^[\s]*[=+@\-\t\r]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function issuesCsv(issues: Issue[]) {
  const columns: (keyof Issue)[] = [
    "id",
    "metric",
    "severity",
    "outcome",
    "impact",
    "page_url",
    "target_url",
    "status_code",
    "observed",
    "expected",
    "suggested_action",
    "evidence",
  ];
  return [
    columns.join(","),
    ...issues.map((issue) =>
      columns.map((key) => csvCell(key === "evidence" ? JSON.stringify(issue.evidence ?? {}) : issue[key])).join(","),
    ),
  ].join("\r\n");
}
export function downloadReport(report: Report, format: "json" | "csv") {
  const data =
    format === "json"
      ? JSON.stringify(report, null, 2)
      : "\uFEFF" + issuesCsv(report.issues);
  const url = URL.createObjectURL(
    new Blob([data], {
      type: format === "json" ? "application/json" : "text/csv;charset=utf-8;",
    }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `crawlens-${host(report.website)}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      signal: options?.signal ?? AbortSignal.timeout(15000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new Error(
      "Cannot reach the backend. Make sure the API server is running, then try again.",
    );
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? (data.detail[0]?.msg ?? "Check the website URL.")
          : "The request could not be completed. Please try again.",
    );
  return data as T;
}
