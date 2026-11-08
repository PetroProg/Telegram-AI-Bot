import asyncio
import base64
import logging
from typing import List, Optional
import httpx

from app.core.config import settings
from app.providers.base import BaseLLMProvider, ChatTurn

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def generate_response(
        self,
        model_id: str,
        messages: List[ChatTurn],
        system_prompt: Optional[str] = None
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured in .env")

        clean_model = model_id.replace("gemini-", "").replace("gemini/", "")
        # Normalize model identifier
        if "2.0-flash" in model_id:
            api_model = "gemini-2.0-flash"
        elif "1.5-pro" in model_id:
            api_model = "gemini-1.5-pro"
        else:
            api_model = "gemini-1.5-flash"

        url = f"{self.base_url}/{api_model}:generateContent?key={self.api_key}"

        contents = []
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            parts = []
            if msg.image_bytes:
                b64_img = base64.b64encode(msg.image_bytes).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_img
                    }
                })
            if msg.content:
                parts.append({"text": msg.content})

            contents.append({
                "role": role,
                "parts": parts
            })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
            }
        }

        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}]
            }

        # Handle 429 rate limit with retry loop
        max_retries = 3
        backoff = 3.0

        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(max_retries):
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError("Gemini returned no candidates (content may be filtered)")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "") for p in parts if "text" in p]
                    return "".join(text_parts).strip()

                if resp.status_code == 429:
                    logger.warning(f"Gemini 429 Too Many Requests. Retrying in {backoff}s (attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                logger.error(f"Gemini API error {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")

        raise RuntimeError("Gemini API rate limit exceeded after multiple retries.")
