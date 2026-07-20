from typing import List, Dict
from ddgs import DDGS
from core.interfaces import ISearchProvider

class DuckDuckGoSearchProvider(ISearchProvider):
    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, query: str, max_results: int = None) -> List[Dict[str, str]]:
        limit = max_results if max_results is not None else self.max_results
        try:
            results = DDGS(timeout=10).text(query, max_results=limit)
        except Exception:
            return []
        return [
            {
                "url": r.get('href', ''),
                "title": r.get('title', ''),
                "snippet": r.get('body', '')
            }
            for r in results
        ] if results else []
