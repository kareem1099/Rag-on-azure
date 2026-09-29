from abc import ABC, abstractmethod


class LLMInterface(ABC):

    @abstractmethod
    def set_generation_model(self, model_id: str):
        pass

    @abstractmethod
    def set_embedding_model(self, model_id: str, embedding_size: int):
        pass

    @abstractmethod
    def generate_text(self, prompt: str, chat_history: list = None,
                      max_output_tokens: int = None, temperature: float = None):
        pass

    @abstractmethod
    def generate_grounded(self, query: str, documents: list, system_prompt: str = None,
                          max_output_tokens: int = None, temperature: float = None,
                          frequency_penalty: float = None, presence_penalty: float = None):
        pass

    @abstractmethod
    def embed_text(self, text, document_type: str = None):
        # text: str أو List[str] — بيرجّع لستة vectors دايماً
        pass

    @abstractmethod
    def construct_prompt(self, prompt: str, role: str):
        pass
