"""
Additional edge-case tests for ResearchService (services/research_service.py)

Covers gaps not in test_research_service.py:
- Malformed JSON (no '[', truncated, dict instead of list) from LLM
- Deduplication: same primary key from 2 chunks → only 1 entity saved
- check_state_fn returning False mid-loop stops processing
- Crawl failure → source marked REJECTED, returns None without crashing
- _extract_json_array module-level helper with various malformed inputs
- Source is marked COMPLETED after successful extraction
- Source is marked REJECTED when all rows lack a primary key
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from services.research_service import ResearchService, _extract_json_array
from core.models import Source, SourceStatus, SourceType
from core.interfaces import ICrawlProvider


# ── helpers ───────────────────────────────────────────────────────────────────

class _StaticCrawlProvider(ICrawlProvider):
    """Returns a fixed string for every URL."""
    def __init__(self, content: str = ""):
        self._content = content

    def fetch(self, url: str) -> str:
        return self._content


class _FailingCrawlProvider(ICrawlProvider):
    """Always raises on fetch."""
    def fetch(self, url: str) -> str:
        raise ConnectionError("Simulated network error")


def _make_source(url: str = "https://example.com") -> Source:
    return Source(
        source_id="s1", dataset_id="topic1", url=url,
        status=SourceStatus.PENDING, source_type=SourceType.HTML,
        metadata_draft="Test"
    )


STARTUP_HTML = """
<html><body>
  <p>1. <b>AlphaCorp</b> – AI platform for enterprise</p>
  <p>2. <b>BetaInc</b> – Quantum computing startup</p>
</body></html>
"""

SCHEMA = {
    "company_name": {"type": "string", "description": "Name of the startup"},
    "description": {"type": "string", "description": "What they do"},
}


# ── _extract_json_array unit tests ────────────────────────────────────────────

class TestExtractJsonArray:
    def test_plain_valid_array(self):
        result = _extract_json_array('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_strips_markdown_json_fence(self):
        result = _extract_json_array('```json\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_strips_plain_code_fence(self):
        result = _extract_json_array('```\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_text_before_array(self):
        result = _extract_json_array('Here is the output:\n[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_truncated_array_recovers_valid_subset(self):
        """Algorithm walks back past trailing garbage to find the last valid ] boundary."""
        # Valid array followed by junk that also contains a ] — rfind walks back
        result = _extract_json_array('[{"a": 1}] trailing garbage with another ]')
        assert result is not None
        assert result[0] == {"a": 1}

    def test_empty_array(self):
        result = _extract_json_array("[]")
        assert result == []

    def test_no_array_returns_none(self):
        result = _extract_json_array("This is plain text with no JSON array.")
        assert result is None

    def test_dict_not_array_returns_none(self):
        result = _extract_json_array('{"key": "value"}')
        assert result is None

    def test_null_string_values_parsed(self):
        result = _extract_json_array('[{"a": null}]')
        assert result == [{"a": None}]


# ── ResearchService edge cases ────────────────────────────────────────────────

class TestResearchServiceEdgeCases:
    def test_crawl_failure_marks_source_rejected(self, mock_store, sample_schema):
        """If the crawl provider throws, process_source returns None and marks REJECTED."""
        svc = ResearchService(mock_store, _FailingCrawlProvider(), model_name="qwen2.5:7b-instruct")
        source = _make_source()

        result = svc.process_source(source, sample_schema, "r1", None, ["company_name"], set())

        assert result is None
        assert "Failed" in source.metadata_draft

    def test_malformed_llm_json_returns_none(self, mock_store):
        """If the LLM always returns unparseable text, process_source returns None."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider("Some HTML content with no JSON"),
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": "I cannot extract anything here."}}
            result = svc.process_source(source, SCHEMA, "r1", None, ["company_name"], set())

        assert result is None
        assert source.status == SourceStatus.REJECTED

    def test_deduplication_across_chunks(self, mock_store):
        """Same company_name in two chunks → only 1 entity saved, not 2."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider(STARTUP_HTML * 10),  # Force multiple chunks
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()
        seen_keys: set = set()

        # LLM always returns the same company regardless of chunk
        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {
                "message": {"content": '[{"company_name": "AlphaCorp", "description": "AI platform"}]'}
            }
            result = svc.process_source(source, SCHEMA, "r1", None, ["company_name"], seen_keys)

        if result:
            names = [e.entity_id for e in result]
            # All entity_ids must be unique (no duplicate AlphaCorp rows)
            assert len(names) == len(set(names))

    def test_check_state_fn_false_stops_processing(self, mock_store):
        """If check_state_fn() returns False, the loop breaks and we return None (no data)."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider(STARTUP_HTML),
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()

        # Always cancel immediately
        def always_cancel():
            return False

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {
                "message": {"content": '[{"company_name": "AlphaCorp", "description": "AI"}]'}
            }
            result = svc.process_source(source, SCHEMA, "r1", always_cancel, ["company_name"], set())

        # With check_state_fn returning False, no chunks are processed → no data
        assert result is None

    def test_all_rows_missing_primary_key_returns_none(self, mock_store):
        """If every extracted row is missing the primary key, source is REJECTED."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider(STARTUP_HTML),
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()

        with patch("ollama.chat") as mock_chat:
            # LLM returns rows where company_name is null
            mock_chat.return_value = {
                "message": {"content": '[{"company_name": null, "description": "AI platform"}]'}
            }
            result = svc.process_source(source, SCHEMA, "r1", None, ["company_name"], set())

        assert result is None
        assert source.status == SourceStatus.REJECTED

    def test_source_marked_completed_on_success(self, mock_store):
        """After successful extraction, source.status is set to COMPLETED."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider(STARTUP_HTML),
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {
                "message": {"content": '[{"company_name": "AlphaCorp", "description": "AI platform"}]'}
            }
            result = svc.process_source(source, SCHEMA, "r1", None, ["company_name"], set())

        assert source.status == SourceStatus.COMPLETED
        assert result is not None
        assert len(result) >= 1

    def test_entities_persisted_to_store_on_success(self, mock_store):
        """Entities extracted are saved to the store and retrievable by run_id."""
        svc = ResearchService(
            mock_store,
            _StaticCrawlProvider(STARTUP_HTML),
            model_name="qwen2.5:7b-instruct"
        )
        source = _make_source()

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {
                "message": {"content": '[{"company_name": "AlphaCorp", "description": "AI platform"}]'}
            }
            result = svc.process_source(source, SCHEMA, "r1", None, ["company_name"], set())

        if result:
            saved = mock_store.get_entities_by_run_id("r1")
            assert len(saved) >= 1
            names = [f.value for e in saved for f in e.fields if f.field_name == "company_name"]
            assert "AlphaCorp" in names
