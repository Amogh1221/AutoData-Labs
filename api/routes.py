from fastapi import APIRouter, Depends
import asyncio
import json
import sqlite3
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, wait
from sse_starlette.sse import EventSourceResponse
from core import llm as llm_module
from core.llm import set_current_run_id, set_run_key, clear_run_key, HFKeyExhaustedException

from core.schemas import (
    TopicRequest, SchemaGenerateRequest, SearchContextResponse, SchemaResponse, EntityRequest,
    DiscoveryResponse, ValidateColumnRequest, ValidateColumnResponse,
    StartExtractionRequest, StartCompletionRequest, FindMoreSourcesRequest, SetApiKeyRequest, RunActionRequest
)
from api.dependencies import (
    get_store, get_planner_service, get_source_service, get_research_service, get_completion_service
)
from persistence.sqlite_store import SQLiteStore
from services.planner_service import PlannerService
from services.source_service import SourceService
from services.research_service import ResearchService
from services.completion_service import CompletionService
from core.models import RunLog, Source, Dataset, SourceStatus, SourceType

router = APIRouter()

executor = ThreadPoolExecutor(max_workers=10)

run_states = {}
run_api_keys: dict[str, str] = {}  # run_id → user-supplied HF API key (session-only)


def _wait_for_key(run_id: str, timeout_seconds: int = 300) -> str | None:
    """Block until a user key arrives for run_id, or until timeout / cancellation."""
    elapsed = 0
    while elapsed < timeout_seconds:
        if run_states.get(run_id) == "cancelled":
            return None
        key = llm_module.get_run_key(run_id)
        if key:
            return key
        time.sleep(2)
        elapsed += 2
    return None

@router.post("/api/schema/search", response_model=SearchContextResponse)
def search_schema_context(
    req: TopicRequest,
    planner: PlannerService = Depends(get_planner_service)
):
    """Fetches search context quickly before schema generation."""
    context_text, context_urls = planner.get_search_context(req.topic)
    return SearchContextResponse(context_text=context_text, context_urls=context_urls)

@router.post("/api/schema", response_model=SchemaResponse)
def generate_schema(
    req: SchemaGenerateRequest, 
    planner: PlannerService = Depends(get_planner_service)
):
    """Generates a JSON schema using Ollama based on the topic and context."""
    columns, _ = planner.generate_schema(req.topic, req.context_text)
    return SchemaResponse(columns=columns, context_urls=[])

@router.post("/api/schema/validate", response_model=ValidateColumnResponse)
def validate_column(
    req: ValidateColumnRequest,
    planner: PlannerService = Depends(get_planner_service)
):
    """Validates if a requested column makes sense for the topic."""
    result = planner.validate_column(req.topic, req.current_schema, req.new_column_name)
    return ValidateColumnResponse(valid=result["valid"], reason=result["reason"])

@router.post("/api/discover", response_model=DiscoveryResponse)
async def discover_entities(
    req: EntityRequest, 
    source_service: SourceService = Depends(get_source_service)
):
    """Discovers candidate sources using DuckDuckGo and Head-Only fetching."""
    candidates = source_service.discover_sources(req.topic)
    return DiscoveryResponse(candidates=candidates)

