"""H2Brain - LLM Client Wrapper

Encapsulates OpenAI-compatible SDK calls (GLM-4 / OpenAI / etc).
Provides synchronous chat and streaming chat with retry and timeout.
"""

from __future__ import annotations

import time
import logging
from typing import Iterator

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from .config import settings

logger = logging.getLogger("h2brain.llm")

_client: OpenAI | None = None

# Retry config
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds
_REQUEST_TIMEOUT = 30  # seconds


def get_client() -> OpenAI | None:
    """Return a singleton OpenAI client, or None if LLM is not configured."""
    global _client
    if not settings.llm_enabled:
        return None
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=_REQUEST_TIMEOUT,
        )
        logger.info(
            "LLM client initialized: base_url=%s model=%s",
            settings.llm_base_url,
            settings.llm_model,
        )
    return _client


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Synchronous chat completion. Returns the assistant message content.

    Raises RuntimeError if all retries are exhausted.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if not content:
                raise RuntimeError("LLM returned empty content")
            return content.strip()

        except (APITimeoutError, RateLimitError) as e:
            last_error = e
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "LLM call attempt %d/%d failed (%s), retrying in %.1fs",
                attempt,
                _MAX_RETRIES,
                type(e).__name__,
                delay,
            )
            time.sleep(delay)

        except APIError as e:
            last_error = e
            logger.error("LLM API error (attempt %d): %s", attempt, e)
            # Non-retryable for most APIErrors, but try once more
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} retries: {last_error}")


def chat_stream(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Streaming chat completion. Yields content deltas as strings.

    Raises RuntimeError if all retries are exhausted.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            stream = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return  # Success, exit generator

        except (APITimeoutError, RateLimitError) as e:
            last_error = e
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "LLM stream attempt %d/%d failed (%s), retrying in %.1fs",
                attempt,
                _MAX_RETRIES,
                type(e).__name__,
                delay,
            )
            time.sleep(delay)

        except APIError as e:
            last_error = e
            logger.error("LLM stream API error (attempt %d): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

    raise RuntimeError(f"LLM stream failed after {_MAX_RETRIES} retries: {last_error}")
