import pytest
from providers.ddg_search_provider import DuckDuckGoSearchProvider
from providers.bs4_crawl_provider import BasicCrawlProvider

def test_duckduckgo_search():
    provider = DuckDuckGoSearchProvider()
    results = provider.search("tech startups 2026", max_results=2)
    
    assert isinstance(results, list)
    assert len(results) > 0
    assert "url" in results[0]
    assert "title" in results[0]
    assert results[0]["url"].startswith("http")

def test_basic_crawl_provider_success():
    provider = BasicCrawlProvider(timeout=10)
    # Wikipedia doesn't block basic scraping, so this should succeed
    html = provider.fetch("https://en.wikipedia.org/wiki/List_of_unicorn_startup_companies")
    
    assert html is not None
    assert len(html) > 500
    assert "unicorn" in html.lower()

def test_basic_crawl_provider_403_fallback():
    provider = BasicCrawlProvider(timeout=10)
    # fastcompany blocks basic scraping with a 403, but we should STILL return whatever HTML we get
    # instead of crashing. (If it crashes, this test will fail).
    html = provider.fetch("https://www.fastcompany.com/")
    
    assert html is not None
    assert isinstance(html, str)
