import json
import logging
import time
from typing import Any

import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import google.generativeai as genai

from bot.config import settings
from bot.metrics import (
    LLM_LATENCY,
    LLM_REQUESTS,
    LLM_SEMAPHORE_QUEUE,
    LLM_TOKENS_INPUT,
    LLM_TOKENS_OUTPUT,
)

logger = logging.getLogger(__name__)

# Global semaphore for rate limiting LLM calls
_semaphore = asyncio.Semaphore(10)


class GeminiClient:
    """Wrapper around Google Generative AI SDK with retry, rate limiting, and usage logging."""

    def __init__(self, session_factory=None):
        genai.configure(api_key=settings.GOOGLE_AI_API_KEY)
        self._model = genai.GenerativeModel(settings.GOOGLE_AI_MODEL)
        self._session_factory = session_factory

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        feature: str = "unknown",
        temperature: float = 0.5,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> str:
        """Send a prompt to Gemini and return the text response.

        Args:
            prompt: User prompt text.
            system: Optional system instruction.
            feature: Feature name for usage logging.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            json_mode: If True, request JSON output from the model.

        Returns:
            The model's text response.
        """
        LLM_SEMAPHORE_QUEUE.inc()
        async with _semaphore:
            LLM_SEMAPHORE_QUEUE.dec()
            start = time.monotonic()
            error_text = None
            input_tokens = 0
            output_tokens = 0

            try:
                model = self._model
                if system:
                    model = genai.GenerativeModel(
                        settings.GOOGLE_AI_MODEL,
                        system_instruction=system,
                    )

                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                if json_mode:
                    generation_config.response_mime_type = "application/json"

                response = await model.generate_content_async(
                    prompt,
                    generation_config=generation_config,
                )

                # Extract token usage
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count or 0
                    output_tokens = response.usage_metadata.candidates_token_count or 0

                result = response.text
                return result

            except Exception as e:
                error_text = str(e)
                logger.error("Gemini API error (feature=%s): %s", feature, e)
                raise

            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                latency_sec = latency_ms / 1000.0
                status = "error" if error_text else "success"
                LLM_REQUESTS.labels(feature=feature, status=status).inc()
                LLM_LATENCY.labels(feature=feature).observe(latency_sec)
                if input_tokens:
                    LLM_TOKENS_INPUT.labels(feature=feature).inc(input_tokens)
                if output_tokens:
                    LLM_TOKENS_OUTPUT.labels(feature=feature).inc(output_tokens)
                await self._log_usage(
                    feature=feature,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    error=error_text,
                )

    async def call_json(
        self,
        *,
        prompt: str,
        system: str | None = None,
        feature: str = "unknown",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:
        """Call Gemini and parse the response as JSON."""
        text = await self.call(
            prompt=prompt,
            system=system,
            feature=feature,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)

    async def _log_usage(
        self,
        *,
        feature: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        error: str | None,
    ) -> None:
        """Log LLM usage to the database."""
        if not self._session_factory:
            return

        try:
            from bot.db.models import LLMUsageLog

            async with self._session_factory() as session:
                log_entry = LLMUsageLog(
                    feature=feature,
                    model=settings.GOOGLE_AI_MODEL,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    error=error,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to log LLM usage: %s", e)
