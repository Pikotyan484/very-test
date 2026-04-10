from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from autopedia.config import Settings


def _extract_json_block(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)

    bracket = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if bracket:
        return bracket.group(1)
    return text


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        if settings.api_key and not settings.demo_mode:
            self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
    )
    def _chat(self, system_prompt: str, user_prompt: str, *, temperature: float, max_tokens: int) -> str:
        if self.client is None:
            raise RuntimeError("LLM client is not configured")
        response = self.client.chat.completions.create(
            model=self.settings.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""

    def complete_markdown(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: Callable[[], str],
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> str:
        if not self.enabled:
            return fallback()
        try:
            output = self._chat(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return output or fallback()
        except Exception:
            return fallback()

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: Callable[[], dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 2200,
    ) -> dict[str, Any]:
        if not self.enabled:
            return fallback()
        try:
            output = self._chat(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return json.loads(_extract_json_block(output))
        except Exception:
            return fallback()
