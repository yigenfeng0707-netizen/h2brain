"""氢智行 H2Brain - 健康检查接口"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "service": "H2Brain"}


@router.get("/ready", tags=["系统"])
def ready():
    return {"status": "ready"}
