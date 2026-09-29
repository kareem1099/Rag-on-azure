from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums, DocumentTypeEnum
import cohere
import httpx
import logging
import re


class CoHereProvider(LLMInterface):

    def __init__(self, api_key: str,
                 default_input_max_characters: int = 1000,
                 default_generation_max_output_tokens: int = 1000,
                 default_generation_temperature: float = 0.1):

        self.api_key = api_key

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None

        self.embedding_model_id = None
        self.embedding_size = None

        self.client = cohere.Client(api_key=self.api_key)

        self.enums = CoHereEnums
        self.supports_grounded_generation = True
        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def generate_text(self, prompt: str, chat_history: list = None,
                      max_output_tokens: int = None, temperature: float = None):

        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for CoHere was not set")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        temperature = temperature if temperature else self.default_generation_temperature

        response = self.client.chat(
            model=self.generation_model_id,
            chat_history=chat_history,
            message=prompt,
            temperature=temperature,
            max_tokens=max_output_tokens,
        )

        if not response or not response.text:
            self.logger.error("Error while generating text with CoHere")
            return None

        return response.text

    def generate_grounded(self, query: str, documents: list, system_prompt: str = None,
                          max_output_tokens: int = None, temperature: float = None,
                          frequency_penalty: float = None, presence_penalty: float = None):

        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for CoHere was not set")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        temperature = temperature if temperature else self.default_generation_temperature

        payload = {
            "model": self.generation_model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "documents": [
                {
                    "id": doc["id"],
                    "data": {"title": doc["title"], "snippet": doc["text"]},
                }
                for doc in documents
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty

        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    "https://api.cohere.com/v2/chat",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                response_data = response.json()
        except httpx.HTTPError as error:
            self.logger.error("Error while generating grounded text with Cohere: %s", error)
            return None

        message = response_data.get("message") or {}
        content = message.get("content") or []
        answer_text = "\n".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        )
        if not answer_text:
            self.logger.error("Error while generating grounded text with CoHere")
            return None

        citations = [
            {
                "start": citation.get("start", 0),
                "end": citation.get("end", 0),
                "text": citation.get("text", ""),
                "document_ids": [
                    source["id"]
                    for source in citation.get("sources", [])
                    if source.get("type") == "document" and source.get("id")
                ],
            }
            for citation in message.get("citations", [])
        ]

        return {
            "text": answer_text,
            "citations": citations,
            "finish_reason": response_data.get("finish_reason"),
            "citation_markup_complete": True,
        }

    def embed_text(self, text, document_type: str = None):
        # text: نص واحد أو List[str] — بترجّع لستة vectors دايماً

        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.embedding_model_id:
            self.logger.error("Embedding model for CoHere was not set")
            return None

        input_type = CoHereEnums.DOCUMENT.value
        if document_type == DocumentTypeEnum.QUERY.value:
            input_type = CoHereEnums.QUERY.value

        texts = text if isinstance(text, list) else [text]
        texts = [self.process_text(t) for t in texts]

        response = self.client.embed(
            model=self.embedding_model_id,
            texts=texts,
            input_type=input_type,
            embedding_types=["float"],
        )

        if not response or not response.embeddings or not response.embeddings.float:
            self.logger.error("Error while embedding text with CoHere")
            return None

        return response.embeddings.float

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "text": prompt,
        }
