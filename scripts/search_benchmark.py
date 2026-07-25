import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUARK_CLICK_TRANSFER", "true")
os.environ.setdefault("QUARK_MOCK_TRANSFER", "true")
os.environ.setdefault("VALIDATE_LINKS", "false")

from pansou_py.core.cache import cache_service
from pansou_py.core.search import search_service
from pansou_py.core.tg_searcher import telegram_searcher
from pansou_py.models.database import init_db
import pansou_py.plugins.core  # noqa: F401


DEFAULT_KEYWORDS = [
    "庆余年",
    "凡人修仙传",
    "长安的荔枝",
    "藏海传",
    "国色芳华",
    "哪吒2",
    "歌手2025",
    "奔跑吧",
    "折腰",
    "临江仙",
    "书卷一梦",
    "酱园弄",
    "九龙城寨",
    "沙丘2",
    "周处除三害",
    "甄嬛传",
    "哈利波特",
    "权力的游戏",
    "海贼王",
    "名侦探柯南",
]


@dataclass
class KeywordResult:
    keyword: str
    success: bool
    total: int
    seconds: float
    error: str = ""


def load_keywords(path: str | None) -> List[str]:
    if not path:
        return DEFAULT_KEYWORDS
    with open(path, "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


def count_quark_links(response: dict) -> int:
    merged = response.get("merged_by_type") or {}
    if "quark" in merged:
        return len(merged["quark"])
    results = response.get("results") or []
    return sum(1 for item in results for link in item.get("links", []) if link.get("type") == "quark")


async def run_one(keyword: str, args: argparse.Namespace) -> KeywordResult:
    start = time.perf_counter()
    try:
        response = await search_service.search(
            keyword,
            force_refresh=args.refresh,
            res_type="all",
            src=args.src,
            cloud_types=["quark"],
            max_pages=args.max_pages,
            max_results=args.max_results,
            tg_timeout=args.timeout,
        )
        total = count_quark_links(response)
        return KeywordResult(
            keyword=keyword,
            success=total > 0,
            total=total,
            seconds=round(time.perf_counter() - start, 2),
        )
    except Exception as exc:
        return KeywordResult(
            keyword=keyword,
            success=False,
            total=0,
            seconds=round(time.perf_counter() - start, 2),
            error=str(exc),
        )


async def run_benchmark(keywords: Iterable[str], args: argparse.Namespace) -> dict:
    await init_db()
    if args.clear_cache:
        cache_service.clear()

    results: List[KeywordResult] = []
    semaphore = asyncio.Semaphore(args.concurrency)

    async def guarded(keyword: str) -> KeywordResult:
        async with semaphore:
            result = await run_one(keyword, args)
            status = "OK" if result.success else "MISS"
            print(f"{status:4} {result.keyword} links={result.total} seconds={result.seconds} {result.error}")
            return result

    tasks = [guarded(keyword) for keyword in keywords]
    for task in asyncio.as_completed(tasks):
        results.append(await task)

    success_count = sum(1 for result in results if result.success)
    total_count = len(results)
    success_rate = success_count / total_count if total_count else 0
    return {
        "success_rate": round(success_rate, 4),
        "success_count": success_count,
        "total_count": total_count,
        "misses": [result.keyword for result in results if not result.success],
        "results": [asdict(result) for result in sorted(results, key=lambda item: item.keyword)],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure Quark search success rate.")
    parser.add_argument("--keywords-file", help="One keyword per line. Defaults to built-in popular queries.")
    parser.add_argument("--refresh", action="store_true", help="Bypass search cache.")
    parser.add_argument("--clear-cache", action="store_true", help="Clear disk cache before running.")
    parser.add_argument("--src", default="all", choices=["all", "tg", "plugin"])
    parser.add_argument("--max-pages", type=int, default=6)
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--concurrency", type=int, default=3)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    try:
        summary = await run_benchmark(load_keywords(args.keywords_file), args)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        await telegram_searcher.close()


if __name__ == "__main__":
    asyncio.run(main())
