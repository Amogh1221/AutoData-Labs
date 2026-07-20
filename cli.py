import os
import sqlite3
import json
from dotenv import load_dotenv
from providers.ddg_search_provider import DuckDuckGoSearchProvider
from providers.bs4_crawl_provider import BasicCrawlProvider
from providers.ollama_extractor import OllamaExtractor
from persistence.sqlite_store import SQLiteStore
from services.orchestrator import Orchestrator
from core.interfaces import ICircuitBreaker

load_dotenv()

class DummyCircuitBreaker(ICircuitBreaker):
    def call(self, provider_fn, *args, **kwargs):
        return provider_fn(*args, **kwargs)
    
    def is_open(self, provider_id: str) -> bool:
        return False

def print_db_contents():
    print("\n--- Database Contents ---")
    with sqlite3.connect("autodata.db") as conn:
        cursor = conn.cursor()
        print("Entities:")
        cursor.execute("SELECT entity_id, canonical_name, status, raw_data FROM entities")
        for row in cursor.fetchall():
            print(f"ID: {row[0]}, Name: {row[1]}, Status: {row[2]}")
            # Print the extracted fields
            data = json.loads(row[3])
            fields = data.get('fields', [])
            for field in fields:
                if field['field_name'] != 'target_url':
                    print(f"  -> {field['field_name']}: {field['value']}")

def main():
    print("Initializing AutoData Labs Pipeline...")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    print(f"Using Ollama Model: {model}")
    
    search = DuckDuckGoSearchProvider()
    crawl = BasicCrawlProvider()
    extractor = OllamaExtractor(model_name=model)
    store = SQLiteStore("autodata.db")
    breaker = DummyCircuitBreaker()
    
    orchestrator = Orchestrator(search, crawl, extractor, store, breaker)
    
    topic = "Anthropic Claude AI"
    print(f"\nRunning pipeline for topic: {topic}")
    orchestrator.run_pipeline(topic)
    
    print("\nPipeline completed.")
    print_db_contents()
    
if __name__ == "__main__":
    main()
