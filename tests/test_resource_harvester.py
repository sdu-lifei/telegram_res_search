import datetime as dt
from types import SimpleNamespace

import httpx
import pytest

from scripts.resource_harvester import (
    ResourceHarvester, ValidationResult, daily_keyword_date, normalize_quark_url, normalize_search_keyword,
    parse_authenticated_telegram_rows, parse_datetime, parse_pansou_rows, validate_quark_link,
    public_channel_chats,
)
from pansou_py.core.tg_searcher import TelegramSearcher


def test_normalize_quark_url_strips_query_and_rejects_other_hosts():
    assert normalize_quark_url("https://pan.quark.cn/s/abc123?entry=foo") == "https://pan.quark.cn/s/abc123"
    assert normalize_quark_url("https://example.com/s/abc123") is None


def test_parse_pansou_rows_keeps_only_quark_links():
    payload = {"data": {"results": [{
        "title": "功夫女足", "content": "2026 周星驰", "datetime": "2026-07-12T00:00:00Z",
        "links": [
            {"type": "quark", "url": "https://pan.quark.cn/s/abc123"},
            {"type": "baidu", "url": "https://pan.baidu.com/s/nope"},
        ],
    }]}}
    rows = parse_pansou_rows(payload, "功夫女足")
    assert [row.url for row in rows] == ["https://pan.quark.cn/s/abc123"]
    assert rows[0].keyword == "功夫女足"
    assert rows[0].source_datetime.year == 2026
    assert parse_pansou_rows({"data": None}, "功夫女足") == []


def test_parse_authenticated_telegram_rows_keeps_all_quark_links():
    rows = parse_authenticated_telegram_rows(
        "功夫女足\nhttps://pan.quark.cn/s/abc123 和 https://pan.quark.cn/s/def456?x=1",
        "资源群", "telegram:-1001", dt.datetime(2026, 7, 14, tzinfo=dt.timezone.utc),
    )
    assert [row.url for row in rows] == [
        "https://pan.quark.cn/s/abc123", "https://pan.quark.cn/s/def456",
    ]
    assert all(row.source_datetime.tzinfo is None for row in rows)


def test_public_channel_search_keeps_only_channels_with_usernames():
    public = SimpleNamespace(id=1, username="resources")
    result = SimpleNamespace(chats=[public, SimpleNamespace(id=2, username=None)])
    assert public_channel_chats(result) == [public]


def test_normalize_search_keyword_removes_links_and_quality_noise():
    value = "庆余年 第二季【4K HDR 全集】 https://pan.quark.cn/s/abc123"
    assert normalize_search_keyword(value) == "庆余年 第二季"
    assert normalize_search_keyword("择天记 S01E01 - E24 杜比音效 HiveWeb") == "择天记"
    assert normalize_search_keyword("名称：二十世纪电气目录(2026)【更01集】") == "二十世纪电气目录"
    assert normalize_search_keyword("2026年5月18日 短剧更新目录17") is None
    assert normalize_search_keyword("#藏海传") == "藏海传"
    assert parse_datetime("bad-date").tzinfo is None


def test_keyword_search_runs_once_at_1am_china_time():
    now = dt.datetime(2026, 7, 14, 17, 30, tzinfo=dt.timezone.utc)
    assert daily_keyword_date(now, "") == "2026-07-15"
    assert daily_keyword_date(now, "2026-07-15") is None
    assert daily_keyword_date(now + dt.timedelta(hours=1), "") is None


def test_telegram_public_url_uses_working_host_and_history_cursor():
    url = TelegramSearcher().build_search_url("Quark_Movies", "", "before=59619")
    assert url == "https://telegram.me/s/Quark_Movies?before=59619"


@pytest.mark.asyncio
async def test_uuyue_null_items_is_empty_result():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"items": None}})

    harvester = ResourceHarvester(cycle_seconds=30, validation_batch=1, target=1)

    async def keywords(*args, **kwargs):
        return ["测试"]

    harvester.keywords = keywords
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await harvester.discover_search_apis(client) == []


@pytest.mark.asyncio
async def test_strict_validation_requires_explicit_success():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "code": 0, "data": {"stoken": "ok"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await validate_quark_link(client, "https://pan.quark.cn/s/abc123")
    assert result == (ValidationResult.VALID, "confirmed")


@pytest.mark.asyncio
async def test_rate_limit_is_not_treated_as_valid():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status, detail = await validate_quark_link(client, "https://pan.quark.cn/s/abc123")
    assert status == ValidationResult.UNKNOWN
    assert detail == "http_429"


@pytest.mark.asyncio
async def test_explicit_quark_rejection_is_invalid():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 400, "code": 41001, "message": "expired"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status, detail = await validate_quark_link(client, "https://pan.quark.cn/s/abc123")
    assert status == ValidationResult.INVALID
    assert detail.startswith("quark_41001")
