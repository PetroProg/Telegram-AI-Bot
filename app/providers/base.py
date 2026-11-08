from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: str  # 'user', 'assistant', 'system'
    content: str
    image_bytes: Optional[bytes] = None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_response(
        self,
        model_id: str,
        messages: List[ChatTurn],
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate full text response from LLM."""
        pass
