from ..RerankInterface import RerankInterface
from typing import List
import httpx
import logging


class HTTPRerankProvider(RerankInterface):

    def __init__(self, api_url: str, model_id: str, api_key: str = None,
                 max_characters: int = 4000, timeout: float = 60):

        self.model_id = model_id
        self.max_characters = max_characters

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.AsyncClient(base_url=api_url, headers=headers, timeout=timeout)

        self.logger = logging.getLogger(__name__)

    async def rerank(self, query: str, documents: List[str], top_n: int = None):

        if not documents:
            return []

        payload = {
            "model": self.model_id,
            "query": query,
            "documents": [document[:self.max_characters] for document in documents],
            "return_documents": False,
        }
        if top_n:
            payload["top_n"] = top_n

        try:
            response = await self.client.post("rerank", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as e:
            self.logger.error(f"Error while reranking: {e}")
            return None

        results = response.json().get("results", [])

        ranked = [(item["index"], float(item["relevance_score"])) for item in results]
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    async def close(self):
        await self.client.aclose()
