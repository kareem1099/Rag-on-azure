from ..RerankInterface import RerankInterface
from typing import List
import cohere
import httpx
import logging


class CohereRerankProvider(RerankInterface):

    def __init__(self, api_key: str, model_id: str,
                 max_characters: int = 4000, timeout: float = 60):

        self.model_id = model_id
        self.max_characters = max_characters
        self.httpx_client = httpx.AsyncClient(timeout=timeout)
        self.client = cohere.AsyncClient(
            api_key=api_key,
            timeout=timeout,
            httpx_client=self.httpx_client,
        )
        self.logger = logging.getLogger(__name__)

    async def rerank(self, query: str, documents: List[str], top_n: int = None):

        if not documents:
            return []

        try:
            response = await self.client.rerank(
                model=self.model_id,
                query=query,
                documents=[document[:self.max_characters] for document in documents],
                top_n=top_n,
                return_documents=False,
            )
        except Exception as error:
            self.logger.error("Error while reranking with Cohere: %s", error)
            return None

        results = [
            (item.index, float(item.relevance_score))
            for item in response.results
        ]
        return sorted(results, key=lambda item: item[1], reverse=True)

    async def close(self):
        await self.httpx_client.aclose()
