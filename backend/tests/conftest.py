import pytest
from backend.app.schemas import CrawlPage


@pytest.fixture
def good_html():
    return '''<html><head><title>A thoughtful workspace for modern teams</title>
    <meta name="description" content="Bring your projects and people together in one thoughtful workspace. Plan your next chapter with a little more clarity.">
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Example","offers":{"@type":"Offer","price":"19","priceCurrency":"USD"}}</script>
    </head><body><h1>A little clarity for your team</h1><h2>Plan together</h2><a href="/pricing#plans">Pricing</a></body></html>'''


@pytest.fixture
def good_page(good_html):
    return CrawlPage(url='https://example.com/', html=good_html, status_code=200, headers={})
