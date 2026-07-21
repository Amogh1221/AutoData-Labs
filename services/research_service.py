import json
import uuid
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from core.llm import chat, HFKeyExhaustedException, set_current_run_id

from core.models import Source, SourceStatus, FieldValue, Evidence, Entity, EntityStatus, RunLog
from core.interfaces import ICheckpointStore, ICrawlProvider
from core.prompts import RESEARCH_AGENT_EXTRACTION_PROMPT


def _extract_json_array(text: str) -> list | None:
    """
    Robustly extracts a JSON array from LLM output.
    Handles markdown code fences and partial/invalid trailing content.
    """
    # Strip markdown code fences if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start_idx = text.find('[')
    if start_idx == -1:
        return None
    text = text[start_idx:]

    # Walk backwards from the last ']' to find a valid JSON array
    end_idx = text.rfind(']')
    while end_idx != -1:
        try:
            parsed = json.loads(text[:end_idx + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        end_idx = text.rfind(']', 0, end_idx)

    return None


class ResearchService:
    def __init__(self, store: ICheckpointStore, crawl: ICrawlProvider, model_name: str = "llama3"):
        self.store = store
        self.crawl = crawl
        self.model_name = model_name

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _chunk_text(self, text: str) -> list[str]:
        """
        Chunks plain text into ~8000-character segments.
        Attempts to split on newlines to preserve sentence boundaries.
        """
        chunks = []
        chunk_size = 8000
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            # Try to break on a newline so we don't cut mid-sentence
            if end < len(text):
                newline_pos = text.rfind('\n', start, end)
                if newline_pos > start:
                    end = newline_pos
            chunks.append(text[start:end])
            start = end
        return chunks[:5]  # Limit to 5 chunks for speed

    def _chunk_html(self, html: str) -> list[str]:
        """Semantically chunks HTML then falls back to plain text chunking."""
        soup = BeautifulSoup(html, "html.parser")
        chunks = []

        # Prefer semantic containers
        containers = soup.find_all(['article', 'section', 'table'])
        if not containers:
            containers = soup.find_all('div')

        for c in containers:
            text = c.get_text(separator=" ", strip=True)
            if len(text) > 100:
                chunks.append(text[:8000])

        if not chunks:
            # Fallback: chunk the entire page text
            full_text = soup.get_text(separator=" ", strip=True)
            chunks = self._chunk_text(full_text)

        return chunks[:5]

    def _call_llm(self, schema: dict, chunk: str, required_fields: list[str]) -> list[dict]:
        """Calls the LLM with the extraction prompt and returns parsed rows."""
        req_instruction = ""
        if required_fields:
            req_instruction = (
                f"8. REQUIRED FIELDS: The following fields are highly important: {', '.join(required_fields)}. "
                f"If you can find the primary field ({required_fields[0]}), extract the row even if other "
                f"required fields are missing (use null for those)."
            )

        prompt = RESEARCH_AGENT_EXTRACTION_PROMPT.format(
            schema=json.dumps(schema, indent=2),
            chunk=chunk,
            required_fields_instruction=req_instruction
        )

        set_current_run_id(getattr(self, '_current_run_id', None) or '')
        response = chat(
            model=self.model_name,
            messages=[
                {'role': 'system', 'content': 'You are a precise data extraction system. You only output valid JSON arrays without any markdown formatting.'},
                {'role': 'user', 'content': prompt}
            ]
        )

        content = response['message']['content'].strip()
        print(f"DEBUG LLM CONTENT:\n{content}\n---")

        rows = _extract_json_array(content)
        if rows is not None:
            print(f"DEBUG EXTRACTED {len(rows)} ITEMS FROM JSON ARRAY")
            return rows

        print(f"No JSON array found in LLM output.")
        return []

    def _build_entity(self, row: dict, source: Source, run_id: str, primary_key: str) -> Entity:
        """Converts an extracted row dict into an Entity with FieldValues."""
        entity_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(row.get(primary_key, uuid.uuid4()))))
        entity = Entity(
            entity_id=entity_id,
            run_id=run_id,
            canonical_name=source.url,
            status=EntityStatus.RESOLVED
        )

        for field_name, val in row.items():
            # Normalise NULL variants to Python None
            if val is None or (isinstance(val, str) and val.strip().upper() == "NULL"):
                val = None
            else:
                val = str(val)

            fv = FieldValue(
                field_id=str(uuid.uuid4()),
                entity_id=entity_id,
                field_name=field_name,
                value=val,
                confidence=0.9 if val else 0.0,
                status="extracted" if val else "missing",
                evidence=[Evidence(
                    evidence_id=str(uuid.uuid4()),
                    field_id="tbd",
                    source_url=source.url,
                    snippet=val[:100] if val else "NULL",
                    source_tier=1,
                    extracted_at=self._now()
                )]
            )
            entity.fields.append(fv)

        return entity

    def process_source(
        self,
        source: Source,
        schema: dict,
        run_id: str,
        check_state_fn=None,
        required_fields: list[str] | None = None,
        seen_keys: set | None = None
    ) -> list[Entity] | None:
        self._current_run_id = run_id
        set_current_run_id(run_id)
        """Crawls a source, chunks it, extracts and immediately persists each row."""
        primary_key = required_fields[0] if required_fields else None
        if seen_keys is None:
            seen_keys = set()

        try:
            # 1. Crawl (can be slow — Playwright/BeautifulSoup)
            html = self.crawl.fetch(source.url)

            # ✅ FIX: Check cancellation immediately after the long crawl
            if check_state_fn and not check_state_fn():
                return None

            # 2. Chunk
            chunks = self._chunk_html(html)

            entities: list[Entity] = []

            # 3. Extract per chunk — save each valid row immediately (streaming)
            for chunk in chunks:
                if check_state_fn and not check_state_fn():
                    break
                try:
                    rows = self._call_llm(schema, chunk, required_fields or [])
                except HFKeyExhaustedException:
                    raise  # Let the pipeline handle this
                except Exception as e:
                    print(f"Extraction failed on a chunk for {source.url}: {e}")
                    continue

                for row in rows:
                    # 4. Deduplicate — drop rows missing the primary key or already seen
                    if primary_key:
                        pk_val = row.get(primary_key)
                        if not pk_val or str(pk_val).strip().upper() == "NULL" or str(pk_val).strip() == "":
                            continue  # Must have a primary key value

                        pk_lower = str(pk_val).strip().lower()
                        if pk_lower in seen_keys:
                            continue
                        seen_keys.add(pk_lower)

                    # 5. Build entity and persist IMMEDIATELY — frontend sees it on next poll
                    entity = self._build_entity(row, source, run_id, primary_key or "")
                    self.store.save_checkpoint(entity.entity_id, entity)
                    if hasattr(self.store, 'log_run'):
                        self.store.log_run(RunLog(
                            log_id=str(uuid.uuid4()),
                            run_id=run_id,
                            entity_id=entity.entity_id,
                            stage="resolved",
                            outcome="success",
                            error_message=None,
                            timestamp=self._now()
                        ))
                    entities.append(entity)

            if not entities:
                source.status = SourceStatus.REJECTED
                source.metadata_draft += " (Rejected: No valid rows extracted)"
                if hasattr(self.store, 'save_source'):
                    self.store.save_source(source)
                return None

            source.status = SourceStatus.COMPLETED
            if hasattr(self.store, 'save_source'):
                self.store.save_source(source)

            return entities

        except HFKeyExhaustedException:
            raise  # Propagate quota errors to the pipeline
        except Exception as e:
            print(f"ResearchService error for {source.url}: {e}")
            source.status = SourceStatus.REJECTED
            source.metadata_draft += f" (Failed: {str(e)})"
            if hasattr(self.store, 'save_source'):
                self.store.save_source(source)
            return None
