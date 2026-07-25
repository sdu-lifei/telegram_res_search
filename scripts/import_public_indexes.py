#!/usr/bin/env python3
"""Rate-limited importer for explicitly public search endpoints."""

import argparse
import asyncio
import datetime as dt
import json
from typing import Any

import httpx
from sqlalchemy import select

from pansou_py.models.database import Resource, async_session, init_db

KEYWORDS = [
    "唐朝诡事录", "逐玉", "凡人修仙传", "神探狄仁杰", "低智商犯罪",
    "重返寂静岭", "仙逆", "主角", "黑袍纠察队", "南部档案",
    "家里家外", "黑夜告白", "牧神记", "剑来", "择天记",
    "熊出没", "飞驰人生3", "吞噬星空", "红楼梦", "天道",
    "庆余年", "铁拳教育", "绝命毒师", "延禧攻略", "折腰",
    "权力的游戏", "甄嬛传", "琅琊榜", "漫长的季节", "狂飙",
]


def parse_datetime(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.utcnow()
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return dt.datetime.utcnow()


async def fetch_pansou(client: httpx.AsyncClient, keyword: str, limit: int) -> list[dict[str, Any]]:
    response = await client.get(
        "https://so.252035.xyz/api/search",
        params={"kw": keyword, "res": "all", "cloud_types": "quark"},
    )
    response.raise_for_status()
    payload = json.loads(response.content.decode("utf-8", errors="replace"))
    results = payload.get("data", {}).get("results", []) if payload.get("code") == 0 else []
    rows: list[dict[str, Any]] = []
    for result in results:
        for link in result.get("links", []):
            if link.get("type") != "quark" or not link.get("url"):
                continue
            rows.append({
                "keyword": keyword,
                "title": result.get("title") or keyword,
                "description": result.get("content") or result.get("title") or "",
                "url": link["url"],
                "password": link.get("password") or "",
                "datetime": parse_datetime(result.get("datetime")),
                "source": "public:so.252035.xyz",
            })
            if len(rows) >= limit:
                return rows
    return rows


async def fetch_uuyue(client: httpx.AsyncClient, keyword: str, limit: int) -> list[dict[str, Any]]:
    response = await client.get(
        "https://uuyue.top/api/search/index",
        params={"title": keyword, "page_no": 1, "page_size": limit, "search_type": 1},
    )
    response.raise_for_status()
    payload = json.loads(response.content.decode("utf-8", errors="replace"))
    items = payload.get("data", {}).get("items", []) if payload.get("code") == 200 else []
    rows = []
    for item in items:
        url = str(item.get("url") or "")
        if "pan.quark.cn/s/" not in url:
            continue
        rows.append({
            "keyword": keyword,
            "title": item.get("name") or item.get("title") or keyword,
            "description": item.get("title") or item.get("name") or "",
            "url": url,
            "password": item.get("code") or "",
            "datetime": dt.datetime.utcnow(),
            "source": "public:uuyue.top",
        })
    return rows[:limit]


async def save_rows(rows: list[dict[str, Any]]) -> int:
    inserted = 0
    async with async_session() as session:
        for row in rows:
            exists = await session.scalar(select(Resource.id).where(Resource.url == row["url"]))
            if exists:
                continue
            session.add(Resource(
                **row,
                disk_type="quark",
                images=[],
                transfer_status="none",
                score=1,
            ))
            inserted += 1
        await session.commit()
    return inserted


async def run(limit_per_keyword: int, delay: float) -> None:
    await init_db()
    total = 0
    timeout = httpx.Timeout(30.0)
    headers = {"User-Agent": "PanSouPublicIndexer/1.0 (+https://panss.dpdns.org/)"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for keyword in KEYWORDS:
            rows: list[dict[str, Any]] = []
            for fetcher in (fetch_pansou, fetch_uuyue):
                try:
                    rows.extend(await fetcher(client, keyword, limit_per_keyword))
                except (httpx.HTTPError, ValueError) as error:
                    print(f"skip {fetcher.__name__} {keyword}: {error}")
                await asyncio.sleep(delay)
            unique = {row["url"]: row for row in rows}
            added = await save_rows(list(unique.values()))
            total += added
            print(f"{keyword}: +{added}")
    print(f"Imported {total} unique public resource links")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-keyword", type=int, default=20)
    parser.add_argument("--delay", type=float, default=0.6)
    args = parser.parse_args()
    asyncio.run(run(max(1, min(args.limit_per_keyword, 50)), max(args.delay, 0.3)))
