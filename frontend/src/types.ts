export type MetricKey =
  | "metadata"
  | "broken_links"
  | "indexability"
  | "headings"
  | "performance" | "canonical" | "media" | "geo" | "site_health"
  | "structured_data";
export type Severity = "critical" | "high" | "medium" | "low";
export type IssueCategory = MetricKey | "robots_txt" | "sitemap";
export type View =
  | "history"
  | "overview"
  | "issues"
  | "pages"
  | "essentials"
  | "social"
  | "plan"
  | "coverage";
export type SiteStatus = "passed" | "warning" | "error" | "unknown";
export interface SocialProfile {
  platform: string;
  url: string;
  source_pages: string[];
  evidence_types: string[];
}
export interface SiteChecks {
  llms_txt?: {status?: string; summary?: string; preview?: string};
  https?: {
    status: SiteStatus;
    summary: string;
    certificate_valid?: boolean;
    http_to_https?: boolean;
    https_status?: number;
    http_status?: number;
    http_final_url?: string;
    redirect_chain?: {
      url: string;
      status_code: number;
      location: string | null;
    }[];
  };
  robots_txt: {
    url: string;
    status: SiteStatus;
    status_code: number | null;
    summary: string;
    content: string;
    content_truncated: boolean;
    rules: {
      directive: string;
      value: string;
      agents: string[];
      line: number;
    }[];
    sitemap_urls: string[];
    permissions: {
      page_url: string;
      agent: string;
      allowed: boolean;
      matched_rule: string | null;
    }[];
    warnings: string[];
  };
  sitemap: {
    status: SiteStatus;
    summary: string;
    declared?: number; visited?: number; nested?: number; successful?: number; failed?: number; pending?: number;
    page_coverage?: {url:string;status:string;reason:string}[];
    external_hosts?: Record<string, number>;
    files: {
      url: string;
      status: SiteStatus;
      status_code: number | null;
      kind: string | null;
      entries: number;
      message: string;
    }[];
    urls_discovered: number;
    url_sample: string[];
    scanned_pages_listed: number;
    scanned_pages_missing: string[];
    complete: boolean;
    file_limit: number;
    warnings: string[];
  };
  social: {
    status: "found" | "not_found" | "unknown";
    profiles: SocialProfile[];
    pages_checked: number;
    pages_with_profiles: number;
    summary: string;
  };
}
export interface Check {
  outcome?: "Passed" | "Failed" | "Warning" | "Review" | "N/A";
  passed: boolean | null;
  observed: string;
  expected: string;
  details: Record<string, unknown>;
}
export interface Page {
  source_kind?: string;
  supplemental?: {
    social_metadata?: Record<string,string|null>;
    mixed_content?: string[];
    images?: {
      checked: number;
      missing_alt: string[];
      empty_alt_review: string[];
      note: string;
    };
    viewport?: { present: boolean; content: string };
    http?: {
      status_code: number | null;
      redirect_chain: {
        url: string;
        status_code: number;
        location: string | null;
      }[];
    };
  };
  url: string;
  status_code: number | null;
  checks: Partial<Record<MetricKey, Check>>;
  links: string[];
  diagnostics: string[];
  headers_available: boolean;
  social_profiles?: SocialProfile[];
}
export interface Issue {
  id: string;
  metric: IssueCategory;
  severity: Severity;
  page_url: string;
  title: string;
  observed: string;
  expected: string;
  suggested_action: string;
  target_url: string | null;
  status_code: number | null;
  manual_review: boolean;
  evidence?: Record<string,unknown>;
  impact?: string;
  outcome?: string;
  affected_source_pages: number | null;
}
export interface Metric {
  unit?: string;
  warnings?: number;
  evidence?: {url:string;status:string;observed:string;rule?:string}[];
  not_applicable?: number;
  review_required?: number;
  score: number | null;
  weight: number;
  passing: number;
  evaluated: number;
  unknown: number;
  status: "measured" | "unknown";
}
export interface Link {
  url: string;
  source_pages: string[];
  status: "ok" | "broken" | "unknown";
  status_code: number | null;
  final_url: string | null;
  reason: string | null;
  manual_review: boolean;
}
export interface Recommendation {
  priority: Severity;
  issue_ids: string[];
  action: string;
  reason: string;
  suggested_fix: string;
  metadata: { page_url: string; title: string; description: string } | null;
}
export interface Report {
  rule_version?: string;
  classification_bands?: [number,number,number];
  executive_summary?: string;
  site_checks?: SiteChecks;
  website: string;
  completed_at: string;
  duration_seconds: number;
  is_sample: boolean;
  pages_crawled: number;
  overall_score: number | null;
  classification: string;
  score_status: "complete" | "partial";
  metrics: Record<MetricKey, Metric>;
  issues: Issue[];
  pages: Page[];
  links: Link[];
  recommendations: Recommendation[];
  recommendation_source: "ai" | "rules";
  recommendation_note: string;
  coverage: {
    page_limit: number;
    pages_analyzed: number;
    pages_failed: number;
    measured_weight?: number; link_occurrences?: number;
    links_discovered: number;
    links_verified: number;
    links_unknown: number;
    headers_checked: number;
    crawl_complete: boolean;
    failures: { url: string; reason: string }[];
    warnings: string[];
  };
}
export interface Job {
  audit_id: string;
  website: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  report: Report | null;
  error: string | null;
}
export interface Health {
  status: string;
  crawler_configured: boolean;
  ai_configured: boolean;
  model: string;
  page_limit: number;
  link_limit: number;
}
