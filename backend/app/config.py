from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

WEIGHTS = {'metadata': 12, 'broken_links': 12, 'indexability': 16, 'performance': 13,
           'headings': 8, 'site_health': 7, 'canonical': 10, 'structured_data': 10, 'media': 7, 'geo': 5}

# The reported metrics: the two the brief mandates, three chosen SEO metrics and one AI-search signal.
# Each of the ten scored checks belongs to exactly one group; a group's weight is the sum of its checks.
METRIC_GROUPS = (
    ('title_meta', 'Title and meta description', 'mandatory', ('metadata',)),
    ('broken_links', 'Broken internal links', 'mandatory', ('broken_links',)),
    ('crawlability', 'Crawlability and indexability', 'seo', ('indexability', 'site_health', 'canonical')),
    ('performance', 'Mobile page performance', 'seo', ('performance',)),
    ('content', 'Content structure and rich results', 'seo', ('headings', 'structured_data', 'media')),
    ('ai_readiness', 'AI search readiness', 'ai', ('geo',)),
)
if sorted(c for *_, checks in METRIC_GROUPS for c in checks) != sorted(WEIGHTS):
    raise RuntimeError('Every scored check must belong to exactly one metric group.')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', env_file_encoding='utf-8')
    firecrawl_api_key: str = ''
    firecrawl_api_url: str = 'https://api.firecrawl.dev'
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    openai_json_mode: bool = True
    crawl_page_limit: int = Field(default=20, ge=1, le=20)
    link_check_limit: int = Field(default=300, ge=1, le=300)
    link_concurrency: int = Field(default=5, ge=1, le=10)
    request_timeout_seconds: int = Field(default=12, ge=1, le=30)
    audit_timeout_seconds: int = Field(default=180, ge=15, le=600)
    ai_timeout_seconds: int = Field(default=40, ge=1, le=120)
    max_concurrent_audits: int = Field(default=2, ge=1, le=5)
    max_stored_audits: int = Field(default=50, ge=1, le=100)
    database_path: str = str(ROOT / 'data' / 'crawlens.sqlite3')
    max_html_bytes: int = 2_000_000
    metric_weights: dict[str, int] = Field(default_factory=lambda: WEIGHTS.copy())
    title_min: int = Field(30, ge=1)
    title_max: int = Field(60, ge=1)
    description_min: int = Field(70, ge=1)
    description_max: int = Field(160, ge=1)
    lcp_ms: float = Field(2500, gt=0)
    inp_ms: float = Field(200, gt=0)
    cls_limit: float = Field(0.1, gt=0)
    sitemap_hosts: list[str] = Field(default_factory=list)
    sitemap_file_limit: int = Field(40, ge=1, le=200)
    sitemap_bytes: int = Field(5_000_000, ge=1024, le=52_428_800)
    pagespeed_page_limit: int = Field(1, ge=0, le=20)
    pagespeed_api_key: str = ''
    media_check_limit: int = Field(80, ge=0, le=300)
    ai_crawlers: list[str] = Field(default_factory=lambda: ['Googlebot', 'OAI-SearchBot', 'PerplexityBot'])
    search_crawlers: list[str] = Field(default_factory=lambda: ['Googlebot', 'Bingbot'])
    required_index_urls: list[str] = Field(default_factory=list)
    media_hosts: list[str] = Field(default_factory=list)
    excluded_path_segments: list[str] = Field(default_factory=lambda: ['cart', 'basket', 'checkout', 'account', 'my-account', 'login', 'logout',
                                                                         'signin', 'sign-in', 'register', 'wishlist', 'search'])
    excellent_score: int = Field(90, ge=0, le=100)
    good_score: int = Field(75, ge=0, le=100)
    improvement_score: int = Field(50, ge=0, le=100)
    thin_word_limit: int = Field(50, ge=1)
    similarity_threshold: float = Field(.9, gt=0, le=1)
    large_resource_bytes: int = Field(250_000, ge=1)
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'

    @model_validator(mode='after')
    def validate_rules(self):
        if set(self.metric_weights) != set(WEIGHTS) or any(w < 0 for w in self.metric_weights.values()) or sum(self.metric_weights.values()) != 100:
            raise ValueError('Supply all ten metric weights totaling 100.')
        if self.title_min > self.title_max or self.description_min > self.description_max:
            raise ValueError('Minimum lengths must be within their configured maximums.')
        if not self.improvement_score < self.good_score < self.excellent_score:
            raise ValueError('Score classification thresholds must be increasing.')
        if not self.search_crawlers or not self.ai_crawlers:
            raise ValueError('Configure at least one search and AI crawler.')
        return self


settings = Settings()
