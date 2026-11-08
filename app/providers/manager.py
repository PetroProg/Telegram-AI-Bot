import logging
from typing import List, Optional

from app.core.config import settings
from app.db.models import ModelCatalog
from app.providers.base import BaseLLMProvider, ChatTurn
from app.providers.gemini import GeminiProvider
from app.providers.horde import AIHordeProvider
from app.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


class ProviderManager:
    def __init__(self):
        self.horde = AIHordeProvider()
        self.openrouter = OpenRouterProvider()
        self.gemini = GeminiProvider()

    def get_provider(self, provider_name: str) -> BaseLLMProvider:
        p = provider_name.lower().strip()
        if p == "horde":
            return self.horde
        elif p == "openrouter":
            return self.openrouter
        elif p == "gemini":
            return self.gemini
        else:
            # Default to OpenRouter free if unknown
            return self.openrouter

    async def generate(
        self,
        model: ModelCatalog,
        messages: List[ChatTurn],
        system_prompt: Optional[str] = None,
        has_image: bool = False
    ) -> str:
        """
        Executes model inference. If has_image is True and current model is text-only,
        executes Smart Vision Routing (temporarily delegates to Gemini or OpenRouter Vision).
        """
        if has_image and not model.supports_vision:
            logger.info(f"Model '{model.id}' is text-only. Routing photo to Vision model...")
            # Route to Gemini if key available, otherwise OpenRouter Vision
            if settings.GEMINI_API_KEY:
                vision_provider = self.gemini
                vision_model = "gemini-2.0-flash"
            else:
                vision_provider = self.openrouter
                vision_model = "nvidia/nemotron-3.5-super-vl:free"

            try:
                return await vision_provider.generate_response(
                    model_id=vision_model,
                    messages=messages,
                    system_prompt=system_prompt
                )
            except Exception as e:
                logger.warning(f"Smart Vision Routing error: {e}. Trying active provider fallback...")

        provider = self.get_provider(model.provider)
        return await provider.generate_response(
            model_id=model.id,
            messages=messages,
            system_prompt=system_prompt
        )


provider_manager = ProviderManager()
