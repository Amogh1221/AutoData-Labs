import pytest
from services.research_service import ResearchService
from core.models import Source, SourceStatus, SourceType
from core.interfaces import ICrawlProvider
import json

class MockEmptyHTMLCrawlProvider(ICrawlProvider):
    def fetch(self, url: str) -> str:
        # Simulates a JS-heavy SPA before rendering
        return '<div id="root"></div>'

class MockPartialDataCrawlProvider(ICrawlProvider):
    def fetch(self, url: str) -> str:
        # Simulates a site where the required "description" field is missing
        return '''
        <html>
            <body>
                <h1>Startups to watch in 2026</h1>
                <ul>
                    <li>MockTech (No description provided)</li>
                </ul>
            </body>
        </html>
        '''

def test_extraction_empty_js_shell(mock_store, sample_schema):
    """Proves that BasicCrawlProvider on a JS site returns 0 rows because the LLM gets an empty shell."""
    service = ResearchService(mock_store, MockEmptyHTMLCrawlProvider(), model_name="qwen2.5:7b-instruct")
    
    s = Source(
        source_id="test-e2e-1", 
        dataset_id="test-topic", 
        url="https://example.com/spa", 
        status=SourceStatus.PENDING, 
        source_type=SourceType.HTML, 
        metadata_draft="Test Source"
    )
    
    def check_state_fn(): return True
    
    entities = service.process_source(s, sample_schema, "run-123", check_state_fn, ["company_name"], set())
    
    # Should extract 0 rows from empty HTML
    assert entities is None or len(entities) == 0

def test_extraction_drops_partial_match_due_to_required_fields(mock_store, sample_schema):
    """Proves that missing a required field completely drops the row."""
    service = ResearchService(mock_store, MockPartialDataCrawlProvider(), model_name="qwen2.5:7b-instruct")
    
    s = Source(
        source_id="test-e2e-2", 
        dataset_id="test-topic", 
        url="https://example.com/partial", 
        status=SourceStatus.PENDING, 
        source_type=SourceType.HTML, 
        metadata_draft="Test Source"
    )
    
    def check_state_fn(): return True
    
    # We make BOTH company_name and description required
    entities = service.process_source(s, sample_schema, "run-123", check_state_fn, ["company_name", "description"], set())
    
    # Under current strict logic, it drops the row completely if description is missing.
    # After we fix the logic, it should return 1 row with description marked as 'missing'.
    # We assert the fixed behavior here (len == 1). It will fail initially.
    assert entities is not None
    assert len(entities) == 1
    
    # Verify the industry field is marked as missing
    desc_field = next((f for f in entities[0].fields if f.field_name == "industry"), None)
    assert desc_field is not None
    assert desc_field.status == "missing"
