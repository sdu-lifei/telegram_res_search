from typing import Optional
from fastapi import APIRouter, Depends, Query
from pansou_py.models.schemas import SearchRequest, SearchResponse
from pansou_py.api.auth import verify_token
from pansou_py.core.search import search_service

router = APIRouter()

@router.post("/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search_post(req: SearchRequest, _ = Depends(verify_token)):
    return await search_service.search(
        keyword=req.kw,
        channels=req.channels,
        force_refresh=req.refresh,
        res_type=req.res,
        src=req.src,
        plugins=req.plugins,
        cloud_types=req.cloud_types,
    )

@router.get("/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search_get(
    kw: str = Query(..., min_length=1),
    channels: Optional[str] = None,
    refresh: bool = False,
    res: str = "merge",
    src: str = "all",
    plugins: Optional[str] = None,
    cloud_types: Optional[str] = None,
    _ = Depends(verify_token)
):
    return await search_service.search(
        keyword=kw,
        channels=[c.strip() for c in channels.split(",")] if channels else None,
        force_refresh=refresh,
        res_type=res,
        src=src,
        plugins=[p.strip() for p in plugins.split(",")] if plugins else None,
        cloud_types=[c.strip() for c in cloud_types.split(",")] if cloud_types else None,
    )
