from pydantic import BaseModel
from typing import List, Dict, Any

class TopicRequest(BaseModel):
    topic: str

class SchemaGenerateRequest(BaseModel):
    topic: str
    context_text: str

class SearchContextResponse(BaseModel):
    context_text: str
    context_urls: List[str]

class SchemaColumn(BaseModel):
    id: int
    name: str
    type: str
    reason: str

class SchemaResponse(BaseModel):
    columns: List[SchemaColumn]
    context_urls: List[str] = []

class EntityRequest(BaseModel):
    topic: str
    columns: List[Dict[str, Any]]

class Candidate(BaseModel):
    id: str
    url: str
    metadata_draft: str
    source_type: str
    checked: bool

class DiscoveryResponse(BaseModel):
    candidates: List[Candidate]

class RunRequest(BaseModel):
    topic: str
    entities: List[str]
    schema_def: List[Dict[str, Any]]

class ValidateColumnRequest(BaseModel):
    topic: str
    current_schema: List[SchemaColumn]
    new_column_name: str

class ValidateColumnResponse(BaseModel):
    valid: bool
    reason: str
