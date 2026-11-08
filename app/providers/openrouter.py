import logging
from typing import List, Optional
import httpx

from app.core.config import settings
from app.providers.base import BaseLLMProvider, ChatTurn

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"

    def _is_safe_free_model(self, model_id: str) -> bool:
        """Enforces 100% free constraint: model must end with :free or be openrouter/free."""
        mid = model_id.lower().strip()
        return mid == "openrouter/free" or mid.endswith(":free")

    async def generate_response(
        self,
        model_id: str,
        messages: List[ChatTurn],
        system_prompt: Optional[str] = None
    ) -> str:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured in .env")

        # Strip internal prefix if present
        clean_model = model_id.replace("openrouter/", "") if model_id != "openrouter/free" else model_id

        # Safety check: prevent any paid models from ever being called
        if not self._is_safe_free_model(clean_model):
            raise ValueError(f"Blocked non-free model '{clean_model}'. Strict 100% free policy enforced.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/PetroProg/Telegram-AI-Bot",
            "X-Title": "Telegram AI Bot",
            "Content-Type": "application/json",
        }

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({
                "role": "user" if msg.role == "user" else "assistant",
                "content": msg.content
            })

        payload = {
            "model": clean_model,
            "messages": formatted_messages,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"OpenRouter API error {resp.status_code}: {resp.text}")
                raise RuntimeError(f"OpenRouter error: {resp.text}")

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("OpenRouter returned empty choices")

            reply = choices[0].get("message", {}).get("content", "")
            return reply.strip()
