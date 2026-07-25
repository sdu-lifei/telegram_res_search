#!/usr/bin/env python3
"""Strictly validate and insert or update a manually supplied Quark resource."""

import argparse
import asyncio
import datetime as dt

import httpx
from sqlalchemy import select

from pansou_py.models.database import Resource, async_session, init_db
from scripts.resource_harvester import ValidationResult, normalize_quark_url, validate_quark_link


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--image", default="")
    args = parser.parse_args()

    url = normalize_quark_url(args.url)
    if not url:
        raise SystemExit("invalid Quark URL")

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        status, detail = await validate_quark_link(client, url)
    if status != ValidationResult.VALID:
        raise SystemExit(f"link validation failed: {status.value} ({detail})")

    await init_db()
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    images = [args.image] if args.image else []
    async with async_session() as session:
        resource = await session.scalar(select(Resource).where(Resource.url == url))
        if resource:
            resource.keyword = args.keyword
            resource.title = args.title
            resource.description = args.description
            resource.images = images
            resource.source = "manual:owner"
            resource.last_validated = now
            resource.score = max(resource.score or 0, 100)
            action = "updated"
        else:
            resource = Resource(
                keyword=args.keyword,
                title=args.title,
                description=args.description,
                url=url,
                password="",
                disk_type="quark",
                source="manual:owner",
                datetime=now,
                images=images,
                last_validated=now,
                transfer_status="none",
                score=100,
            )
            session.add(resource)
            action = "inserted"
        await session.commit()
        await session.refresh(resource)
        print(f"{action} resource_id={resource.id} validation={detail}")


if __name__ == "__main__":
    asyncio.run(main())
