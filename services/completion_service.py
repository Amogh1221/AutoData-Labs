import json
import ollama
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

from core.models import Entity, FieldValue, RunLog
from core.interfaces import ISearchProvider, ICrawlProvider
from persistence.sqlite_store import SQLiteStore
from core.prompts import COMPLETION_AGENT_PROMPT

class CompletionService:
    def __init__(self, store: SQLiteStore, search_provider: ISearchProvider, crawl_provider: ICrawlProvider, model_name: str = "llama3.2:3b"):
        self.store = store
        self.search = search_provider
        self.crawl = crawl_provider
        self.model = model_name

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def complete_single_entity(self, entity: Entity, run_id: str, topic: str, schema_dict: dict) -> None:
        """Searches for and fills in any missing field values on a single entity."""
        missing_fields = [
            (i, f) for i, f in enumerate(entity.fields)
            if not f.value or str(f.value).strip().upper() == "NULL"
        ]
        if not missing_fields:
            return

        self.store.log_run(RunLog(
            log_id=str(uuid.uuid4()), run_id=run_id, entity_id=entity.entity_id,
            stage="completion_agent_search", outcome=f"completing_{entity.canonical_name}",
            error_message=None, timestamp=self._now()
        ))

        fields_filled = 0
        for index, field in missing_fields:
            # 1. Targeted Search
            query = f"{entity.canonical_name} {field.field_name} {topic}"
            try:
                results = self.search.search(query, max_results=2)
            except Exception as e:
                print(f"Error searching for completion '{query}': {e}")
                continue

            if not results:
                continue

            # 2. Extract from top 2 results
            found_value = None
            for r in results:
                url = r["url"]
                try:
                    text_chunk = self.crawl.fetch(url)  # BUG FIX: was fetch_content
                except Exception as e:
                    print(f"Error crawling completion URL '{url}': {e}")
                    continue

                if not text_chunk:
                    continue

                text_chunk = text_chunk[:4000]

                prompt = COMPLETION_AGENT_PROMPT.format(
                    entity_name=entity.canonical_name,
                    topic=topic,
                    field_name=field.field_name,
                    field_description=schema_dict.get(field.field_name, {}).get("description", ""),
                    chunk=text_chunk
                )

                try:
                    response = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}], format="json")
                    content = response['message']['content'].strip()
                    if content.startswith("```json"): content = content[7:]
                    elif content.startswith("```"): content = content[3:]
                    if content.endswith("```"): content = content[:-3]

                    data = json.loads(content.strip())
                    extracted_val = data.get("value")

                    if extracted_val and str(extracted_val).strip().upper() != "NULL":
                        found_value = extracted_val
                        break
                except Exception as e:
                    print(f"Error extracting completion for '{field.field_name}': {e}")

            # 3. Update field if found
            if found_value:
                entity.fields[index].value = found_value
                fields_filled += 1

        if fields_filled == 0 and hasattr(self.store, 'delete_entity'):
            # The completion agent failed to find any info for the missing fields
            # Delete the row as it might be a hallucination or invalid
            self.store.delete_entity(entity.entity_id)
        else:
            # Save updated entity back to DB
            self.store.save_checkpoint(entity.entity_id, entity)

    def run_completion(self, run_id: str, topic: str, schema_dict: dict) -> None:
        """Runs completion for all entities belonging to a run."""
        entities = self.store.get_entities_by_run_id(run_id)

        self.store.log_run(RunLog(
            log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system",
            stage="completion_agent_start", outcome=f"found_{len(entities)}_entities",
            error_message=None, timestamp=self._now()
        ))

        for entity in entities:
            self.complete_single_entity(entity, run_id, topic, schema_dict)

        self.store.log_run(RunLog(
            log_id=str(uuid.uuid4()), run_id=run_id, entity_id="system",
            stage="completion_agent_end", outcome="finished",
            error_message=None, timestamp=self._now()
        ))
