"""H2Brain - LLM Client Wrapper

Encapsulates OpenAI-compatible SDK calls (GLM-4 / OpenAI / etc).
Provides synchronous chat and streaming chat with retry, timeout, and fallback.
"""

from __future__ import annotations

import time
import logging
from typing import Iterator

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from .config import settings

logger = logging.getLogger("h2brain.llm")

_client: OpenAI | None = None
_fallback_client: OpenAI | None = None

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


def get_fallback_client() -> OpenAI | None:
    """Return a singleton fallback OpenAI client, or None if not configured."""
    global _fallback_client
    if not settings.llm_fallback_enabled:
        return None
    if _fallback_client is None:
        _fallback_client = OpenAI(
            api_key=settings.llm_fallback_api_key,
            base_url=settings.llm_fallback_base_url,
            timeout=_REQUEST_TIMEOUT,
        )
        logger.info(
            "LLM fallback client initialized: base_url=%s model=%s",
            settings.llm_fallback_base_url,
            settings.llm_fallback_model,
        )
    return _fallback_client


def _call_with_retries(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    stream: bool,
) -> str | Iterator[str]:
    """Call the LLM with retries. Returns content string (non-stream) or iterator (stream).

    Raises RuntimeError if all retries are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if stream:
                stream_resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                return _stream_generator(stream_resp)
            else:
                resp = client.chat.completions.create(
                    model=model,
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
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} retries: {last_error}")


def _stream_generator(stream_resp) -> Iterator[str]:
    """Convert a stream response to a generator yielding content deltas."""
    for chunk in stream_resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Synchronous chat completion. Returns the assistant message content.

    Tries primary LLM first; if all retries fail and fallback is configured,
    tries fallback LLM. Raises RuntimeError if both fail.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    try:
        result = _call_with_retries(
            client,
            settings.llm_model,
            messages,
            temperature,
            max_tokens,
            stream=False,
        )
        return result  # type: ignore[return-value]

    except RuntimeError as primary_err:
        fallback_client = get_fallback_client()
        if fallback_client is None:
            raise

        logger.warning("Primary LLM failed, switching to fallback: %s", primary_err)
        try:
            result = _call_with_retries(
                fallback_client,
                settings.llm_fallback_model,
                messages,
                temperature,
                max_tokens,
                stream=False,
            )
            return result  # type: ignore[return-value]
        except RuntimeError as fallback_err:
            raise RuntimeError(
                f"Both primary and fallback LLM failed. "
                f"Primary: {primary_err} | Fallback: {fallback_err}"
            )


def chat_stream(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Streaming chat completion. Yields content deltas as strings.

    Tries primary LLM first; if all retries fail and fallback is configured,
    tries fallback LLM. Raises RuntimeError if both fail.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    try:
        yield from _call_with_retries(  # type: ignore[misc]
            client,
            settings.llm_model,
            messages,
            temperature,
            max_tokens,
            stream=True,
        )
        return  # Success

    except RuntimeError as primary_err:
        fallback_client = get_fallback_client()
        if fallback_client is None:
            raise

        logger.warning(
            "Primary LLM stream failed, switching to fallback: %s", primary_err
        )
        try:
            yield from _call_with_retries(  # type: ignore[misc]
                fallback_client,
                settings.llm_fallback_model,
                messages,
                temperature,
                max_tokens,
                stream=True,
            )
        except RuntimeError as fallback_err:
            raise RuntimeError(
                f"Both primary and fallback LLM stream failed. "
                f"Primary: {primary_err} | Fallback: {fallback_err}"
            )
