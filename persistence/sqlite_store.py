import sqlite3
import json
from datetime import datetime
from typing import Any, Optional
from core.interfaces import ICheckpointStore
from core.models import Entity, EntityStatus, FieldValue, Evidence, RunLog, Dataset, Source, SourceStatus, SourceType
from dataclasses import asdict

class SQLiteStore(ICheckpointStore):
    def __init__(self, db_path: str = "autodata.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Returns a thread-local connection. Opens one if not already open."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn

    def close(self) -> None:
        """Closes the database connection cleanly."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    canonical_name TEXT,
                    status TEXT,
                    attempt_count INTEGER,
                    raw_data TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS run_logs (
                    log_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    entity_id TEXT,
                    stage TEXT,
                    outcome TEXT,
                    error_message TEXT,
                    timestamp TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    topic TEXT,
                    schema_def TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    url TEXT,
                    status TEXT,
                    source_type TEXT,
                    metadata_draft TEXT,
                    created_at TEXT
                )
            ''')
            
            # Safe migration for existing DB
            try:
                cursor.execute("ALTER TABLE entities ADD COLUMN run_id TEXT")
            except sqlite3.OperationalError:
                pass
                
            try:
                cursor.execute("ALTER TABLE run_logs ADD COLUMN run_id TEXT")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def save_dataset(self, dataset: Dataset) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO datasets (dataset_id, topic, schema_def, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                dataset.dataset_id, dataset.topic, dataset.schema_def, dataset.created_at.isoformat()
            ))
            conn.commit()

    def save_source(self, source: Source) -> None:
        # INSERT OR REPLACE so that status changes (PENDING -> COMPLETED/REJECTED) are persisted
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO sources (source_id, dataset_id, url, status, source_type, metadata_draft, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                source.source_id, source.dataset_id, source.url, source.status.value,
                source.source_type.value, source.metadata_draft, source.created_at.isoformat()
            ))
            conn.commit()

    def get_pending_sources(self, dataset_id: str) -> list[Source]:
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_id, dataset_id, url, status, source_type, metadata_draft, created_at
                FROM sources
                WHERE dataset_id = ? AND status = ?
            ''', (dataset_id, SourceStatus.PENDING.value))
            rows = cursor.fetchall()
            
            sources = []
            for row in rows:
                sources.append(Source(
                    source_id=row[0],
                    dataset_id=row[1],
                    url=row[2],
                    status=SourceStatus(row[3]),
                    source_type=SourceType(row[4]),
                    metadata_draft=row[5],
                    created_at=datetime.fromisoformat(row[6])
                ))
            return sources

    def save_checkpoint(self, entity_id: str, state: Any) -> None:
        if not isinstance(state, Entity):
            raise ValueError("State must be an Entity instance")

        state_dict = asdict(state)
        state_dict['status'] = state.status.value
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO entities (entity_id, run_id, canonical_name, status, attempt_count, raw_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                state.entity_id,
                state.run_id,
                state.canonical_name,
                state.status.value,
                state.attempt_count,
                json.dumps(state_dict, default=str)
            ))
            conn.commit()

    def delete_entity(self, entity_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM entities WHERE entity_id = ?', (entity_id,))
            conn.commit()

    @staticmethod
    def _deserialize_entity(data: dict) -> Entity:
        """Reconstructs a full Entity (with nested FieldValue and Evidence) from a raw JSON dict."""
        fields = []
        for fv_dict in data.get('fields', []):
            evidence_list = []
            for ev_dict in fv_dict.get('evidence', []):
                extracted_at = ev_dict.get('extracted_at')
                if isinstance(extracted_at, str):
                    extracted_at = datetime.fromisoformat(extracted_at)
                evidence_list.append(Evidence(
                    evidence_id=ev_dict['evidence_id'],
                    field_id=ev_dict['field_id'],
                    source_url=ev_dict['source_url'],
                    snippet=ev_dict['snippet'],
                    source_tier=ev_dict['source_tier'],
                    extracted_at=extracted_at
                ))
            fields.append(FieldValue(
                field_id=fv_dict['field_id'],
                entity_id=fv_dict['entity_id'],
                field_name=fv_dict['field_name'],
                value=fv_dict.get('value'),
                confidence=fv_dict.get('confidence', 0.0),
                status=fv_dict.get('status', 'missing'),
                evidence=evidence_list
            ))
        return Entity(
            entity_id=data['entity_id'],
            run_id=data['run_id'],
            canonical_name=data['canonical_name'],
            status=EntityStatus(data['status']),
            attempt_count=data.get('attempt_count', 0),
            fields=fields
        )

    def load_checkpoint(self, entity_id: str) -> Optional[Entity]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT raw_data FROM entities WHERE entity_id = ?', (entity_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._deserialize_entity(json.loads(row[0]))
            
    def get_entities_by_run_id(self, run_id: str) -> list[Entity]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT raw_data FROM entities WHERE run_id = ?', (run_id,))
            rows = cursor.fetchall()
            return [self._deserialize_entity(json.loads(row[0])) for row in rows]
            
    def log_run(self, log: RunLog) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO run_logs (log_id, run_id, entity_id, stage, outcome, error_message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                log.log_id, log.run_id, log.entity_id, log.stage, log.outcome, log.error_message, log.timestamp.isoformat()
            ))
            conn.commit()
