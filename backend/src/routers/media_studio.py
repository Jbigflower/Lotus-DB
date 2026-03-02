from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/media_studio", tags=["MediaStudio"])


@router.get("/ping")
async def ping():
    return {"status": "ok", "router": "MediaStudio"}
