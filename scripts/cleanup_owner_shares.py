import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import or_, select

from pansou_py.models.database import Resource, async_session, init_db


def parse_csv_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    ids = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def compact(value: str | None, limit: int = 64) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


async def load_candidates(args: argparse.Namespace) -> list[Resource]:
    cutoff = datetime.utcnow() - timedelta(days=args.older_than_days)
    include_ids = parse_csv_ids(args.ids)
    exclude_ids = parse_csv_ids(args.exclude_ids)

    query = select(Resource).where(Resource.owner_share_url.is_not(None))

    if include_ids:
        query = query.where(Resource.id.in_(include_ids))
    else:
        query = query.where(
            or_(Resource.transferred_at.is_(None), Resource.transferred_at < cutoff),
            or_(Resource.last_clicked_at.is_(None), Resource.last_clicked_at < cutoff),
            (Resource.click_count.is_(None)) | (Resource.click_count <= args.max_clicks),
        )

    if exclude_ids:
        query = query.where(Resource.id.not_in(exclude_ids))

    query = query.order_by(
        Resource.last_clicked_at.asc().nullsfirst(),
        Resource.transferred_at.asc().nullsfirst(),
        Resource.id.asc(),
    )
    if args.limit:
        query = query.limit(args.limit)

    async with async_session() as session:
        return (await session.execute(query)).scalars().all()


def print_table(rows: list[Resource]) -> None:
    if not rows:
        print("No owner-share records matched the filters.")
        return

    print("id | clicks | transferred_at | last_clicked_at | title")
    print("-" * 96)
    for row in rows:
        print(
            f"{row.id} | "
            f"{row.click_count or 0} | "
            f"{row.transferred_at or '-'} | "
            f"{row.last_clicked_at or '-'} | "
            f"{compact(row.title)}"
        )


def write_csv(rows: list[Resource], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "id",
                "keyword",
                "title",
                "source_url",
                "owner_share_url",
                "click_count",
                "transferred_at",
                "last_clicked_at",
                "owner_fids",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.id,
                    row.keyword or "",
                    row.title or "",
                    row.url or "",
                    row.owner_share_url or "",
                    row.click_count or 0,
                    row.transferred_at or "",
                    row.last_clicked_at or "",
                    row.owner_fids or "",
                ]
            )


async def clear_owner_share_records(rows: list[Resource]) -> int:
    ids = [row.id for row in rows]
    if not ids:
        return 0

    async with async_session() as session:
        async with session.begin():
            db_rows = (await session.execute(select(Resource).where(Resource.id.in_(ids)))).scalars().all()
            for row in db_rows:
                row.owner_share_url = None
                row.owner_share_password = None
                row.owner_fids = None
                row.transfer_status = "none"
                row.transfer_error = None
                row.transferred_at = None
    return len(ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or clear database owner-share records. This does not delete Quark files."
    )
    parser.add_argument("--db", default=os.getenv("DATABASE_PATH", "./pansou.db"), help="SQLite database path.")
    parser.add_argument("--older-than-days", type=int, default=7, help="Only include records older than this many days.")
    parser.add_argument("--max-clicks", type=int, default=0, help="Only include records with click_count <= this value.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum records to process. Use 0 for no limit.")
    parser.add_argument("--ids", help="Comma-separated resource ids to include, bypassing age/click filters.")
    parser.add_argument("--exclude-ids", help="Comma-separated resource ids to exclude.")
    parser.add_argument("--csv", help="Write the preview list to a CSV file.")
    parser.add_argument("--apply", action="store_true", help="Actually clear matched database records.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    os.environ["DATABASE_PATH"] = args.db
    await init_db()

    rows = await load_candidates(args)
    print_table(rows)
    if args.csv:
        write_csv(rows, args.csv)
        print(f"\nWrote CSV: {args.csv}")

    if not args.apply:
        print(f"\nDry run only. Matched {len(rows)} records. Add --apply to clear database owner-share fields.")
        return

    cleared = await clear_owner_share_records(rows)
    print(f"\nCleared owner-share fields for {cleared} database records.")
    print("Quark files were not deleted. Delete them manually from your dedicated Quark folder.")


if __name__ == "__main__":
    asyncio.run(main())
