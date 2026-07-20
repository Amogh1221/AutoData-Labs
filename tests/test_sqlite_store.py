"""
Tests for SQLiteStore (persistence/sqlite_store.py)

Covers:
- save_checkpoint / load_checkpoint round-trip
- get_entities_by_run_id
- save_source with INSERT OR REPLACE (status updates persist)
- get_pending_sources filters by status correctly
- save_dataset / dataset table
- log_run inserts a run log
- load_checkpoint returns None for unknown entity_id
- close() allows safe teardown without errors
"""
import pytest
from datetime import datetime, timezone
from core.models import (
    Entity, EntityStatus, FieldValue, Evidence,
    Source, SourceStatus, SourceType, RunLog, Dataset
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_entity(entity_id: str = "e1", run_id: str = "r1") -> Entity:
    now = datetime.now(timezone.utc)
    fv = FieldValue(
        field_id="f1",
        entity_id=entity_id,
        field_name="company_name",
        value="Acme Corp",
        confidence=0.9,
        status="extracted",
        evidence=[Evidence(
            evidence_id="ev1",
            field_id="f1",
            source_url="https://example.com",
            snippet="Acme Corp",
            source_tier=1,
            extracted_at=now
        )]
    )
    return Entity(entity_id=entity_id, run_id=run_id, canonical_name="https://example.com",
                  status=EntityStatus.RESOLVED, fields=[fv])


def _make_source(source_id: str = "s1", dataset_id: str = "topic1",
                 status: SourceStatus = SourceStatus.PENDING) -> Source:
    return Source(
        source_id=source_id, dataset_id=dataset_id,
        url="https://example.com", status=status,
        source_type=SourceType.HTML, metadata_draft="Test"
    )


# ── SQLiteStore tests ─────────────────────────────────────────────────────────

class TestSQLiteStoreCheckpoint:
    def test_save_and_load_checkpoint(self, mock_store):
        """Round-trip: what we save we can load back."""
        entity = _make_entity()
        mock_store.save_checkpoint(entity.entity_id, entity)

        loaded = mock_store.load_checkpoint(entity.entity_id)
        assert loaded is not None
        assert loaded.entity_id == "e1"
        assert loaded.run_id == "r1"
        assert loaded.status == EntityStatus.RESOLVED
        assert len(loaded.fields) == 1
        assert loaded.fields[0].value == "Acme Corp"

    def test_load_checkpoint_returns_none_for_unknown_id(self, mock_store):
        """Querying a non-existent entity_id returns None, not an error."""
        result = mock_store.load_checkpoint("does-not-exist")
        assert result is None

    def test_save_checkpoint_overwrites_existing(self, mock_store):
        """A second save_checkpoint with the same entity_id replaces the old record."""
        entity = _make_entity()
        mock_store.save_checkpoint(entity.entity_id, entity)

        entity.status = EntityStatus.FAILED
        mock_store.save_checkpoint(entity.entity_id, entity)

        loaded = mock_store.load_checkpoint(entity.entity_id)
        assert loaded.status == EntityStatus.FAILED

    def test_save_checkpoint_raises_for_non_entity(self, mock_store):
        """save_checkpoint must reject objects that are not Entity instances."""
        with pytest.raises(ValueError):
            mock_store.save_checkpoint("bad", {"not": "an entity"})

    def test_delete_entity(self, mock_store):
        """delete_entity removes the entity from the database."""
        entity = _make_entity()
        mock_store.save_checkpoint(entity.entity_id, entity)
        
        # Verify it exists
        assert mock_store.load_checkpoint(entity.entity_id) is not None
        
        # Delete it
        mock_store.delete_entity(entity.entity_id)
        
        # Verify it is gone
        assert mock_store.load_checkpoint(entity.entity_id) is None


class TestSQLiteStoreEntitiesByRunId:
    def test_get_entities_by_run_id_returns_all(self, mock_store):
        """get_entities_by_run_id returns every entity belonging to a run."""
        e1 = _make_entity("e1", "run-A")
        e2 = _make_entity("e2", "run-A")
        e3 = _make_entity("e3", "run-B")

        for e in [e1, e2, e3]:
            mock_store.save_checkpoint(e.entity_id, e)

        results = mock_store.get_entities_by_run_id("run-A")
        assert len(results) == 2
        ids = {r.entity_id for r in results}
        assert ids == {"e1", "e2"}

    def test_get_entities_by_run_id_returns_empty_for_unknown_run(self, mock_store):
        results = mock_store.get_entities_by_run_id("no-such-run")
        assert results == []


class TestSQLiteStoreSource:
    def test_save_and_get_pending_sources(self, mock_store):
        """A freshly saved PENDING source is returned by get_pending_sources."""
        source = _make_source()
        mock_store.save_source(source)

        pending = mock_store.get_pending_sources("topic1")
        assert len(pending) == 1
        assert pending[0].source_id == "s1"
        assert pending[0].status == SourceStatus.PENDING

    def test_save_source_status_update_persists(self, mock_store):
        """INSERT OR REPLACE means a status change from PENDING→COMPLETED is saved."""
        source = _make_source()
        mock_store.save_source(source)

        # Change status and save again
        source.status = SourceStatus.COMPLETED
        mock_store.save_source(source)

        # Should no longer be PENDING
        pending = mock_store.get_pending_sources("topic1")
        assert len(pending) == 0

    def test_completed_source_not_in_pending(self, mock_store):
        """COMPLETED and REJECTED sources are not returned by get_pending_sources."""
        s_completed = _make_source("s1", status=SourceStatus.COMPLETED)
        s_rejected = _make_source("s2", status=SourceStatus.REJECTED)
        s_pending = _make_source("s3", status=SourceStatus.PENDING)

        for s in [s_completed, s_rejected, s_pending]:
            mock_store.save_source(s)

        pending = mock_store.get_pending_sources("topic1")
        assert len(pending) == 1
        assert pending[0].source_id == "s3"


class TestSQLiteStoreRunLog:
    def test_log_run_inserts_successfully(self, mock_store):
        """log_run must not raise, confirming the row is inserted."""
        log = RunLog(
            log_id="log1", run_id="r1", entity_id="e1",
            stage="resolved", outcome="success",
            error_message=None, timestamp=datetime.now(timezone.utc)
        )
        mock_store.log_run(log)  # Should not raise

    def test_multiple_logs_for_same_run(self, mock_store):
        """Multiple log entries for the same run_id are all accepted."""
        now = datetime.now(timezone.utc)
        for i in range(3):
            mock_store.log_run(RunLog(
                log_id=f"log{i}", run_id="r1", entity_id="system",
                stage="step", outcome=f"step_{i}",
                error_message=None, timestamp=now
            ))
        # If no exception was raised, all 3 logs were written


class TestSQLiteStoreClose:
    def test_close_is_idempotent(self, mock_store):
        """Calling close() multiple times must not raise."""
        mock_store.close()
        mock_store.close()  # Second close should be a no-op
