"""
Tests for PlannerService (services/planner_service.py)

Covers:
- generate_schema returns well-formed SchemaColumn objects
- generate_schema handles LLM returning a dict instead of a list (robustness)
- generate_schema handles LLM returning indexed dict ({"0": {...}, "1": {...}})
- generate_schema falls back gracefully when LLM returns invalid JSON
- get_search_context returns (text, urls) tuple and handles no search provider
- validate_column returns valid=True for a sensible column
- validate_column returns valid=False for an irrelevant column
- validate_column falls back gracefully when LLM returns invalid JSON

NOTE: Tests that call the real LLM are integration tests (marked as such).
      Tests of internal parsing logic use patched LLM responses.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from services.planner_service import PlannerService
from core.schemas import SchemaColumn


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_ollama(content: str):
    """Returns a mock ollama.chat response with the given content string."""
    return {"message": {"content": content}}


def _make_service(search_provider=None) -> PlannerService:
    return PlannerService(model_name="qwen2.5:7b-instruct", search_provider=search_provider)


# ── generate_schema tests ─────────────────────────────────────────────────────

class TestGenerateSchema:
    def test_returns_list_of_schema_columns(self):
        """When LLM returns a clean JSON array, we get a list of SchemaColumn objects."""
        payload = json.dumps([
            {"id": 1, "name": "company_name", "type": "string", "reason": "Primary key"},
            {"id": 2, "name": "industry", "type": "string", "reason": "Sector info"},
        ])
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama(payload)):
            columns, _ = svc.generate_schema("deep tech startups", "context here")

        assert len(columns) == 2
        assert all(isinstance(c, SchemaColumn) for c in columns)
        assert columns[0].name == "company_name"
        assert columns[1].name == "industry"

    def test_handles_dict_with_list_value(self):
        """LLM sometimes wraps the list in a dict key."""
        payload = json.dumps({"columns": [
            {"name": "startup_name", "type": "string", "reason": "Name"},
        ]})
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama(payload)):
            columns, _ = svc.generate_schema("AI startups", "")

        assert len(columns) == 1
        assert columns[0].name == "startup_name"

    def test_handles_indexed_dict_format(self):
        """LLM sometimes returns {"0": {...}, "1": {...}} instead of a list."""
        payload = json.dumps({
            "0": {"name": "country", "type": "string", "reason": "HQ country"},
            "1": {"name": "funding", "type": "number", "reason": "Total funding"},
        })
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama(payload)):
            columns, _ = svc.generate_schema("biotech companies", "")

        assert len(columns) == 2

    def test_falls_back_on_invalid_json(self):
        """Invalid JSON from the LLM results in a fallback schema, not a crash."""
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama("THIS IS NOT JSON")):
            columns, _ = svc.generate_schema("any topic", "")

        # Fallback schema has at least one column and doesn't raise
        assert len(columns) >= 1
        assert isinstance(columns[0], SchemaColumn)

    def test_strips_markdown_fences(self):
        """Markdown ```json fences in the LLM response are handled correctly."""
        payload = '```json\n[{"name": "founder", "type": "string", "reason": "Person"}]\n```'
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama(payload)):
            columns, _ = svc.generate_schema("founders", "")

        assert len(columns) == 1
        assert columns[0].name == "founder"

    def test_schema_column_has_correct_id_numbering(self):
        """Column IDs should be 1-indexed and sequential."""
        payload = json.dumps([
            {"name": "a", "type": "string", "reason": ""},
            {"name": "b", "type": "string", "reason": ""},
            {"name": "c", "type": "string", "reason": ""},
        ])
        svc = _make_service()

        with patch("ollama.chat", return_value=_mock_ollama(payload)):
            columns, _ = svc.generate_schema("topic", "")

        assert [c.id for c in columns] == [1, 2, 3]


# ── get_search_context tests ──────────────────────────────────────────────────

class TestGetSearchContext:
    def test_returns_context_from_search_provider(self):
        """get_search_context builds context text and urls from search results."""
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {"title": "Top AI startups", "snippet": "A list of AI companies", "url": "https://example.com/ai"},
            {"title": "Best VC funds", "snippet": "VC funding info", "url": "https://example.com/vc"},
        ]
        svc = _make_service(search_provider=mock_search)

        context_text, context_urls = svc.get_search_context("AI startups")

        assert "Top AI startups" in context_text
        assert len(context_urls) == 2
        assert context_urls[0] == "https://example.com/ai"

    def test_returns_empty_strings_when_no_search_provider(self):
        """get_search_context returns empty strings when no provider is set."""
        svc = PlannerService(model_name="qwen2.5:7b-instruct", search_provider=None)
        context_text, context_urls = svc.get_search_context("any topic")

        assert context_text == ""
        assert context_urls == []

    def test_handles_search_provider_exception_gracefully(self):
        """If the search provider throws, context is empty and no crash occurs."""
        mock_search = MagicMock()
        mock_search.search.side_effect = Exception("Network error")
        svc = _make_service(search_provider=mock_search)

        context_text, context_urls = svc.get_search_context("topic")

        assert context_text == ""
        assert context_urls == []


# ── validate_column tests ─────────────────────────────────────────────────────

class TestValidateColumn:
    def test_valid_column_returns_true(self):
        """A clearly relevant column name returns valid=True."""
        svc = _make_service()
        current = [SchemaColumn(id=1, name="company_name", type="string", reason="")]

        with patch("ollama.chat", return_value=_mock_ollama(json.dumps({"valid": True, "reason": "Makes sense"}))):
            result = svc.validate_column("deep tech startups", current, "funding_amount")

        assert result["valid"] is True
        assert isinstance(result["reason"], str)

    def test_invalid_column_returns_false(self):
        """An irrelevant column returns valid=False with a reason."""
        svc = _make_service()
        current = [SchemaColumn(id=1, name="company_name", type="string", reason="")]

        with patch("ollama.chat", return_value=_mock_ollama(json.dumps({"valid": False, "reason": "Not relevant"}))):
            result = svc.validate_column("deep tech startups", current, "eye_color")

        assert result["valid"] is False
        assert "Not relevant" in result["reason"]

    def test_falls_back_gracefully_on_invalid_json(self):
        """If LLM returns invalid JSON, fallback allows the column (valid=True)."""
        svc = _make_service()
        current = [SchemaColumn(id=1, name="company_name", type="string", reason="")]

        with patch("ollama.chat", return_value=_mock_ollama("NOT JSON")):
            result = svc.validate_column("startups", current, "any_column")

        assert result["valid"] is True  # Fail-open fallback
        assert "reason" in result
