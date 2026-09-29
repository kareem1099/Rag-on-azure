from ..LLMInterface import LLMInterface
from ..LLMEnums import OpenAIEnums
from openai import OpenAI, OpenAIError
import logging


class OpenAIProvider(LLMInterface):

    def __init__(self, api_key: str, api_url: str = None,
                 default_input_max_characters: int = 1000,
                 default_generation_max_output_tokens: int = 1000,
                 default_generation_temperature: float = 0.1):

        self.api_key = api_key
        self.api_url = api_url

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None

        self.embedding_model_id = None
        self.embedding_size = None

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_url if self.api_url else None,
        )

        self.enums = OpenAIEnums
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

    def generate_text(self, prompt: str, chat_history: list = None,
                      max_output_tokens: int = None, temperature: float = None):

        if not self.client:
            self.logger.error("OpenAI client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for OpenAI was not set")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        temperature = temperature if temperature else self.default_generation_temperature

        chat_history.append(
            self.construct_prompt(prompt=prompt, role=OpenAIEnums.USER.value)
        )

        response = self.client.chat.completions.create(
            model=self.generation_model_id,
            messages=chat_history,
            max_tokens=max_output_tokens,
            temperature=temperature,
        )

        if not response or not response.choices or len(response.choices) == 0 or not response.choices[0].message:
            self.logger.error("Error while generating text with OpenAI")
            return None

        return response.choices[0].message.content

    def generate_grounded(self, query: str, documents: list, system_prompt: str = None,
                          max_output_tokens: int = None, temperature: float = None,
                          frequency_penalty: float = None, presence_penalty: float = None):

        if not self.client:
            self.logger.error("OpenAI client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for OpenAI was not set")
            return None

        documents_text = "\n\n".join(
            f"<document id=\"{doc['id']}\">\n<title>{doc['title']}</title>\n<content>\n{doc['text']}\n</content>\n</document>"
            for doc in documents
        )
        messages = []
        if system_prompt:
            messages.append(self.construct_prompt(prompt=system_prompt, role=OpenAIEnums.SYSTEM.value))
        messages.append(self.construct_prompt(
            prompt=f"<documents>\n{documents_text}\n</documents>\n\n{query}",
            role=OpenAIEnums.USER.value,
        ))

        options = {}
        if frequency_penalty is not None:
            options["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            options["presence_penalty"] = presence_penalty

        try:
            response = self.client.chat.completions.create(
                model=self.generation_model_id,
                messages=messages,
                max_tokens=max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens,
                temperature=temperature if temperature else self.default_generation_temperature,
                **options,
            )
        except OpenAIError as error:
            self.logger.error("Error while generating grounded text with OpenAI: %s", error)
            return None

        if not response or not response.choices or not response.choices[0].message.content:
            self.logger.error("Error while generating grounded text with OpenAI: empty response")
            return None

        choice = response.choices[0]
        return {
            "text": choice.message.content,
            "citations": [],
            "finish_reason": "MAX_TOKENS" if choice.finish_reason == "length" else choice.finish_reason,
            "citation_markup_complete": True,
        }

    def embed_text(self, text, document_type: str = None):
        # text: نص واحد أو List[str] — بترجّع لستة vectors دايماً

        if not self.client:
            self.logger.error("OpenAI client was not set")
            return None

        if not self.embedding_model_id:
            self.logger.error("Embedding model for OpenAI was not set")
            return None

        texts = text if isinstance(text, list) else [text]
        texts = [self.process_text(t) for t in texts]

        response = self.client.embeddings.create(
            model=self.embedding_model_id,
            input=texts,
        )

        if not response or not response.data or len(response.data) == 0:
            self.logger.error("Error while embedding text with OpenAI")
            return None

        return [item.embedding for item in response.data]

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt,
        }
