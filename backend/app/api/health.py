"""H2Brain - Health Check API"""

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
