"""H2Brain - LLM Client Wrapper

Uses httpx directly (not OpenAI SDK) to avoid proxy/env issues in ModelScope containers.
Provides synchronous chat and streaming chat with retry, timeout, and fallback.
"""

from __future__ import annotations

import time
import json
import logging
from typing import Iterator

import httpx

from .config import settings

logger = logging.getLogger("h2brain.llm")

# Retry config - tuned for ModelScope container constraints
_MAX_RETRIES = 1
_RETRY_BASE_DELAY = 0.5  # seconds
_REQUEST_TIMEOUT = 60  # seconds (推理模型单轮含reasoning需40-50s,30s会中途掐断)

# Circuit breaker: after primary fails, skip it for this cooldown window
# (avoids wasting ~15s per ReAct iteration on a dead endpoint -> gateway 504)
_PRIMARY_COOLDOWN = 60.0
_primary_failed_at: float | None = None


def _primary_available() -> bool:
    return _primary_failed_at is None or (time.time() - _primary_failed_at) > _PRIMARY_COOLDOWN


def _mark_primary_failure() -> None:
    global _primary_failed_at
    _primary_failed_at = time.time()


def _mark_primary_success() -> None:
    global _primary_failed_at
    _primary_failed_at = None


class _LLMConfig:
    """Simple config container for an LLM endpoint."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        # Ensure base_url ends with /v1 (no trailing slash)
        self.base_url = base_url.rstrip("/")
        self.model = model


_primary: _LLMConfig | None = None
_fallback: _LLMConfig | None = None


def _init_configs():
    """Initialize LLM configs from settings."""
    global _primary, _fallback
    if _primary is None and settings.llm_enabled:
        _primary = _LLMConfig(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        logger.info(
            "LLM primary config: base_url=%s model=%s",
            _primary.base_url,
            _primary.model,
        )
    if _fallback is None and settings.llm_fallback_enabled:
        _fallback = _LLMConfig(
            api_key=settings.llm_fallback_api_key,
            base_url=settings.llm_fallback_base_url,
            model=settings.llm_fallback_model,
        )
        logger.info(
            "LLM fallback config: base_url=%s model=%s",
            _fallback.base_url,
            _fallback.model,
        )


def get_client() -> _LLMConfig | None:
    """Return primary LLM config, or None if not configured."""
    _init_configs()
    return _primary


def get_fallback_client() -> _LLMConfig | None:
    """Return fallback LLM config, or None if not configured."""
    _init_configs()
    return _fallback


def _call_with_retries(
    config: _LLMConfig,
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
            url = f"{config.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if stream:
                payload["stream"] = True
                return _stream_via_httpx(url, headers, payload)
            else:
                resp = httpx.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=_REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"LLM API returned {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                message = data["choices"][0]["message"]
                content = message.get("content") or ""
                finish_reason = data["choices"][0].get("finish_reason", "")
                if not content:
                    # 推理模型 (step 系列/deepseek-r1): 思维链在 reasoning_content
                    # 若 reasoning 耗尽 token, content 可能为空 → 用 reasoning 兜底
                    reasoning = message.get("reasoning_content") or ""
                    if reasoning:
                        logger.warning(
                            "LLM content 为空 (finish_reason=%s), 使用 reasoning_content 兜底 (%d 字符)",
                            finish_reason,
                            len(reasoning),
                        )
                        return reasoning.strip()
                    raise RuntimeError("LLM returned empty content")
                # 截断保护: finish_reason=length 时 content 可能是不完整 JSON
                if finish_reason == "length":
                    logger.warning(
                        "LLM 输出被 max_tokens 截断 (finish_reason=length), 尝试补全"
                    )
                    # 截尾到最近的完整 JSON 对象边界
                    trimmed = content.rstrip()
                    for closer in ("}}", "}"):
                        idx = trimmed.rfind(closer)
                        if idx != -1:
                            return trimmed[: idx + len(closer)].strip()
                return content.strip()

        except httpx.TimeoutException as e:
            last_error = e
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "LLM call attempt %d/%d timed out, retrying in %.1fs",
                attempt,
                _MAX_RETRIES,
                delay,
            )
            time.sleep(delay)

        except httpx.HTTPError as e:
            last_error = e
            logger.error("LLM HTTP error (attempt %d): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last_error = e
            logger.error("LLM response parse error (attempt %d): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

        except RuntimeError as e:
            # Non-200 status code or empty content
            last_error = e
            logger.error("LLM API error (attempt %d): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_DELAY)
            else:
                break

    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} retries: {last_error}")


def _stream_via_httpx(
    url: str,
    headers: dict[str, str],
    payload: dict,
) -> Iterator[str]:
    """Stream chat completion via httpx, yielding content deltas."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        with client.stream(
            "POST",
            url,
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"LLM stream API returned {resp.status_code}: {body[:300]}"
                )
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # Remove "data: " prefix
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def chat(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """Synchronous chat completion. Returns the assistant message content.

    Tries primary LLM first; if all retries fail and fallback is configured,
    tries fallback LLM. Raises RuntimeError if both fail.
    """
    config = get_client()
    if config is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    fallback = get_fallback_client()
    skip_primary = fallback is not None and not _primary_available()
    if skip_primary:
        logger.info("Primary LLM in cooldown, using fallback directly")

    if not skip_primary:
        try:
            result = _call_with_retries(
                config,
                messages,
                temperature,
                max_tokens,
                stream=False,
            )
            _mark_primary_success()
            return result  # type: ignore[return-value]

        except RuntimeError as primary_err:
            _mark_primary_failure()
            if fallback is None:
                raise
            logger.warning("Primary LLM failed, switching to fallback: %s", primary_err)

    assert fallback is not None
    try:
        result = _call_with_retries(
            fallback,
            messages,
            temperature,
            max_tokens,
            stream=False,
        )
        return result  # type: ignore[return-value]
    except RuntimeError as fallback_err:
        raise RuntimeError(f"Both primary and fallback LLM failed. Fallback: {fallback_err}")


def chat_stream(
    messages: list[dict[str, str]],
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Streaming chat completion. Yields content deltas as strings.

    Tries primary LLM first; if all retries fail and fallback is configured,
    tries fallback LLM. Raises RuntimeError if both fail.
    """
    config = get_client()
    if config is None:
        raise RuntimeError("LLM is not configured (LLM_API_KEY is empty)")

    fallback = get_fallback_client()
    skip_primary = fallback is not None and not _primary_available()
    if skip_primary:
        logger.info("Primary LLM in cooldown, using fallback stream directly")

    if not skip_primary:
        try:
            yield from _call_with_retries(  # type: ignore[misc]
                config,
                messages,
                temperature,
                max_tokens,
                stream=True,
            )
            _mark_primary_success()
            return  # Success

        except RuntimeError as primary_err:
            _mark_primary_failure()
            if fallback is None:
                raise
            logger.warning(
                "Primary LLM stream failed, switching to fallback: %s", primary_err
            )

    assert fallback is not None
    try:
        yield from _call_with_retries(  # type: ignore[misc]
            fallback,
            messages,
            temperature,
            max_tokens,
            stream=True,
        )
    except RuntimeError as fallback_err:
        raise RuntimeError(
            f"Both primary and fallback LLM stream failed. Fallback: {fallback_err}"
        )
