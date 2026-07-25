from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from pansou_py.models.schemas import SearchRequest, SearchResponse
from pansou_py.api.auth import verify_token
from pansou_py.core.search import search_service
from pansou_py.models.database import HarvestState, HotKeyword, SearchRequest as SearchRequestRecord, async_session


async def record_search(keyword: str) -> None:
    """Persist the two homepage counters without affecting retry scheduling."""
    keyword = keyword.strip()
    if not keyword:
        return
    async with async_session() as session:
        async with session.begin():
            total = await session.get(HarvestState, "total_searches")
            if total:
                total.value = str(int(total.value or "0") + 1)
            else:
                previous = await session.scalar(select(func.coalesce(func.sum(SearchRequestRecord.count), 0)))
                session.add(HarvestState(key="total_searches", value=str((previous or 0) + 1)))

            hot = (await session.execute(
                select(HotKeyword).where(HotKeyword.keyword == keyword, HotKeyword.source == "site_search")
            )).scalar_one_or_none()
            if hot:
                hot.score += 1
            else:
                session.add(HotKeyword(keyword=keyword, source="site_search", score=1))

router = APIRouter()

@router.post("/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search_post(req: SearchRequest, _ = Depends(verify_token)):
    if req.track:
        await record_search(req.kw)
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
    await record_search(kw)
    return await search_service.search(
        keyword=kw,
        channels=[c.strip() for c in channels.split(",")] if channels else None,
        force_refresh=refresh,
        res_type=res,
        src=src,
        plugins=[p.strip() for p in plugins.split(",")] if plugins else None,
        cloud_types=[c.strip() for c in cloud_types.split(",")] if cloud_types else None,
    )
