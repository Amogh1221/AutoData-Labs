import pytest
from services.source_service import SourceService
from core.models import SourceType

class MockSearchProvider:
    def search(self, query: str, max_results: int = 5):
        return [
            {"url": "https://example.com/1", "title": "Example 1", "snippet": "A great startup snippet 1"},
            {"url": "https://example.com/2", "title": "Example 2", "snippet": "A great startup snippet 2"},
        ]

def test_discover_sources():
    # Use qwen2.5:7b-instruct for testing to match production
    service = SourceService(search_provider=MockSearchProvider(), model_name="qwen2.5:7b-instruct")
    
    candidates = service.discover_sources("tech startups")
    
    assert isinstance(candidates, list)
    assert len(candidates) > 0
    assert candidates[0].url.startswith("http")
    # Verify the default source_type string doesn't cause ValueError when parsed
    assert candidates[0].source_type in ["html", "document", "api"]
    
    # Simulate routes.py parsing
    try:
        SourceType(candidates[0].source_type)
    except ValueError:
        pytest.fail(f"Invalid SourceType mapped to Candidate: {candidates[0].source_type}")

def test_discover_sources_excludes_urls():
    service = SourceService(search_provider=MockSearchProvider(), model_name="qwen2.5:7b-instruct")
    
    # Example 1 is in the mock results. We exclude it.
    exclude_urls = {"https://example.com/1"}
    candidates = service.discover_sources("tech startups", exclude_urls=exclude_urls)
    
    assert isinstance(candidates, list)
    urls = [c.url for c in candidates]
    
    assert "https://example.com/1" not in urls
    assert "https://example.com/2" in urls
