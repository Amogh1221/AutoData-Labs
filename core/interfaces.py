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

class IExtractor(ABC):
    @abstractmethod
    def extract(self, schema: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Extracts field values based on schema from the given text."""
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

class ICircuitBreaker(ABC):
    @abstractmethod
    def call(self, provider_fn, *args, **kwargs) -> Any:
        """Executes a provider function wrapped in circuit breaker logic."""
        pass
    
    @abstractmethod
    def is_open(self, provider_id: str) -> bool:
        """Checks if the circuit for a given provider is open (blocking calls)."""
        pass
