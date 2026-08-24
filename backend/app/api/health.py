"""H2Brain - Health Check API"""

import time
from fastapi import APIRouter

from ..config import settings

router = APIRouter()


@router.get("/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "service": "H2Brain",
        "version": "0.2.0",
        "llm_enabled": settings.llm_enabled,
        "llm_model": settings.llm_model if settings.llm_enabled else None,
    }


@router.get("/ready", tags=["System"])
def ready():
    return {"status": "ready", "llm_enabled": settings.llm_enabled}


@router.get("/llm-diag", tags=["System"])
def llm_diag():
    """Diagnose LLM connectivity from inside the container."""
    import httpx

    results = {}

    # Test primary LLM endpoint
    primary_url = settings.llm_base_url.rstrip("/")
    results["primary"] = {
        "base_url": primary_url,
        "model": settings.llm_model,
        "api_key_prefix": settings.llm_api_key[:10] + "..."
        if settings.llm_api_key
        else "EMPTY",
    }
    try:
        t0 = time.time()
        resp = httpx.post(
            f"{primary_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        results["primary"]["status_code"] = resp.status_code
        results["primary"]["elapsed_s"] = round(time.time() - t0, 2)
        results["primary"]["body_preview"] = resp.text[:500]
    except Exception as e:
        results["primary"]["error"] = f"{type(e).__name__}: {e}"
        results["primary"]["elapsed_s"] = (
            round(time.time() - t0, 2) if "t0" in dir() else None
        )

    # Test fallback LLM endpoint
    if settings.llm_fallback_enabled:
        fallback_url = settings.llm_fallback_base_url.rstrip("/")
        results["fallback"] = {
            "base_url": fallback_url,
            "model": settings.llm_fallback_model,
            "api_key_prefix": settings.llm_fallback_api_key[:10] + "..."
            if settings.llm_fallback_api_key
            else "EMPTY",
        }
        try:
            t0 = time.time()
            resp = httpx.post(
                f"{fallback_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_fallback_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_fallback_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 10,
                },
                timeout=15,
            )
            results["fallback"]["status_code"] = resp.status_code
            results["fallback"]["elapsed_s"] = round(time.time() - t0, 2)
            results["fallback"]["body_preview"] = resp.text[:500]
        except Exception as e:
            results["fallback"]["error"] = f"{type(e).__name__}: {e}"

    return results