def _live_extraction_pipeline(topic: str, run_id: str, schema_dict: dict, required_fields: list, source_service: SourceService, research_service: ResearchService, completion_service: CompletionService, store: SQLiteStore, executor):
    """Background task that runs the Source Agent, Research Agent, and triggers concurrent Completion Agents."""
    from datetime import datetime

    # Bind run_id to this thread so core.llm can pick up user-supplied keys
    set_current_run_id(run_id)
    
    # 1. Source Agent
    sources = store.get_pending_sources(topic)
    if not sources:
        store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="source_agent_start", outcome="started", error_message=None, timestamp=datetime.utcnow()))
        
        existing_sources_cursor = store._connect().execute("SELECT url FROM sources WHERE dataset_id = ?", (topic,))
        exclude_urls = {row[0] for row in existing_sources_cursor.fetchall()}
        
        candidates = source_service.discover_sources(topic, exclude_urls=exclude_urls)
        for c in candidates:
            if c.checked:
                s = Source(
                    source_id=c.id, dataset_id=topic, url=c.url, status=SourceStatus.PENDING, source_type=SourceType(c.source_type), metadata_draft=c.metadata_draft
                )
                store.save_source(s)
                sources.append(s)
        store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="source_agent_end", outcome=f"found_{len(sources)}_sources", error_message=None, timestamp=datetime.utcnow()))
    
    def check_state_fn():
        state = run_states.get(run_id, "running")
        if state == "cancelled":
            return False
        while state in ("paused", "waiting_for_key"):
            time.sleep(1)
            state = run_states.get(run_id, "running")
            if state == "cancelled":
                return False
        return True

    seen_keys = set()
    if required_fields:
        primary_key = required_fields[0]
        existing = store.get_entities_by_run_id(run_id)
        for e in existing:
            for f in e.fields:
                if f.field_name == primary_key and f.value and str(f.value).strip().upper() != "NULL":
                    seen_keys.add(str(f.value).strip().lower())

    completion_futures = []
    api_exhausted = False  # set True when user dismisses popup without key
    
    # 2. Research Agent
    for source in sources:
        if not check_state_fn() or api_exhausted:
            break

        store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="research_agent_start", outcome=f"processing_{source.url}", error_message=None, timestamp=datetime.utcnow()))

        while True:  # retry loop for API exhaustion
            # ✅ FIX: Check cancellation at the top of every retry iteration
            if not check_state_fn():
                api_exhausted = True
                break
            try:
                entities = research_service.process_source(source, schema_dict, run_id, check_state_fn, required_fields, seen_keys)
                store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="research_agent_end", outcome=f"completed_{source.url}", error_message=None, timestamp=datetime.utcnow()))
                break
            except HFKeyExhaustedException:
                # Signal frontend via SSE
                store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="api_key_exhausted", outcome="waiting_for_key", error_message=None, timestamp=datetime.utcnow()))
                run_states[run_id] = "waiting_for_key"
                print(f"[{run_id}] HF API exhausted — waiting for user key (up to 5 min)...")
                key = _wait_for_key(run_id, timeout_seconds=300)
                if key is None:
                    print(f"[{run_id}] No key provided — finishing with partial data.")
                    api_exhausted = True
                    break
                print(f"[{run_id}] User key received — retrying.")
                run_states[run_id] = "running"
                continue
        
        # 3. Fire off concurrent Completion Agent for newly extracted entities
        if not api_exhausted and entities:
            for entity in entities:
                needs_completion = any(not f.value or str(f.value).upper() == "NULL" for f in entity.fields)
                if needs_completion:
                    fut = executor.submit(completion_service.complete_single_entity, entity, run_id, topic, schema_dict)
                    completion_futures.append(fut)
        
    # ✅ FIX: Wait for completion futures with cancellation support.
    # Poll every 1 s so Stop propagates within ~1 second instead of blocking forever.
    if completion_futures:
        remaining = list(completion_futures)
        while remaining:
            done_set, remaining_set = wait(remaining, timeout=1)
            remaining = list(remaining_set)
            if not check_state_fn():
                # Cancel anything still queued (won't kill in-progress calls,
                # but prevents new ones from starting and unblocks the pipeline).
                for f in remaining:
                    f.cancel()
                break
        
    final_state = run_states.get(run_id, "running")
    if final_state == "cancelled":
        outcome = "cancelled"
    elif api_exhausted:
        outcome = "completed_partial"
    else:
        outcome = "completed"
    store.log_run(RunLog(log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system", stage="system", outcome=outcome, error_message=None, timestamp=datetime.utcnow()))

    clear_run_key(run_id)
    if run_id in run_states:
        del run_states[run_id]


@router.post("/api/start_extraction")
async def start_extraction(
    req: StartExtractionRequest,
    source_service: SourceService = Depends(get_source_service),
    research_service: ResearchService = Depends(get_research_service),
    completion_service: CompletionService = Depends(get_completion_service),
    store = Depends(get_store)
):
    """Starts the live extraction pipeline bypassing Discovery."""
    topic = req.topic
    columns = req.columns

    schema_dict = {
        col["name"]: {
            "type": col.get("type", "string"),
            "description": col.get("reason", "")
        }
        for col in columns
    }
    required_fields = [col["name"] for col in columns if col.get("required")]

    run_id = str(uuid.uuid4())
    run_states[run_id] = "running"

    def done_callback(fut):
        run_states.pop(run_id, None)

    future = executor.submit(
        _live_extraction_pipeline,
        topic, run_id, schema_dict, required_fields,
        source_service, research_service, completion_service, store, executor
    )
    future.add_done_callback(done_callback)
    return {"run_id": run_id, "status": "started"}

@router.post("/api/start_completion")
async def start_completion(
    req: StartCompletionRequest,
    store: SQLiteStore = Depends(get_store),
    completion_service: CompletionService = Depends(get_completion_service)
):
    run_id = req.run_id
    topic = req.topic
    columns = req.columns or []  # Guard: null or missing → empty list

    schema_dict = {
        col["name"]: {
            "type": col.get("type", "string"),
            "description": col.get("reason", "")
        }
        for col in columns
    }
    
    if not run_id or not topic:
        return {"error": "Missing run_id or topic"}
        
    run_states[run_id] = "running"
    
    def done_callback(fut):
        run_states.pop(run_id, None)
        
    future = executor.submit(completion_service.run_completion, run_id, topic, schema_dict)
    future.add_done_callback(done_callback)
    return {"status": "started", "run_id": run_id}

@router.post("/api/find_more_sources")
async def find_more_sources(
    req: FindMoreSourcesRequest,
    source_service: SourceService = Depends(get_source_service),
    research_service: ResearchService = Depends(get_research_service),
    completion_service: CompletionService = Depends(get_completion_service),
    store: SQLiteStore = Depends(get_store)
):
    """Finds a new batch of sources and restarts the pipeline."""
    run_id = req.run_id
    topic = req.topic
    columns = req.columns or []
    
    if not run_id or not topic:
        return {"error": "Missing run_id or topic"}

    schema_dict = {
        col["name"]: {
            "type": col.get("type", "string"),
            "description": col.get("reason", "")
        }
        for col in columns
    }
    required_fields = [col["name"] for col in columns if col.get("required")]

    # Get existing sources to exclude
    existing_sources_cursor = store._connect().execute("SELECT url FROM sources WHERE dataset_id = ?", (topic,))
    exclude_urls = {row[0] for row in existing_sources_cursor.fetchall()}
    
    # Run discovery immediately in route or background? Better run in background.
    run_states[run_id] = "running"
    
    def done_callback(fut):
        run_states.pop(run_id, None)

    future = executor.submit(
        _live_extraction_pipeline,
        topic, run_id, schema_dict, required_fields,
        source_service, research_service, completion_service, store, executor
    )
    future.add_done_callback(done_callback)
    return {"status": "started", "run_id": run_id}

@router.get("/api/stream")
async def stream_logs(run_id: str = None):
    async def event_generator():
        last_log_time = None
        conn = sqlite3.connect("autodata.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        try:
            while True:
                query = "SELECT * FROM run_logs"
                params = ()
                
                conditions = []
                if last_log_time:
                    conditions.append("timestamp > ?")
                    params += (last_log_time,)
                if run_id:
                    conditions.append("run_id = ?")
                    params += (run_id,)
                    
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                    
                query += " ORDER BY timestamp ASC"
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    log_data = dict(row)
                    last_log_time = log_data["timestamp"]
                    yield {
                        "event": "log",
                        "data": json.dumps(log_data)
                    }
                await asyncio.sleep(0.3)
        finally:
            conn.close()

    return EventSourceResponse(event_generator())

@router.post("/api/set_api_key")
async def set_api_key(req: SetApiKeyRequest):
    """
    Accepts a user-supplied HF API key for an active run.
    The key is stored in-memory only (session-scoped) and never written to disk.
    Once stored, the blocked pipeline thread picks it up within 2 s and retries.
    """
    run_id = req.run_id
    api_key = req.api_key.strip()
    if not run_id or not api_key:
        return {"error": "Missing run_id or api_key"}
    set_run_key(run_id, api_key)
    # Resume the pipeline — it was blocked in waiting_for_key state
    if run_states.get(run_id) == "waiting_for_key":
        run_states[run_id] = "running"
    return {"status": "key_accepted"}

@router.post("/api/stop_extraction")
async def stop_extraction(req: RunActionRequest):
    run_id = req.run_id
    if run_id:
        run_states[run_id] = "cancelled"
    return {"status": "stopping"}


@router.post("/api/pause_extraction")
async def pause_extraction(req: RunActionRequest):
    run_id = req.run_id
    if run_id and run_states.get(run_id) != "cancelled":
        run_states[run_id] = "paused"
    return {"status": "paused"}

@router.post("/api/resume_extraction")
async def resume_extraction(req: RunActionRequest):
    run_id = req.run_id
    if run_id and run_states.get(run_id) != "cancelled":
        run_states[run_id] = "running"
    return {"status": "running"}

@router.get("/api/run/{run_id}/data")
async def get_run_data(run_id: str):
    conn = sqlite3.connect("autodata.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT raw_data FROM entities WHERE run_id = ?", (run_id,))
        rows = cursor.fetchall()
        
        entities = []
        for row in rows:
            data = json.loads(row["raw_data"])
            # Format nicely for the frontend
            entity_record = { "id": data.get("entity_id"), "source_url": data.get("canonical_name") }
            for field in data.get("fields", []):
                entity_record[field["field_name"]] = field["value"]
            entities.append(entity_record)
            
        return {"data": entities}
    finally:
        conn.close()
