from fastapi import APIRouter

from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")
