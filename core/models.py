from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum

def _utcnow() -> datetime:
    """Returns the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class EntityStatus(Enum):
    QUEUED = "queued"
    SEARCHING = "searching"
    CRAWLING = "crawling"
    EXTRACTING = "extracting"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"

class SourceStatus(Enum):
    PENDING = "pending"
    REJECTED = "rejected"
    COMPLETED = "completed"

class SourceType(Enum):
    HTML = "html"
    API = "api"
    DOCUMENT = "document"

@dataclass
class Dataset:
    dataset_id: str
    topic: str
    schema_def: str  # JSON string of schema
    created_at: datetime = field(default_factory=_utcnow)

@dataclass
class Source:
    source_id: str
    dataset_id: str
    url: str
    status: SourceStatus
    source_type: SourceType
    metadata_draft: str
    created_at: datetime = field(default_factory=_utcnow)

@dataclass
class Evidence:
    evidence_id: str
    field_id: str
    source_url: str
    snippet: str
    source_tier: int
    extracted_at: datetime

@dataclass
class FieldValue:
    field_id: str
    entity_id: str
    field_name: str
    value: Optional[str]
    confidence: float
    status: str
    evidence: List[Evidence] = field(default_factory=list)

@dataclass
class RunLog:
    log_id: str
    run_id: str
    entity_id: str
    stage: str
    outcome: str
    error_message: Optional[str]
    timestamp: datetime

@dataclass
class Entity:
    entity_id: str
    run_id: str
    canonical_name: str
    status: EntityStatus
    attempt_count: int = 0
    fields: List[FieldValue] = field(default_factory=list)
