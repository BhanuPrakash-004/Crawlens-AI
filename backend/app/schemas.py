from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field
from urllib.parse import urlsplit

MetricName = Literal['metadata', 'broken_links', 'indexability', 'headings', 'structured_data', 'performance', 'canonical', 'media', 'geo', 'site_health']
IssueCategory = Literal['metadata', 'broken_links', 'indexability', 'headings', 'structured_data', 'performance', 'canonical', 'media', 'geo', 'site_health', 'robots_txt', 'sitemap']
Priority = Literal['critical', 'high', 'medium', 'low']


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator('url')
    @classmethod
    def valid_shape(cls, value: str) -> str:
        value = value.strip()
        try:
            parsed = urlsplit(value)
            if not parsed.scheme or not parsed.hostname or any(c.isspace() for c in value):
                raise ValueError('Enter a full website URL, such as https://example.com.')
            _ = parsed.port
        except ValueError as exc:
            raise ValueError('Enter a valid website URL, such as https://example.com.') from exc
        return value


class CrawlPage(BaseModel):
    url: str
    html: str
    status_code: int | None = None
    headers: dict[str, str] | None = None
    original_status_code: int | None = None
    source_kind: str = 'firecrawl_rendered'
    redirect_aliases: list[str] = Field(default_factory=list)
    raw_html: str | None = None
    source_notes: list[str] = Field(default_factory=list)
    redirect_chain: list[dict] = Field(default_factory=list)


class FetchFailure(BaseModel):
    url: str
    reason: str


class CrawlResult(BaseModel):
    pages: list[CrawlPage] = Field(default_factory=list)
    failures: list[FetchFailure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    complete: bool = True
    start_url: str | None = None  # The address actually crawled, after following the entered URL's redirects.


class Check(BaseModel):
    passed: bool | None
    observed: str
    expected: str
    details: dict = Field(default_factory=dict)


    @computed_field
    @property
    def outcome(self) -> Literal['Passed','Failed','Warning','Review','N/A']:
        if self.details.get('not_applicable'):
            return 'N/A'
        if self.passed is False:
            return 'Failed'
        if self.details.get('warnings'):
            return 'Warning'
        return 'Passed' if self.passed is True else 'Review'


class SocialProfile(BaseModel):
    platform: str
    url: str
    source_pages: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)


class PageAnalysis(BaseModel):
    url: str
    status_code: int | None
    checks: dict[MetricName, Check]
    links: list[str]
    diagnostics: list[str] = Field(default_factory=list)
    headers_available: bool = False
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    supplemental: dict = Field(default_factory=dict)
    source_kind: str = 'firecrawl_rendered'


class LinkResult(BaseModel):
    references: list[dict] = Field(default_factory=list)
    redirect_chain: list[dict] = Field(default_factory=list)
    url: str
    source_pages: list[str]
    status: Literal['ok', 'broken', 'unknown']
    status_code: int | None = None
    final_url: str | None = None
    reason: str | None = None
    manual_review: bool = False


class Issue(BaseModel):
    outcome: Literal['Failed', 'Warning', 'Review'] = 'Failed'
    evidence: dict = Field(default_factory=dict)
    impact: str = ''
    id: str
    metric: IssueCategory
    severity: Priority
    page_url: str
    title: str
    observed: str
    expected: str
    suggested_action: str
    target_url: str | None = None
    status_code: int | None = None
    affected_source_pages: int | None = None
    manual_review: bool = False


class Metric(BaseModel):
    score: int | None
    weight: int
    passing: int
    evaluated: int
    unit: str = 'pages'
    warnings: int = 0
    evidence: list[dict] = Field(default_factory=list)
    unknown: int = 0
    not_applicable: int = 0
    review_required: int = 0
    status: Literal['measured', 'unknown']


class MetadataProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    page_url: str
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    priority: Priority
    issue_ids: list[str] = Field(min_length=1, max_length=300)
    action: str = Field(min_length=1, max_length=180)
    reason: str = Field(min_length=1, max_length=800)
    suggested_fix: str = Field(min_length=1, max_length=1200)
    metadata: MetadataProposal | None = None
    source: Literal['ai', 'rules'] = 'rules'  # Set by the backend after validation, never trusted from the LLM.


