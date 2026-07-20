import os
from persistence.sqlite_store import SQLiteStore
from services.orchestrator import Orchestrator
from services.planner_service import PlannerService
from services.source_service import SourceService
from services.research_service import ResearchService
from services.completion_service import CompletionService
from providers.ddg_search_provider import DuckDuckGoSearchProvider
from providers.playwright_crawl_provider import PlaywrightCrawlProvider
from providers.ollama_extractor import OllamaExtractor
from core.interfaces import ICircuitBreaker

class DummyCircuitBreaker(ICircuitBreaker):
    def call(self, provider_fn, *args, **kwargs):
        return provider_fn(*args, **kwargs)
    def is_open(self, provider_id: str) -> bool:
        return False

# Singletons
store_instance = SQLiteStore("autodata.db")
model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
search_provider_instance = DuckDuckGoSearchProvider()
planner_instance = PlannerService(model_name=model_name, search_provider=search_provider_instance)
orchestrator_instance = Orchestrator(
    search_provider=search_provider_instance,
    crawl_provider=PlaywrightCrawlProvider(),
    extractor=OllamaExtractor(model_name=model_name),
    store=store_instance,
    circuit_breaker=DummyCircuitBreaker()
)
source_service_instance = SourceService(search_provider=search_provider_instance, model_name=model_name)
research_service_instance = ResearchService(
    store=store_instance,
    crawl=PlaywrightCrawlProvider(),
    model_name=model_name
)
completion_service_instance = CompletionService(
    store=store_instance,
    search_provider=search_provider_instance,
    crawl_provider=PlaywrightCrawlProvider(),
    model_name=model_name
)

def get_store() -> SQLiteStore:
    return store_instance

def get_planner_service() -> PlannerService:
    return planner_instance

def get_source_service() -> SourceService:
    return source_service_instance

def get_orchestrator() -> Orchestrator:
    return orchestrator_instance

def get_research_service() -> ResearchService:
    return research_service_instance

def get_completion_service() -> CompletionService:
    return completion_service_instance
