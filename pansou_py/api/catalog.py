import asyncio
import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
import httpx
from sqlalchemy import desc, func, select

from pansou_py.models.database import HarvestState, HotKeyword, Resource, SearchRequest, async_session

router = APIRouter()


def _parse_baidu_board(page: str, category: str) -> list[dict]:
    match = re.search(r"<!--s-data:(.*?)-->", page, re.S)
    if not match:
        return []
    content = json.loads(match.group(1))["data"]["cards"][0]["content"]
    return [{
        "title": item["word"], "keyword": item["word"], "category": category,
        "genre": item.get("show", [""])[0].removeprefix("类型："),
        "description": item.get("desc", ""), "heat": int(item.get("hotScore", 0)), "image": item.get("img", ""),
    } for item in content]


def _daily_pick(items: list[dict], now: datetime) -> list[dict]:
    return items[((now + timedelta(hours=8)).toordinal() % 2)::2][:10]


async def _baidu_recommendations() -> tuple[list[dict], str | None]:
    async with async_session() as session:
        cached = await session.get(HarvestState, "baidu_recommendations_v3")
    if cached:
        data = json.loads(cached.value)
        if datetime.fromisoformat(data["updated_at"]) > datetime.utcnow() - timedelta(hours=1):
            return data["items"], data["updated_at"]
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            movie, teleplay = await asyncio.gather(client.get("https://top.baidu.com/board?tab=movie"), client.get("https://top.baidu.com/board?tab=teleplay"))
        movie.raise_for_status(); teleplay.raise_for_status()
        ranked = sorted(_parse_baidu_board(movie.text, "电影") + _parse_baidu_board(teleplay.text, "电视剧"), key=lambda item: item["heat"], reverse=True)
        items = _daily_pick(ranked, datetime.utcnow())
        if not items:
            raise ValueError("empty Baidu ranking")
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        data = json.loads(cached.value) if cached else {}
        return data.get("items", []), data.get("updated_at")
    updated_at = datetime.utcnow().isoformat()
    payload = json.dumps({"updated_at": updated_at, "items": items}, ensure_ascii=False)
    async with async_session() as session:
        row = await session.get(HarvestState, "baidu_recommendations_v3")
        if row:
            row.value = payload
        else:
            session.add(HarvestState(key="baidu_recommendations_v3", value=payload))
        await session.commit()
    return items, updated_at


def _serialize(resource: Resource) -> dict:
    return {
        "id": resource.id,
        "keyword": resource.keyword,
        "title": resource.title,
        "description": resource.description or "",
        "disk_type": resource.disk_type,
        "source": resource.source,
        "datetime": resource.datetime.isoformat() if resource.datetime else None,
        "images": resource.images or [],
        "password": resource.owner_share_password or resource.password or "",
        "open_url": f"/r/{resource.id}",
        "score": resource.score or 0,
        "click_count": resource.click_count or 0,
    }


@router.get("/home")
async def home():
    """Homepage data is calculated on demand; browsers refresh it hourly."""
    today = (datetime.utcnow() + timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    async with async_session() as session:
        resources = await session.scalar(select(func.count(Resource.id)).where(Resource.transfer_status != "failed"))
        daily_new = await session.scalar(select(func.count(Resource.id)).where(Resource.created_at >= today, Resource.transfer_status != "failed"))
        total = await session.get(HarvestState, "total_searches")
        legacy_searches = await session.scalar(select(func.coalesce(func.sum(SearchRequest.count), 0)))
        hot = (await session.execute(
            select(HotKeyword).where(HotKeyword.source == "site_search").order_by(desc(HotKeyword.score), desc(HotKeyword.last_seen)).limit(20)
        )).scalars().all()
        if len(hot) < 20:
            legacy_hot = (await session.execute(
                select(SearchRequest).where(SearchRequest.status == "found").order_by(desc(SearchRequest.count), desc(SearchRequest.last_search)).limit(20)
            )).scalars().all()
            seen = {item.keyword for item in hot}
            hot.extend(item for item in legacy_hot if item.keyword not in seen)
    recommendations, recommendations_updated_at = await _baidu_recommendations()
    if recommendations_updated_at and not recommendations_updated_at.endswith("Z"):
        recommendations_updated_at += "Z"
    return {
        "hot_terms": [{"keyword": item.keyword, "count": item.score if isinstance(item, HotKeyword) else item.count} for item in hot[:20]],
        "stats": {"resources": resources or 0, "daily_new": daily_new or 0, "searches": int(total.value) if total and total.value.isdigit() else legacy_searches or 0},
        "recommendations": recommendations,
        "recommendations_updated_at": recommendations_updated_at,
    }


@router.get("/catalog")
async def catalog(limit: int = Query(100, ge=1, le=500)):
    async with async_session() as session:
        query = (
            select(Resource)
            .where(Resource.transfer_status != "failed")
            .order_by(desc(Resource.score), desc(Resource.click_count), desc(Resource.datetime))
            .limit(limit)
        )
        resources = (await session.execute(query)).scalars().all()
    return {"total": len(resources), "items": [_serialize(item) for item in resources]}


@router.get("/catalog/{resource_id}")
async def catalog_detail(resource_id: int):
    async with async_session() as session:
        resource = await session.get(Resource, resource_id)
    if not resource or resource.transfer_status == "failed":
        raise HTTPException(status_code=404, detail="Resource not found")
    return _serialize(resource)
