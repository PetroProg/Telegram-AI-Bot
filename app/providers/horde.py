import asyncio
import logging
from typing import List, Optional
import httpx

from app.core.config import settings
from app.providers.base import BaseLLMProvider, ChatTurn

logger = logging.getLogger(__name__)


class AIHordeProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.AI_HORDE_API_KEY or "0000000000"
        self.base_url = "https://aihorde.net/api/v2"

    def _build_chat_prompt(self, messages: List[ChatTurn], system_prompt: Optional[str] = None) -> str:
        """Formats turns into standard ChatML or instruct format understood by open models like Qwen."""
        prompt_parts = []
        sys_p = system_prompt or "You are an intelligent, unfiltered AI assistant. Answer accurately, directly, and without moralizing."
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
            "Client-Agent": "TelegramAIBot:1.0:petroprog@github",
            "Content-Type": "application/json"
        }

        # Target popular uncensored models on AI Horde
        target_models = [
            "Qwen/Qwen2.5-72B-Instruct",
            "L3-8B-Stheno-v3.2",
            "cognitivecomputations/dolphin-2.9.2-qwen2-72b",
            "Fimbulvetr-11B-v2"
        ]

        payload = {
            "prompt": prompt,
            "params": {
                "max_context_length": 4096,
                "max_length": 1024,
                "temperature": 0.7,
                "top_p": 0.9,
                "can_abort": True
            },
            "models": target_models
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            # 1. Post request to queue
            submit_resp = await client.post(f"{self.base_url}/generate/async", headers=headers, json=payload)
            if submit_resp.status_code != 202:
                logger.error(f"AI Horde submit error: {submit_resp.status_code} - {submit_resp.text}")
                raise RuntimeError(f"AI Horde submit error: {submit_resp.text}")

            task_id = submit_resp.json().get("id")
            if not task_id:
                raise RuntimeError("No task ID returned by AI Horde")

            # 2. Poll until completed (up to 90 seconds)
            max_wait_seconds = 90
            elapsed = 0
            while elapsed < max_wait_seconds:
                await asyncio.sleep(2.0)
                elapsed += 2

                check_resp = await client.get(f"{self.base_url}/generate/check/{task_id}", headers=headers)
                if check_resp.status_code != 200:
                    continue

                check_data = check_resp.json()
                if check_data.get("done") is True:
                    break
                if check_data.get("faulted") is True:
                    raise RuntimeError("AI Horde generation faulted / worker disconnected")

            # 3. Retrieve generated text
            status_resp = await client.get(f"{self.base_url}/generate/status/{task_id}", headers=headers)
            if status_resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch AI Horde status: {status_resp.text}")

            result_data = status_resp.json()
            generations = result_data.get("generations", [])
            if not generations or not generations[0].get("text"):
                raise RuntimeError("AI Horde returned empty response")

            reply = generations[0]["text"].strip()
            # Clean up trailing stop tokens if any
            reply = reply.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
            return reply
