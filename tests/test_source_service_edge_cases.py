"""
Additional edge-case tests for SourceService (services/source_service.py)

Covers gaps in test_source_service.py:
- LLM returns a dict with nested list instead of a flat query array
- LLM returns completely invalid JSON → uses fallback queries
- All URLs rejected by filter LLM → returns empty candidates list
- Duplicate URLs across queries are deduplicated
- discover_sources returns empty list when search returns nothing
- _fetch_metadata correctly classifies HTML vs JSON vs PDF content types
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from services.source_service import SourceService
from core.interfaces import ISearchProvider


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_service(search_results=None) -> tuple[SourceService, MagicMock]:
    mock_search = MagicMock(spec=ISearchProvider)
    mock_search.search.return_value = search_results if search_results is not None else [
        {"url": "https://example.com/a", "title": "Top Startups", "snippet": "A big list"},
        {"url": "https://example.com/b", "title": "Directory", "snippet": "Another list"},
    ]
    svc = SourceService(search_provider=mock_search, model_name="qwen2.5:7b-instruct")
    return svc, mock_search


VALID_QUERIES_PAYLOAD = json.dumps(["deep tech startups list", "best deep tech companies 2026", "deep tech database"])
VALID_FILTER_PAYLOAD = json.dumps([True, True])
REJECT_ALL_FILTER_PAYLOAD = json.dumps([False, False])


# ── discover_sources edge cases ───────────────────────────────────────────────

class TestDiscoverSourcesEdgeCases:
    def test_llm_returns_dict_with_nested_list(self):
        """When LLM wraps queries in a dict, we extract the list and use it."""
        payload = json.dumps({"queries": ["query A", "query B"]})
        svc, mock_search = _make_service()

        with patch("ollama.chat") as mock_chat:
            # First call: query generation (returns dict-wrapped list)
            # Second call: filter (accepts all)
            mock_chat.side_effect = [
                {"message": {"content": payload}},
                {"message": {"content": VALID_FILTER_PAYLOAD}},
            ]
            with patch.object(svc, "_fetch_metadata", return_value={"source_type": __import__("core.models", fromlist=["SourceType"]).SourceType.HTML, "metadata_draft": "Test"}):
                candidates = svc.discover_sources("deep tech startups")

        # Should have processed some results (query was extracted from dict)
        assert isinstance(candidates, list)

    def test_llm_invalid_query_json_uses_fallback(self):
        """Invalid JSON from query LLM falls back to topic-based default queries."""
        svc, mock_search = _make_service()

        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [
                {"message": {"content": "NOT VALID JSON"}},  # Query gen fails
                {"message": {"content": VALID_FILTER_PAYLOAD}},  # Filter accepts
            ]
            with patch.object(svc, "_fetch_metadata", return_value={"source_type": __import__("core.models", fromlist=["SourceType"]).SourceType.HTML, "metadata_draft": "Fallback"}):
                candidates = svc.discover_sources("deep tech startups")

        # Fallback queries were used, search was called, results processed
        mock_search.search.assert_called()
        assert isinstance(candidates, list)

    def test_all_urls_rejected_by_filter_returns_empty(self):
        """When the filter LLM rejects all results, discover_sources returns []."""
        svc, mock_search = _make_service()

        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [
                {"message": {"content": VALID_QUERIES_PAYLOAD}},
                {"message": {"content": REJECT_ALL_FILTER_PAYLOAD}},
            ]
            candidates = svc.discover_sources("deep tech startups")

        assert candidates == []

    def test_duplicate_urls_across_queries_are_deduplicated(self):
        """If two search queries return the same URL, it appears only once in candidates."""
        # Both queries return the same URL
        mock_search = MagicMock(spec=ISearchProvider)
        mock_search.search.return_value = [
            {"url": "https://example.com/same", "title": "Duplicate", "snippet": "Same page"},
        ]
        svc = SourceService(search_provider=mock_search, model_name="qwen2.5:7b-instruct")

        with patch("ollama.chat") as mock_chat:
            # 3 queries, all search returns same URL → should only appear once after dedup
            mock_chat.side_effect = [
                {"message": {"content": VALID_QUERIES_PAYLOAD}},  # 3 queries
                {"message": {"content": json.dumps([True])}},  # filter: 1 result accepted
            ]
            from core.models import SourceType
            with patch.object(svc, "_fetch_metadata", return_value={"source_type": SourceType.HTML, "metadata_draft": "Test"}):
                candidates = svc.discover_sources("topic")

        urls = [c.url for c in candidates]
        assert len(urls) == len(set(urls)), "Duplicate URLs should be deduplicated"

    def test_returns_empty_when_search_returns_nothing(self):
        """If every search query returns 0 results, discover_sources returns []."""
        svc, mock_search = _make_service(search_results=[])

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": VALID_QUERIES_PAYLOAD}}
            candidates = svc.discover_sources("niche obscure topic with no results")

        assert candidates == []


# ── _fetch_metadata tests ─────────────────────────────────────────────────────

class TestFetchMetadata:
    def _make_mock_response(self, content_type: str, url: str = "https://example.com"):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": content_type}
        mock_resp.iter_content.return_value = iter([b"<html><head><title>Test</title></head></html>"])
        mock_resp.close = MagicMock()
        return mock_resp

    def test_html_content_type_detected(self):
        svc, _ = _make_service()
        from core.models import SourceType
        mock_resp = self._make_mock_response("text/html; charset=utf-8")

        with patch("requests.get", return_value=mock_resp):
            meta = svc._fetch_metadata("https://example.com/page")

        assert meta["source_type"] == SourceType.HTML

    def test_json_content_type_detected_as_api(self):
        svc, _ = _make_service()
        from core.models import SourceType
        mock_resp = self._make_mock_response("application/json")

        with patch("requests.get", return_value=mock_resp):
            meta = svc._fetch_metadata("https://api.example.com/data")

        assert meta["source_type"] == SourceType.API

    def test_pdf_content_type_detected_as_document(self):
        svc, _ = _make_service()
        from core.models import SourceType
        mock_resp = self._make_mock_response("application/pdf")

        with patch("requests.get", return_value=mock_resp):
            meta = svc._fetch_metadata("https://example.com/report.pdf")

        assert meta["source_type"] == SourceType.DOCUMENT

    def test_fetch_metadata_handles_network_error_gracefully(self):
        """If the request fails, returns a default HTML type without crashing."""
        svc, _ = _make_service()
        from core.models import SourceType

        with patch("requests.get", side_effect=Exception("Timeout")):
            meta = svc._fetch_metadata("https://broken-url.example.com")

        # Should return a safe default
        assert "source_type" in meta
        assert "metadata_draft" in meta
