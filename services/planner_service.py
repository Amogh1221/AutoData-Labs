import json
import ollama
from typing import List
from core.schemas import SchemaColumn, Candidate
from core.interfaces import ISearchProvider
from core.prompts import PLANNER_SCHEMA_PROMPT

class PlannerService:
    def __init__(self, model_name: str = "qwen2.5:7b-instruct", search_provider: ISearchProvider = None):
        self.model = model_name
        self.search_provider = search_provider

    def get_search_context(self, topic: str) -> tuple[str, List[str]]:
        context = ""
        context_urls = []
        if self.search_provider:
            try:
                results = self.search_provider.search(topic)
                context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in results[:5]])
                context_urls = [r['url'] for r in results[:5]]
            except Exception:
                pass
        return context, context_urls

    def generate_schema(self, topic: str, context: str) -> tuple[List[SchemaColumn], List[str]]:

        prompt = PLANNER_SCHEMA_PROMPT.format(topic=topic, context=context)
        
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        try:
            content = response['message']['content'].strip()
            
            # Remove markdown JSON wrappers if present
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            content = content.strip()
            data = json.loads(content)
            
            # Robust JSON extraction
            if isinstance(data, dict):
                # Check if it's an indexed dictionary like {"0": {...}, "1": {...}}
                if data and all(isinstance(v, dict) for v in data.values()):
                    cols = list(data.values())
                else:
                    # Find the first list in the dictionary values, if any
                    lists = [v for v in data.values() if isinstance(v, list)]
                    if lists:
                        cols = lists[0]
                    else:
                        # Treat the dictionary itself as a single column
                        cols = [data]
            elif isinstance(data, list):
                cols = data
            else:
                raise ValueError("Unexpected JSON format from LLM")
                
            columns = []
            for i, col in enumerate(cols):
                columns.append(SchemaColumn(
                    id=i+1,
                    name=col.get("name", f"field_{i}"),
                    type=col.get("type", "string"),
                    reason=col.get("reason", "")
                ))
            return columns, []
        except Exception as e:
            return [
                SchemaColumn(id=1, name="description", type="string", reason="Fallback reason")
            ], []

    def discover_entities(self, topic: str) -> List[Candidate]:
        prompt = f"You are a Research Assistant. The user wants to research '{topic}'. Give a list of 5-10 specific target names (companies, people, or products) that fall under this topic. Respond ONLY with a valid JSON array of strings representing the names."
        
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        try:
            data = json.loads(response['message']['content'])
            if isinstance(data, dict):
                data = data[list(data.keys())[0]]
                
            candidates = []
            for i, name in enumerate(data):
                candidates.append(Candidate(
                    id=str(i+1),
                    name=str(name),
                    checked=True,
                    sources=1
                ))
            return candidates
        except Exception as e:
            return [
                Candidate(id="1", name="Example Entity", checked=True, sources=1)
            ]

    def validate_column(self, topic: str, current_schema: List[SchemaColumn], new_column_name: str) -> dict:
        schema_names = [col.name for col in current_schema]
        prompt = (
            f"You are a strict Data Architect evaluating a user's request to add a new column to a dataset.\n"
            f"Topic: '{topic}'\n"
            f"Current Schema Columns: {schema_names}\n"
            f"Requested Column to Add: '{new_column_name}'\n\n"
            f"Does this requested column make logical sense to extract from the web for this topic, and is it distinct from the current columns? "
            f"Respond ONLY with a JSON object containing:\n"
            f"- 'valid': boolean (true if it makes sense to add, false if not)\n"
            f"- 'reason': string (a short, direct explanation of why it is valid or why it is rejected. If rejected, be specific about why it doesn't make sense for this topic or if it's a duplicate)."
        )

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json"
        )
        
        try:
            data = json.loads(response['message']['content'])
            return {
                "valid": bool(data.get("valid", True)),
                "reason": str(data.get("reason", ""))
            }
        except Exception as e:
            return {"valid": True, "reason": "Fallback: allowed."}
