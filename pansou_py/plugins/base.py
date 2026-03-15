from abc import ABC, abstractmethod
from typing import List
from pansou_py.models.schemas import SearchResult

class BasePlugin(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the plugin"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Priority: 1 is highest, 4 is lowest"""
        pass

    @abstractmethod
    async def search(self, keyword: str, **kwargs) -> List[SearchResult]:
        """Perform search and return results"""
        pass