class Coverage(BaseModel):
    page_limit: int
    pages_analyzed: int
    pages_failed: int
    link_occurrences: int = 0
    measured_weight: int = 0
    links_discovered: int
    links_verified: int
    links_unknown: int
    headers_checked: int
    crawl_complete: bool
    failures: list[FetchFailure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


SiteStatus = Literal['passed', 'warning', 'error', 'unknown']


class RobotsRule(BaseModel):
    directive: str
    value: str
    agents: list[str]
    line: int


class CrawlPermission(BaseModel):
    page_url: str
    agent: str
    allowed: bool
    matched_rule: str | None = None


class RobotsAudit(BaseModel):
    url: str = ''
    status: SiteStatus = 'unknown'
    status_code: int | None = None
    summary: str = 'This audit has no robots.txt evidence. Run a new audit to check it.'
    content: str = ''
    content_truncated: bool = False
    rules: list[RobotsRule] = Field(default_factory=list)
    sitemap_urls: list[str] = Field(default_factory=list)
    permissions: list[CrawlPermission] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    crawl_delay_seconds: float = 0


class SitemapFile(BaseModel):
    url: str
    status: SiteStatus = 'unknown'
    status_code: int | None = None
    kind: str | None = None
    entries: int = 0
    message: str = ''


class SitemapAudit(BaseModel):
    status: SiteStatus = 'unknown'
    summary: str = 'This audit has no sitemap evidence. Run a new audit to check it.'
    files: list[SitemapFile] = Field(default_factory=list)
    urls_discovered: int = 0
    url_sample: list[str] = Field(default_factory=list)
    scanned_pages_listed: int = 0
    scanned_pages_missing: list[str] = Field(default_factory=list)
    complete: bool = False
    declared: int = 0
    visited: int = 0
    nested: int = 0
    successful: int = 0
    failed: int = 0
    pending: int = 0
    external_hosts: dict[str, int] = Field(default_factory=dict)
    page_coverage: list[dict] = Field(default_factory=list)
    file_limit: int = 5
    warnings: list[str] = Field(default_factory=list)


class SocialAudit(BaseModel):
    status: Literal['found', 'not_found', 'unknown'] = 'unknown'
    profiles: list[SocialProfile] = Field(default_factory=list)
    pages_checked: int = 0
    pages_with_profiles: int = 0
    summary: str = 'No social-profile evidence is available for this audit.'


class SiteChecks(BaseModel):
    robots_txt: RobotsAudit = Field(default_factory=RobotsAudit)
    sitemap: SitemapAudit = Field(default_factory=SitemapAudit)
    social: SocialAudit = Field(default_factory=SocialAudit)
    llms_txt: dict = Field(default_factory=dict)
    https: dict = Field(default_factory=lambda: {'status':'unknown', 'summary':'Secure transport has not been verified.'})


class Report(BaseModel):
    classification_bands: list[int] = Field(default_factory=lambda: [90,75,50])
    executive_summary: str = ''
    rule_version: str = '2.0'
    website: str
    completed_at: str = Field(default_factory=now)
    duration_seconds: float = 0
    is_sample: bool = False
    pages_crawled: int
    overall_score: int | None
    classification: str
    score_status: Literal['complete', 'partial']
    metrics: dict[MetricName, Metric]
    issues: list[Issue]
    pages: list[PageAnalysis]
    links: list[LinkResult]
    recommendations: list[Recommendation] = Field(default_factory=list)
    recommendation_source: Literal['ai', 'rules'] = 'rules'
    recommendation_note: str = ''
    coverage: Coverage
    site_checks: SiteChecks = Field(default_factory=SiteChecks)
    requested_url: str | None = None  # Set when the entered URL redirected to another website.

    @computed_field
    @property
    def metric_groups(self) -> list[dict]:
        """The six reported metrics, derived from the stored check counts with the same formula as the overall score."""
        from fractions import Fraction
        from backend.app.config import METRIC_GROUPS
        groups = []
        for key, label, kind, names in METRIC_GROUPS:
            checks = [(name, self.metrics[name]) for name in names if name in self.metrics]
            if not checks:
                continue  # Reports saved under older rule versions lack some checks.
            measured = [(m.passing, m.evaluated, m.weight) for _, m in checks if m.evaluated]
            weight_measured = sum(w for *_, w in measured)
            score = None
            if weight_measured:
                value = 100 * sum(Fraction(p, e) * w for p, e, w in measured) / weight_measured
                score = (2 * value.numerator + value.denominator) // (2 * value.denominator)  # round half up
            groups.append({'key': key, 'label': label, 'kind': kind, 'checks': [name for name, _ in checks],
                           'weight': sum(m.weight for _, m in checks), 'measured_weight': weight_measured,
                           'score': score, 'status': 'measured' if weight_measured else 'unknown'})
        return groups


class AuditAccepted(BaseModel):
    audit_id: str
    status: Literal['queued'] = 'queued'


class AuditJob(BaseModel):
    audit_id: str
    website: str
    status: Literal['queued', 'running', 'completed', 'failed'] = 'queued'
    stage: str = 'queued'
    created_at: str = Field(default_factory=now)
    report: Report | None = None
    error: str | None = None


class Health(BaseModel):
    status: str = 'ok'
    crawler_configured: bool
    ai_configured: bool
    pagespeed_configured: bool = False
    model: str
    page_limit: int
    link_limit: int
