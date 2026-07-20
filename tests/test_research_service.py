import pytest
from services.research_service import ResearchService
from core.models import Source, SourceStatus, SourceType
import json

class MockCrawlProvider:
    def fetch(self, url: str) -> str:
        if "fail" in url:
            return ""
        return """
        <html>
            <head><title>Top Startups</title></head>
            <body>
                <h1>Startups to watch in 2026</h1>
                <p>1. <b>MockTech</b> is a great software company.</p>
                <p>2. <b>FinMock</b> is disrupting the financial services sector.</p>
            </body>
        </html>
        """

def test_chunk_html(mock_store):
    service = ResearchService(mock_store, MockCrawlProvider(), model_name="qwen2.5:7b-instruct")
    html = "<html><body>" + "<p>word </p>" * 3000 + "</body></html>"
    chunks = service._chunk_html(html)
    
    assert isinstance(chunks, list)
    assert len(chunks) > 1 # Should break into multiple chunks due to length
    assert all(isinstance(c, str) for c in chunks)

def test_process_source(mock_store, sample_schema):
    service = ResearchService(mock_store, MockCrawlProvider(), model_name="qwen2.5:7b-instruct")
    
    # Create a source
    s = Source(
        source_id="test-1", 
        dataset_id="test-topic", 
        url="https://example.com/success", 
        status=SourceStatus.PENDING, 
        source_type=SourceType.HTML, 
        metadata_draft="Test Source"
    )
    
    def check_state_fn(): return True
    
    # Run extraction (this will actually invoke the LLM locally)
    entities = service.process_source(s, sample_schema, "run-123", check_state_fn, [], set())
    
    assert entities is not None, "Extraction returned None, likely due to JSON parsing failure"
    assert isinstance(entities, list)
    if len(entities) > 0: # If LLM found data
        assert hasattr(entities[0], "fields")
        assert len(entities[0].fields) > 0

def test_process_source_empty_html(mock_store, sample_schema):
    service = ResearchService(mock_store, MockCrawlProvider(), model_name="qwen2.5:7b-instruct")
    
    # Create a source that fails to load HTML
    s = Source(
        source_id="test-2", 
        dataset_id="test-topic", 
        url="https://example.com/fail", 
        status=SourceStatus.PENDING, 
        source_type=SourceType.HTML, 
        metadata_draft="Failed Source"
    )
    
    def check_state_fn(): return True
    
    # Run extraction
    entities = service.process_source(s, sample_schema, "run-123", check_state_fn, [], set())
    
    # Empty HTML should return None or empty list, but not crash
    assert entities is None or len(entities) == 0
