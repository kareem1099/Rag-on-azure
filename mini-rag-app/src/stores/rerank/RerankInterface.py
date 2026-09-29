from abc import ABC, abstractmethod
from typing import List, Optional, Tuple


class RerankInterface(ABC):

    @abstractmethod
    async def rerank(self, query: str, documents: List[str],
                     top_n: int = None) -> Optional[List[Tuple[int, float]]]: pass

    @abstractmethod
    async def close(self): pass
