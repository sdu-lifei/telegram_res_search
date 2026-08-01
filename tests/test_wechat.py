import asyncio
import hashlib
import os
import time
from datetime import datetime

os.environ.setdefault("DATABASE_PATH", "/tmp/telegram_res_search_test.db")
os.environ.setdefault("QUARK_CLICK_TRANSFER", "true")
os.environ.setdefault("QUARK_MOCK_TRANSFER", "true")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete

from main import app
from pansou_py.core.cache import cache_service
from pansou_py.core.config import settings
from pansou_py.models.database import Resource, TransferJob, async_session, init_db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    original = {
        "WECHAT_TOKEN": settings.WECHAT_TOKEN,
        "QUARK_CLICK_TRANSFER": settings.QUARK_CLICK_TRANSFER,
        "QUARK_MOCK_TRANSFER": settings.QUARK_MOCK_TRANSFER,
        "PUBLIC_BASE_URL": settings.PUBLIC_BASE_URL,
    }
    settings.WECHAT_TOKEN = "wechat-test-token"
    settings.QUARK_CLICK_TRANSFER = True
    settings.QUARK_MOCK_TRANSFER = True
    settings.PUBLIC_BASE_URL = "http://testserver"
    cache_service.clear()
    await init_db()
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(TransferJob))
            await session.execute(delete(Resource))
    yield
    cache_service.clear()
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(TransferJob))
            await session.execute(delete(Resource))
    for key, value in original.items():
        setattr(settings, key, value)


async def add_resource(**kwargs) -> Resource:
    defaults = {
        "keyword": "庆余年",
        "title": "庆余年 第二季",
        "description": "测试资源",
        "url": "https://pan.quark.cn/s/a500126895e7",
        "password": "",
        "disk_type": "quark",
        "source": "tg:test",
        "datetime": datetime.utcnow(),
        "last_validated": datetime.utcnow(),
        "transfer_status": "none",
    }
    defaults.update(kwargs)
    async with async_session() as session:
        async with session.begin():
            resource = Resource(**defaults)
            session.add(resource)
            await session.flush()
            resource_id = resource.id

    async with async_session() as session:
        return await session.get(Resource, resource_id)


def signed_params(token: str) -> dict:
    timestamp = str(int(time.time()))
    nonce = "nonce"
    signature = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()
    return {"signature": signature, "timestamp": timestamp, "nonce": nonce}


def text_message_xml(content: str) -> str:
    return f"""
    <xml>
      <ToUserName><![CDATA[gh_test]]></ToUserName>
      <FromUserName><![CDATA[user_openid]]></FromUserName>
      <CreateTime>{int(time.time())}</CreateTime>
      <MsgType><![CDATA[text]]></MsgType>
      <Content><![CDATA[{content}]]></Content>
    </xml>
    """


@pytest.mark.asyncio
async def test_wechat_replies_existing_owner_share_url():
    await add_resource(owner_share_url="https://pan.quark.cn/s/owner123", transfer_status="succeeded")
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("庆余年").encode(),
    )

    assert response.status_code == 200
    assert "https://pan.quark.cn/s/owner123" in response.text
    assert "http://testserver/r/" not in response.text


@pytest.mark.asyncio
async def test_wechat_replies_open_link_without_preparing_resource():
    await add_resource()
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("庆余年").encode(),
    )

    assert response.status_code == 200
    assert "http://testserver/search?kw=%E5%BA%86%E4%BD%99%E5%B9%B4" in response.text
    assert "http://testserver/r/" not in response.text
    assert "打开搜索页查看全部结果" in response.text
    assert "https://pan.quark.cn/s/mock_a500126895e7" not in response.text


@pytest.mark.asyncio
async def test_wechat_prefers_ready_owner_share_beyond_first_three_candidates():
    for idx in range(4):
        await add_resource(
            title=f"逐玉 未检查 {idx}",
            keyword="逐玉",
            url=f"https://pan.quark.cn/s/notready{idx}",
            transfer_status="none",
        )
    await add_resource(
        title="逐玉 已检查",
        keyword="逐玉",
        url="https://pan.quark.cn/s/ready-source",
        owner_share_url="https://pan.quark.cn/s/ready-owner",
        transfer_status="succeeded",
    )
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("逐玉").encode(),
    )

    assert response.status_code == 200
    assert "https://pan.quark.cn/s/ready-owner" in response.text
    assert "正在生成" not in response.text


@pytest.mark.asyncio
async def test_wechat_returns_only_one_ready_owner_share():
    await add_resource(
        title="逐玉 最新资源",
        keyword="逐玉",
        url="https://pan.quark.cn/s/ready-source-1",
        owner_share_url="https://pan.quark.cn/s/ready-owner-1",
        transfer_status="succeeded",
    )
    await add_resource(
        title="逐玉 旧资源",
        keyword="逐玉",
        url="https://pan.quark.cn/s/ready-source-2",
        owner_share_url="https://pan.quark.cn/s/ready-owner-2",
        transfer_status="succeeded",
    )
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("逐玉").encode(),
    )

    assert response.status_code == 200
    assert response.text.count("https://pan.quark.cn/s/ready-owner") == 1


@pytest.mark.asyncio
async def test_wechat_wait_message_includes_search_page(monkeypatch):
    await add_resource()
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("庆余年").encode(),
    )

    assert response.status_code == 200
    assert "打开搜索页查看全部结果" in response.text
    assert "http://testserver/search?kw=%E5%BA%86%E4%BD%99%E5%B9%B4" in response.text
    assert "http://testserver/r/" not in response.text
    assert "再次发送" not in response.text


@pytest.mark.asyncio
async def test_wechat_timeout_message_includes_search_page(monkeypatch):
    async def slow_search(*args, **kwargs):
        await asyncio.sleep(3.5)

    monkeypatch.setattr("pansou_py.api.wechat.search_service.search", slow_search)
    client = TestClient(app)

    response = client.post(
        "/wechat",
        params=signed_params(settings.WECHAT_TOKEN),
        content=text_message_xml("红楼梦").encode(),
    )

    assert response.status_code == 200
    assert "http://testserver/search?kw=%E7%BA%A2%E6%A5%BC%E6%A2%A6" in response.text
    assert "再次发送" not in response.text
