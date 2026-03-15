import asyncio
from pansou_py.core.tg_searcher import telegram_searcher
from pansou_py.core.config import settings

async def main():
    # settings.PROXY = "http://127.0.0.1:4780"  # Uncomment if you need a proxy
    print("Testing tg_searcher...")
    try:
        url = telegram_searcher.build_search_url("tgsearchers5", "百度")
        html = await telegram_searcher.fetch_html(url)
        with open("raw.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved raw HTML to raw.html (Length {len(html)})")
    except Exception as e:
        print(f"HTTP Error: {e}")

    results, _ = telegram_searcher.parse_search_results(html, "tgsearchers5")
    for r in results:
        print(f"Title: {r.title}")
        print(f"Links: {[l.url for l in r.links]}")
    print(f"Total found: {len(results)}")

if __name__ == "__main__":
    asyncio.run(main())
