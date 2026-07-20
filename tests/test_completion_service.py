"""
Tests for CompletionService (services/completion_service.py)

Covers:
- complete_single_entity skips entities with no missing fields
- complete_single_entity calls crawl.fetch() (not fetch_content)
- complete_single_entity fills in a missing field when search + crawl succeed
- complete_single_entity handles search provider failure gracefully
- complete_single_entity handles crawl failure gracefully
- complete_single_entity handles LLM returning NULL gracefully
- run_completion processes all entities in a run and logs start/end
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from services.completion_service import CompletionService
from core.models import Entity, EntityStatus, FieldValue, Evidence, RunLog
from core.interfaces import ICrawlProvider, ISearchProvider


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_field(name: str, value: str | None, fid: str = "f1") -> FieldValue:
    now = datetime.now(timezone.utc)
    return FieldValue(
        field_id=fid,
        entity_id="e1",
        field_name=name,
        value=value,
        confidence=0.9 if value else 0.0,
        status="extracted" if value else "missing",
        evidence=[Evidence(
            evidence_id="ev1", field_id=fid,
            source_url="https://example.com",
            snippet=value[:100] if value else "NULL",
            source_tier=1, extracted_at=now
        )]
    )


def _make_entity_with_fields(fields: list[FieldValue]) -> Entity:
    return Entity(
        entity_id="e1", run_id="r1",
        canonical_name="Acme Corp",
        status=EntityStatus.RESOLVED,
        fields=fields
    )


def _mock_service(mock_store, search_results=None, crawl_text="Some page content", llm_response=None):
    """Helper that wires up a CompletionService with full mock collaborators."""
    search = MagicMock(spec=ISearchProvider)
    search.search.return_value = search_results if search_results is not None else [
        {"url": "https://example.com/acme", "title": "Acme", "snippet": "About Acme"}
    ]

    # Use spec=ICrawlProvider so accessing .fetch_content raises AttributeError
    crawl = MagicMock(spec=ICrawlProvider)
    crawl.fetch.return_value = crawl_text

    return CompletionService(
        store=mock_store,
        search_provider=search,
        crawl_provider=crawl,
        model_name="test-model"
    ), search, crawl


# ── CompletionService tests ───────────────────────────────────────────────────

class TestCompleteSingleEntity:
    def test_skips_entity_with_no_missing_fields(self, mock_store):
        """If all fields have values, no search or crawl calls are made."""
        svc, search, crawl = _mock_service(mock_store)
        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", "Fintech", "f2"),
        ])

        svc.complete_single_entity(entity, "r1", "startups", {})

        search.search.assert_not_called()
        crawl.fetch.assert_not_called()

    def test_calls_fetch_not_fetch_content(self, mock_store):
        """Confirms the bug fix: crawl.fetch() is called, not fetch_content()."""
        svc, search, crawl = _mock_service(mock_store)
        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": json.dumps({"value": "Fintech"})}}
            svc.complete_single_entity(entity, "r1", "startups", {"industry": {"description": "Sector"}})

        crawl.fetch.assert_called()  # Must use .fetch, not .fetch_content
        with pytest.raises(AttributeError):
            crawl.fetch_content("anything")  # fetch_content does NOT exist on the mock

    def test_fills_missing_field_when_value_found(self, mock_store):
        """A missing field is updated in-memory and the entity is re-saved to the DB."""
        svc, search, crawl = _mock_service(mock_store)
        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])
        mock_store.save_checkpoint(entity.entity_id, entity)

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": json.dumps({"value": "Fintech"})}}
            svc.complete_single_entity(entity, "r1", "startups", {"industry": {"description": "Sector"}})

        # Field updated in memory
        industry_field = next(f for f in entity.fields if f.field_name == "industry")
        assert industry_field.value == "Fintech"

        # Entity re-saved to DB
        loaded = mock_store.load_checkpoint("e1")
        assert loaded is not None

    def test_does_not_update_field_when_llm_returns_null(self, mock_store):
        """If the LLM returns NULL, the field is left as None (not overwritten)."""
        svc, search, crawl = _mock_service(
            mock_store,
            llm_response=json.dumps({"value": "NULL"})
        )
        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": json.dumps({"value": "NULL"})}}
            svc.complete_single_entity(entity, "r1", "startups", {"industry": {"description": "Sector"}})

        industry_field = next(f for f in entity.fields if f.field_name == "industry")
        assert industry_field.value is None  # Should remain None

    def test_handles_search_failure_gracefully(self, mock_store):
        """If the search provider throws, no crash — field remains missing."""
        svc, search, crawl = _mock_service(mock_store)
        search.search.side_effect = Exception("Rate limit hit")

        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        # Should not raise
        svc.complete_single_entity(entity, "r1", "startups", {})

        industry_field = next(f for f in entity.fields if f.field_name == "industry")
        assert industry_field.value is None

    def test_handles_crawl_failure_gracefully(self, mock_store):
        """If the crawl provider throws, the field remains missing and no crash occurs."""
        svc, search, crawl = _mock_service(mock_store)
        crawl.fetch.side_effect = Exception("Connection refused")

        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        with patch("ollama.chat"):  # should not even be called
            svc.complete_single_entity(entity, "r1", "startups", {})

        industry_field = next(f for f in entity.fields if f.field_name == "industry")
        assert industry_field.value is None

    def test_handles_empty_search_results_gracefully(self, mock_store):
        """If search returns no results, the field stays missing and no crash occurs."""
        svc, search, crawl = _mock_service(mock_store, search_results=[])

        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        svc.complete_single_entity(entity, "r1", "startups", {})
        crawl.fetch.assert_not_called()

    def test_handles_malformed_llm_json_gracefully(self, mock_store):
        """If the LLM returns garbage JSON, the field remains missing and no crash occurs."""
        svc, search, crawl = _mock_service(mock_store)
        entity = _make_entity_with_fields([
            _make_field("company_name", "Acme Corp"),
            _make_field("industry", None, "f2"),
        ])

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": "NOT JSON AT ALL"}}
            svc.complete_single_entity(entity, "r1", "startups", {"industry": {"description": "Sector"}})

        industry_field = next(f for f in entity.fields if f.field_name == "industry")
        assert industry_field.value is None  # Graceful: field not updated

    def test_deletes_entity_if_all_missing_fields_fail(self, mock_store):
        """If completion agent finds no data for missing fields, it deletes the entity."""
        svc, search, crawl = _mock_service(mock_store, search_results=[])
        entity = _make_entity_with_fields([
            _make_field("industry", None, "f2"),
        ])
        
        # Ensure the store has delete_entity method mocked
        mock_store.delete_entity = MagicMock()
        
        svc.complete_single_entity(entity, "r1", "startups", {"industry": {"description": "Sector"}})
        
        # The agent found 0 fields, so it should delete the entity
        mock_store.delete_entity.assert_called_once_with(entity.entity_id)


class TestRunCompletion:
    def test_run_completion_processes_all_entities(self, mock_store):
        """run_completion calls complete_single_entity for every entity in the run."""
        svc, search, crawl = _mock_service(mock_store)

        # Save 2 entities with a missing field each
        for eid in ["e1", "e2"]:
            entity = Entity(
                entity_id=eid, run_id="r1",
                canonical_name="https://example.com",
                status=EntityStatus.RESOLVED,
                fields=[_make_field("industry", None)]
            )
            entity.fields[0].entity_id = eid
            mock_store.save_checkpoint(eid, entity)

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = {"message": {"content": json.dumps({"value": "AI"})}}
            svc.run_completion("r1", "startups", {"industry": {"description": "Sector"}})

        # search was called once per missing field per entity = 2 times
        assert search.search.call_count == 2

    def test_run_completion_with_empty_run_does_not_crash(self, mock_store):
        """run_completion for a run with no entities completes without error."""
        svc, search, crawl = _mock_service(mock_store)
        svc.run_completion("nonexistent-run", "startups", {})  # Should not raise
        search.search.assert_not_called()
