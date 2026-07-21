import uuid
import requests
from typing import List
from bs4 import BeautifulSoup

import json
from core.models import Source, SourceStatus, SourceType
from core.llm import chat, HFKeyExhaustedException
from core.schemas import Candidate
from core.interfaces import ISearchProvider
from core.prompts import SOURCE_AGENT_QUERY_PROMPT, SOURCE_AGENT_FILTER_PROMPT

class SourceService:
    def __init__(self, search_provider: ISearchProvider, model_name: str = "llama3.2:3b"):
        self.search_provider = search_provider
        self.model = model_name

    def _fetch_metadata(self, url: str) -> dict:
        """Performs a Head-Only fetch to gather metadata."""
        try:
            # We use GET with stream=True because many servers block HEAD requests
            # But we only read a small chunk to get the <head>
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, stream=True, headers=headers, timeout=(3.0, 5.0))
            content_type = response.headers.get("Content-Type", "").lower()
            
            if "application/json" in content_type:
                return {"source_type": SourceType.API, "metadata_draft": "JSON API Endpoint"}
            elif "text/csv" in content_type or url.endswith(".csv"):
                return {"source_type": SourceType.DOCUMENT, "metadata_draft": "CSV Document"}
            elif "application/pdf" in content_type:
                return {"source_type": SourceType.DOCUMENT, "metadata_draft": "PDF Document"}
            elif "text/html" in content_type:
                # Read just enough bytes to hopefully capture the <head>
                chunk = next(response.iter_content(chunk_size=8192), b"")
                response.close()
                
                soup = BeautifulSoup(chunk, "html.parser")
                title = soup.title.string if soup.title else ""
                
                desc_tag = soup.find("meta", attrs={"name": "description"})
                desc = desc_tag["content"] if desc_tag and desc_tag.has_attr("content") else ""
                
                metadata_draft = f"{title} - {desc}".strip(" -")
                if not metadata_draft:
                    metadata_draft = "HTML Webpage (No meta description found)"
                
                return {"source_type": SourceType.HTML, "metadata_draft": metadata_draft}
            else:
                response.close()
                return {"source_type": SourceType.DOCUMENT, "metadata_draft": f"Unknown Document Type: {content_type}"}
                
        except Exception as e:
            return {"source_type": SourceType.HTML, "metadata_draft": f"Failed to fetch metadata: {str(e)}"}

    def discover_sources(self, topic: str, exclude_urls: set = None) -> List[Candidate]:
        """Discovers URLs via web search and creates Candidate objects."""
        if exclude_urls is None:
            exclude_urls = set()

        # 1. Generate Queries
        prompt = SOURCE_AGENT_QUERY_PROMPT.format(topic=topic)
        response = chat(model=self.model, messages=[{"role": "user", "content": prompt}], format="json")
        try:
            content = response['message']['content'].strip()
            # Remove markdown JSON wrappers if present
            if content.startswith("```json"): content = content[7:]
            elif content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            print(f"DEBUG RAW CONTENT: {content.strip()}")
            queries = json.loads(content.strip())
            if isinstance(queries, dict):
                flat_queries = []
                for k, v in queries.items():
                    # Extract from keys if they look like queries (longer than 10 chars)
                    if len(str(k)) > 10 and "query" not in str(k).lower():
                        flat_queries.append(k)
                    if isinstance(v, list):
                        flat_queries.extend(v)
                    elif isinstance(v, str) and len(v) > 5:
                        flat_queries.append(v)
                queries = flat_queries
            
            # Ensure queries is a list of strings
            queries = [str(q).strip() for q in queries if q and len(str(q).strip()) > 5]
            if not queries:
                raise ValueError("No valid queries found")
        except Exception as e:
            print(f"Error generating queries: {e}")
            if isinstance(e, HFKeyExhaustedException):
                raise
            queries = [f"{topic} list", f"{topic} database"]
            
        print(f"DEBUG QUERIES: {queries}")
        candidates = []
        seen_urls = set()
        
        # 2. Search
        all_results = []
        for query in queries[:3]: # limit to 3 queries
            if not query or not str(query).strip(): continue
            try:
                results = self.search_provider.search(query, max_results=5)
                for r in results:
                    url = r["url"]
                    if url in seen_urls or url in exclude_urls: continue
                    seen_urls.add(url)
                    all_results.append(r)
            except Exception as e:
                print(f"Error searching for query '{query}': {e}")
                
        print(f"DEBUG ALL_RESULTS: {len(all_results)}")
        if not all_results:
            return []
            
        # 3. Filter Results
        filter_prompt = SOURCE_AGENT_FILTER_PROMPT.format(
            topic=topic, 
            results_json=json.dumps([{"url": r["url"], "title": r["title"], "snippet": r.get("snippet", "")} for r in all_results], indent=2)
        )
        try:
            filter_response = chat(model=self.model, messages=[{"role": "user", "content": filter_prompt}], format="json")
            content = filter_response['message']['content'].strip()
            if content.startswith("```json"): content = content[7:]
            elif content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            approved_flags = json.loads(content.strip())
            if isinstance(approved_flags, dict): 
                # Find the first list in the dictionary
                for val in approved_flags.values():
                    if isinstance(val, list):
                        approved_flags = val
                        break
                if isinstance(approved_flags, dict): # if still dict
                    approved_flags = [True] * len(all_results)
        except Exception as e:
            print(f"Error filtering results: {e}")
            if isinstance(e, HFKeyExhaustedException):
                raise
            approved_flags = [True] * len(all_results)
            
        print(f"DEBUG APPROVED FLAGS: {approved_flags}")
        # 4. Generate Candidates
        for i, r in enumerate(all_results):
            if i < len(approved_flags) and approved_flags[i]:
                meta = self._fetch_metadata(r["url"])
                candidate = Candidate(
                    id=str(uuid.uuid4()),
                    url=r["url"],
                    metadata_draft=meta["metadata_draft"] or r.get("snippet", ""),
                    source_type=meta["source_type"].value,
                    checked=True
                )
                candidates.append(candidate)
                
        return candidates
