from .RerankEnums import RerankEnums
from .providers import CohereRerankProvider, HTTPRerankProvider


class RerankProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == RerankEnums.COHERE.value:
            return CohereRerankProvider(
                model_id=self.config.RERANK_MODEL_ID,
                api_key=self.config.COHERE_API_KEY,
                max_characters=self.config.RERANK_MAX_CHARACTERS,
            )

        if provider == RerankEnums.HTTP.value:
            return HTTPRerankProvider(
                api_url=self.config.RERANK_API_URL,
                model_id=self.config.RERANK_MODEL_ID,
                api_key=self.config.RERANK_API_KEY,
                max_characters=self.config.RERANK_MAX_CHARACTERS,
            )

        return None
