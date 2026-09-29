from ..LLMInterface import LLMInterface
from ..LLMEnums import GeminiEnums
import httpx
import logging


class GeminiProvider(LLMInterface):

    def __init__(self, api_key: str,
                 api_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 default_input_max_characters: int = 1000,
                 default_generation_max_output_tokens: int = 1000,
                 default_generation_temperature: float = 0.1,
                 thinking_budget: int = None,
                 fallback_model_ids: list = None):

        self.api_key = api_key
        self.thinking_budget = thinking_budget
        self.fallback_model_ids = fallback_model_ids or []
        self.api_url = api_url.rstrip("/")

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None

        self.embedding_model_id = None
        self.embedding_size = None

        self.enums = GeminiEnums
        self.supports_grounded_generation = True
        self.supports_citations = False
        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def generate_content(self, contents: list, system_prompt: str = None,
                         max_output_tokens: int = None, temperature: float = None):

        if not self.api_key:
            self.logger.error("Gemini api key was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for Gemini was not set")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        generation_config = {
            "temperature": temperature if temperature else self.default_generation_temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if self.thinking_budget is not None:
            generation_config["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
            generation_config["maxOutputTokens"] = max_output_tokens + self.thinking_budget

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        response_data, model_id = None, None
        for model_id in [self.generation_model_id, *self.fallback_model_ids]:
            try:
                with httpx.Client(timeout=180) as client:
                    response = client.post(
                        f"{self.api_url}/models/{model_id}:generateContent",
                        headers={"x-goog-api-key": self.api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    break
            except httpx.HTTPStatusError as error:
                self.logger.error("Error while generating text with Gemini %s: %s %s",
                                  model_id, error, error.response.text[:300])
                if error.response.status_code not in (429, 500, 503):
                    return None
            except httpx.HTTPError as error:
                self.logger.error("Error while generating text with Gemini %s: %s", model_id, error)

        if response_data is None:
            return None

        candidates = response_data.get("candidates") or []
        if not candidates:
            self.logger.error("Gemini returned no candidates: %s", response_data.get("promptFeedback"))
            return None

        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        if not text:
            self.logger.error("Gemini returned empty text, finish reason: %s", candidate.get("finishReason"))
            return None

        return {"text": text, "finish_reason": candidate.get("finishReason"), "model": model_id}

    def generate_text(self, prompt: str, chat_history: list = None,
                      max_output_tokens: int = None, temperature: float = None):

        history = chat_history or []
        system_prompt = "\n".join(
            message["text"] for message in history if message["role"] == GeminiEnums.SYSTEM.value
        )
        contents = [
            {"role": message["role"], "parts": [{"text": message["text"]}]}
            for message in history if message["role"] != GeminiEnums.SYSTEM.value
        ]
        contents.append({"role": GeminiEnums.USER.value, "parts": [{"text": prompt}]})

        result = self.generate_content(contents=contents, system_prompt=system_prompt or None,
                                       max_output_tokens=max_output_tokens, temperature=temperature)
        return result["text"] if result else None

    def generate_grounded(self, query: str, documents: list, system_prompt: str = None,
                          max_output_tokens: int = None, temperature: float = None,
                          frequency_penalty: float = None, presence_penalty: float = None):

        documents_text = "\n\n".join(
            f"<document id=\"{doc['id']}\">\n<title>{doc['title']}</title>\n<content>\n{doc['text']}\n</content>\n</document>"
            for doc in documents
        )
        contents = [{
            "role": GeminiEnums.USER.value,
            "parts": [{"text": f"<documents>\n{documents_text}\n</documents>\n\n{query}"}],
        }]

        result = self.generate_content(contents=contents, system_prompt=system_prompt,
                                       max_output_tokens=max_output_tokens, temperature=temperature)
        if not result:
            return None

        return {
            "text": result["text"],
            "citations": [],
            "finish_reason": result["finish_reason"],
            "citation_markup_complete": True,
            "model": result["model"],
        }

    def embed_text(self, text, document_type: str = None):
        self.logger.error("Embedding is not supported by GeminiProvider")
        return None

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "text": prompt,
        }
