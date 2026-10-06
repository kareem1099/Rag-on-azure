from .LLMEnums import LLMEnums
from .providers import OpenAIProvider, CoHereProvider, GeminiProvider


class LLMProviderFactory:

    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        if provider == LLMEnums.OPENAI.value:
            return OpenAIProvider(
                api_key=self.config.OPENAI_API_KEY,
                api_url=self.config.OPENAI_API_URL,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE,
            )

        if provider == LLMEnums.COHERE.value:
            return CoHereProvider(
                api_key=self.config.COHERE_API_KEY,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE,
            )

        if provider == LLMEnums.OPENROUTER.value:
            return OpenAIProvider(
                api_key=self.config.OPENROUTER_API_KEY,
                api_url=self.config.OPENROUTER_API_URL,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE,
            )

        if provider == LLMEnums.GEMINI.value:
            return GeminiProvider(
                api_key=self.config.GEMINI_API_KEY,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE,
                thinking_budget=self.config.GEMINI_THINKING_BUDGET,
                fallback_model_ids=[
                    model_id.strip()
                    for model_id in (self.config.GEMINI_FALLBACK_MODELS or "").split(",")
                    if model_id.strip()
                ],
                attempts_per_model=self.config.GEMINI_ATTEMPTS_PER_MODEL,
                total_timeout_seconds=self.config.GEMINI_TOTAL_TIMEOUT_SECONDS,
            )

        return None
