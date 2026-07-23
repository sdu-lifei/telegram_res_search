import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "daily_promotion.py"
SPEC = importlib.util.spec_from_file_location("daily_promotion", MODULE_PATH)
promotion = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(promotion)


def test_campaigns_only_use_guide_urls():
    urls = [
        "https://panss.dpdns.org/guides/cloud-search-keyword-guide",
        "https://panss.dpdns.org/d/123",
    ]
    result = promotion.campaigns(urls[:1])
    assert len(result) == 7
    assert all("/guides/" in campaign["url"] for campaign in result)


def test_choose_campaign_retries_only_missing_channel():
    available = [{"id": "guide:1", "url": "https://example.com/guides/a", "angle": "a"}]
    state = {
        "delivered": {
            "guide:1": {
                "bluesky": {
                    "sent_at": "2026-07-23T00:00:00+00:00",
                    "public_url": "https://bsky.app/example",
                }
            }
        }
    }
    campaign, channels = promotion.choose_campaign(
        available, state, ["bluesky", "mastodon"]
    )
    assert campaign["id"] == "guide:1"
    assert channels == ["mastodon"]


def test_tracking_url_is_channel_specific():
    url = promotion.tracking_url("https://panss.dpdns.org/guides/a", "bluesky")
    assert "utm_source=bluesky" in url
    assert "utm_medium=social" in url
    assert "utm_campaign=daily_guide" in url


def test_bluesky_message_fits_limit_and_keeps_link():
    link = promotion.tracking_url(
        "https://panss.dpdns.org/guides/cloud-search-keyword-guide", "bluesky"
    )
    text = promotion.message(
        {"title": "网盘资源搜索关键词怎么写", "description": "", "url": link},
        "很长的介绍" * 100,
        link,
        300,
    )
    assert len(text) <= 300
    assert link in text
