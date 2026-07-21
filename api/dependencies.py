import os
from persistence.sqlite_store import SQLiteStore
from services.planner_service import PlannerService
from services.source_service import SourceService
from services.research_service import ResearchService
from services.completion_service import CompletionService
from providers.ddg_search_provider import DuckDuckGoSearchProvider
from providers.playwright_crawl_provider import PlaywrightCrawlProvider

# Singletons — instantiated once at startup and injected via FastAPI Depends()
store_instance = SQLiteStore("autodata.db")
model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
search_provider_instance = DuckDuckGoSearchProvider()

planner_instance = PlannerService(
    model_name=model_name,
    search_provider=search_provider_instance
)
source_service_instance = SourceService(
    search_provider=search_provider_instance,
    model_name=model_name
)
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

def get_research_service() -> ResearchService:
    return research_service_instance

def get_completion_service() -> CompletionService:
    return completion_service_instance
