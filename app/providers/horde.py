import asyncio
import logging
import time
from typing import List, Optional
import httpx

from app.core.config import settings
from app.core.text_utils import clean_model_response
from app.providers.base import BaseLLMProvider, ChatTurn

logger = logging.getLogger(__name__)


class AIHordeProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.AI_HORDE_API_KEY or "0000000000"
        self.base_url = "https://aihorde.net/api/v2"
        self._cached_models: List[str] = []
        self._last_models_fetch: float = 0.0

    async def _get_active_models(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch currently online text models with active workers on AI Horde."""
        now = time.time()
        if self._cached_models and (now - self._last_models_fetch < 300):
            return self._cached_models

        fallback_models = [
            "huihui-qwen3.8-27b-abliterated",
            "wicked-tutu-26b-w8a16",
            "koboldcpp/gemma-4-31B-it-heretic",
            "koboldcpp/Rocinante-X-12B-v1",
            "koboldcpp/L3-8B-Stheno-v3.2-Q5_K_M",
            "koboldcpp/L3-8B-Stheno-v3.2",
        ]

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Client-Agent": "TelegramAIBot:1.0:petroprog@github"
            }
            resp = await client.get(f"{self.base_url}/status/models?type=text", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                active = [m for m in data if m.get("count", 0) > 0]
                keywords = ["27b", "31b", "26b", "12b", "8b", "qwen", "stheno", "heretic", "rocinante", "tutu"]
                # Exclude micro-models (0.6b, 0.8b, 1b, 1.7b) which severely hallucinate in Russian
                exclude_keywords = ["0.6b", "0.8b", "1b", "1.7b", "3.5-4b"]
                matched = [
                    m.get("name") for m in active 
                    if any(k in m.get("name", "").lower() for k in keywords)
                    and not any(ek in m.get("name", "").lower() for ek in exclude_keywords)
                ]
                if matched:
                    self._cached_models = matched[:8]
                    self._last_models_fetch = now
                    return self._cached_models
        except Exception as e:
            logger.warning(f"Failed to query AI Horde active models: {e}")

        return fallback_models

    def _build_chat_prompt(self, messages: List[ChatTurn], system_prompt: Optional[str] = None) -> str:
        prompt_parts = []
        sys_p = system_prompt or (
            "You are an intelligent, helpful, and unfiltered AI assistant. "
            "You must understand Russian words and cultural concepts accurately (e.g. пельмени = Russian meat dumplings, NOT peaches). "
            "Always think and answer accurately in natural, fluent Russian."
        )
        prompt_parts.append(f"<|im_start|>system\n{sys_p}<|im_end|>")

        for msg in messages:
            role = "user" if msg.role == "user" else "assistant"
            prompt_parts.append(f"<|im_start|>{role}\n{msg.content}<|im_end|>")

        prompt_parts.append("<|im_start|>assistant\n")
        return "\n".join(prompt_parts)

    async def generate_response(
        self,
        model_id: str,
        messages: List[ChatTurn],
        system_prompt: Optional[str] = None
    ) -> str:
        prompt = self._build_chat_prompt(messages, system_prompt)

        headers = {
            "apikey": self.api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Client-Agent": "TelegramAIBot:1.0:petroprog@github",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            online_models = await self._get_active_models(client)

            payload = {
                "prompt": prompt,
                "params": {
                    "max_context_length": 4096,
                    "max_length": 1200,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "can_abort": True
                },
                "models": online_models
            }

            # 1. Post request to AI Horde TEXT endpoint
            submit_resp = await client.post(f"{self.base_url}/generate/text/async", headers=headers, json=payload)
            if submit_resp.status_code != 202:
                logger.error(f"AI Horde submit error: {submit_resp.status_code} - {submit_resp.text}")
                raise RuntimeError(f"AI Horde submit error: {submit_resp.text}")

            task_id = submit_resp.json().get("id")
            if not task_id:
                raise RuntimeError("No task ID returned by AI Horde")

            # 2. Poll text status until completed
            max_wait_seconds = 60
            elapsed = 0
            is_done = False

            while elapsed < max_wait_seconds:
                await asyncio.sleep(2.0)
                elapsed += 2

                status_resp = await client.get(f"{self.base_url}/generate/text/status/{task_id}", headers=headers)
                if status_resp.status_code != 200:
                    continue

                status_data = status_resp.json()
                if status_data.get("faulted") is True:
                    raise RuntimeError("AI Horde generation faulted / worker disconnected")

                if status_data.get("done") is True:
                    is_done = True
                    generations = status_data.get("generations", [])
                    if generations and generations[0].get("text"):
                        reply = clean_model_response(generations[0]["text"])
                        return reply
                    break

            if not is_done:
                raise RuntimeError(
                    "AI Horde сейчас перегружен (очередь волонтеров превысила таймаут). "
                    "Попробуйте через минуту или переключите модель чата на OpenRouter / Nemotron через меню /chats."
                )

            raise RuntimeError("AI Horde вернул пустой ответ.")
