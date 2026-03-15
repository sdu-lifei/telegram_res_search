import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pansou_py.core.search import search_service
from pansou_py.core.config import settings
import pytest

@pytest.mark.asyncio
async def test_search():
    print("Testing search_service.search with 1 page...")
    keyword = "庆余年"
    try:
        # Simulate the 'fast path' search
        result = await search_service.search(keyword=keyword, max_pages=1)
        print(f"Success! Found {result.get('total', 0)} items.")
        if result.get("merged_by_type"):
            for k, v in result["merged_by_type"].items():
                print(f" - {k}: {len(v)} links")
    except Exception as e:
        print(f"Error during search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure proxy is set if needed for local testing
    # settings.PROXY = "http://127.0.0.1:7890" 
    asyncio.run(test_search())
