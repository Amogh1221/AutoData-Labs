import uuid
from datetime import datetime
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

from core.models import Entity, EntityStatus, RunLog, Evidence, FieldValue
from core.interfaces import ISearchProvider, ICrawlProvider, IExtractor, ICheckpointStore, ICircuitBreaker

class PipelineState(TypedDict):
    entity: Entity

class Orchestrator:
    def __init__(
        self,
        search_provider: ISearchProvider,
        crawl_provider: ICrawlProvider,
        extractor: IExtractor,
        store: ICheckpointStore,
        circuit_breaker: ICircuitBreaker
    ):
        self.search = search_provider
        self.crawl = crawl_provider
        self.extract = extractor
        self.store = store
        self.breaker = circuit_breaker
        
        self.schema = {
            "description": "What is this entity?",
            "website": "The main website URL",
            "summary": "A short 2 sentence summary"
        }
        
        self.app = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PipelineState)
        
        # Add nodes
        builder.add_node("search", self._search_node)
        builder.add_node("crawl", self._crawl_node)
        builder.add_node("extract", self._extract_node)
        builder.add_node("verify", self._verify_node)
        
        # Add edges (linear for MVP)
        builder.add_edge(START, "search")
        builder.add_edge("search", "crawl")
        builder.add_edge("crawl", "extract")
        builder.add_edge("extract", "verify")
        builder.add_edge("verify", END)
        
        return builder.compile()

    def run_pipeline(self, topic: str, run_id: str):
        """Creates a dummy entity and invokes the langgraph application."""
        entity_id = str(uuid.uuid4())
        entity = Entity(
            entity_id=entity_id,
            run_id=run_id,
            canonical_name=topic,
            status=EntityStatus.QUEUED
        )
        self.store.save_checkpoint(entity_id, entity)
        self._log_run(entity, EntityStatus.QUEUED.value, "success")
        
        # Execute the graph
        self.app.invoke({"entity": entity})

    def resume_entity(self, entity_id: str):
        """
        In a full LangGraph implementation with checkpointing, you would pass a config thread_id.
        Since we are doing hybrid manual logging for observability, this method would be 
        adapted to inject state back into the graph. For now, run_pipeline is sufficient for MVP.
        """
        pass

    # --- LangGraph Nodes ---

    def _search_node(self, state: PipelineState) -> PipelineState:
        entity = state["entity"]
        try:
            urls = self.breaker.call(self.search.search, entity.canonical_name)
            if not urls:
                raise Exception("No URLs found")
            
            target_url = urls[0]["url"] if isinstance(urls[0], dict) else urls[0]
            
            entity.fields.append(FieldValue(
                field_id="target_url",
                entity_id=entity.entity_id,
                field_name="target_url",
                value=target_url,
                confidence=1.0,
                status="found"
            ))
            
            self._transition(entity, EntityStatus.SEARCHING)
        except Exception as error:
            self._handle_error(entity, error)
            
        return {"entity": entity}

    def _crawl_node(self, state: PipelineState) -> PipelineState:
        entity = state["entity"]
        if entity.status == EntityStatus.DEAD_LETTER: return state
        
        try:
            target_url = next((f.value for f in entity.fields if f.field_name == "target_url"), None)
            if target_url:
                text = self.breaker.call(self.crawl.fetch, target_url)
                self._temp_text = text
                self._temp_url = target_url
                self._transition(entity, EntityStatus.CRAWLING)
            else:
                raise Exception("target_url missing in fields")
        except Exception as error:
            self._handle_error(entity, error)
            
        return {"entity": entity}

    def _extract_node(self, state: PipelineState) -> PipelineState:
        entity = state["entity"]
        if entity.status == EntityStatus.DEAD_LETTER: return state
        
        try:
            text_to_extract = getattr(self, '_temp_text', "")
            url_source = getattr(self, '_temp_url', "unknown")
            
            extracted_data = self.breaker.call(self.extract.extract, self.schema, text_to_extract)
            
            for key, val in extracted_data.items():
                fv = FieldValue(
                    field_id=str(uuid.uuid4()),
                    entity_id=entity.entity_id,
                    field_name=key,
                    value=str(val) if val is not None else None,
                    confidence=0.9, 
                    status="extracted",
                    evidence=[Evidence(
                        evidence_id=str(uuid.uuid4()),
                        field_id="tbd",
                        source_url=url_source,
                        snippet=str(val)[:100] if val else "",
                        source_tier=1,
                        extracted_at=datetime.now()
                    )]
                )
                entity.fields.append(fv)
            
            self._transition(entity, EntityStatus.EXTRACTING)
        except Exception as error:
            self._handle_error(entity, error)
            
        return {"entity": entity}

    def _verify_node(self, state: PipelineState) -> PipelineState:
        entity = state["entity"]
        if entity.status == EntityStatus.DEAD_LETTER: return state
        
        self._transition(entity, EntityStatus.RESOLVED)
        return {"entity": entity}

    # --- Observability Helpers ---

    def _transition(self, entity: Entity, new_status: EntityStatus):
        entity.status = new_status
        self.store.save_checkpoint(entity.entity_id, entity)
        self._log_run(entity, new_status.value, "success")

    def _log_run(self, entity: Entity, stage: str, outcome: str, error_message: str = None):
        log = RunLog(
            log_id=str(uuid.uuid4()),
            run_id=entity.run_id,
            entity_id=entity.entity_id,
            stage=stage,
            outcome=outcome,
            error_message=error_message,
            timestamp=datetime.now()
        )
        if hasattr(self.store, 'log_run'):
            self.store.log_run(log)

    def _handle_error(self, entity: Entity, error: Exception):
        entity.attempt_count += 1
        self._log_run(entity, entity.status.value, "failed", str(error))
        self._transition(entity, EntityStatus.DEAD_LETTER)
