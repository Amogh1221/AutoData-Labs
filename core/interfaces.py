from abc import ABC, abstractmethod
from typing import List, Dict, Any


class ISearchProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> List[Dict[str, str]]:
        """Returns a list of dicts containing url, title, and snippet for a given query."""
        pass


class ICrawlProvider(ABC):
    @abstractmethod
    def fetch(self, url: str) -> str:
        """Fetches and returns cleaned text from a given URL."""
        pass


class ICheckpointStore(ABC):
    @abstractmethod
    def save_checkpoint(self, entity_id: str, state: Any) -> None:
        """Saves the current state of an entity."""
        pass

    @abstractmethod
    def load_checkpoint(self, entity_id: str) -> Any:
        """Loads the last saved state of an entity."""
        pass
