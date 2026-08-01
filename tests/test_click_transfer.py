import os
from datetime import datetime, timedelta

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
from pansou_py.core.quark import QuarkTransferResult
from pansou_py.core.search import search_service
from pansou_py.core.transfer import transfer_service
from pansou_py.models.database import HarvestState, HotKeyword, Resource, SearchRequest, TransferJob, async_session, init_db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    settings.QUARK_CLICK_TRANSFER = True
    settings.QUARK_MOCK_TRANSFER = True
    settings.QUARK_STORAGE_MIN_FREE_GB = 100
    settings.QUARK_STORAGE_CLEANUP_ENABLED = True
    settings.QUARK_STORAGE_CLEANUP_KEEP_DAYS = 7
    settings.QUARK_STORAGE_CLEANUP_MAX_ITEMS = 20
    settings.PUBLIC_BASE_URL = "http://testserver"
    cache_service.clear()
    await init_db()
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(TransferJob))
            await session.execute(delete(Resource))
            await session.execute(delete(SearchRequest))
            await session.execute(delete(HarvestState))
            await session.execute(delete(HotKeyword))
    cache_service.clear()
    yield
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(TransferJob))
            await session.execute(delete(Resource))
            await session.execute(delete(SearchRequest))
            await session.execute(delete(HarvestState))
            await session.execute(delete(HotKeyword))


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


@pytest.mark.asyncio
async def test_home_counts_ingestion_time_not_source_date(monkeypatch):
    from pansou_py.api import catalog

    async def no_recommendations():
        return [], None

    monkeypatch.setattr(catalog, "_baidu_recommendations", no_recommendations)
    await add_resource(datetime=datetime(2020, 1, 1))

    assert (await catalog.home())["stats"]["daily_new"] == 1


def test_baidu_daily_pick_changes_each_day():
    from pansou_py.api.catalog import _daily_pick

    items = [{"title": str(i)} for i in range(20)]
    today = _daily_pick(items, datetime(2026, 7, 22))
    tomorrow = _daily_pick(items, datetime(2026, 7, 23))

    assert len(today) == len(tomorrow) == 10
    assert {item["title"] for item in today}.isdisjoint(item["title"] for item in tomorrow)


@pytest.mark.asyncio
async def test_search_retry_does_not_increment_counter(monkeypatch):
    from pansou_py.api import search as search_api
    from pansou_py.models.schemas import SearchRequest as SearchPayload

    async def empty_search(**kwargs):
        return {"total": 0}

    monkeypatch.setattr(search_api.search_service, "search", empty_search)
    async with async_session() as session:
        async with session.begin():
            await session.execute(delete(HarvestState).where(HarvestState.key == "total_searches"))

    await search_api.search_post(SearchPayload(kw="测试", track=True))
    await search_api.search_post(SearchPayload(kw="测试", track=False))

    async with async_session() as session:
        total = await session.get(HarvestState, "total_searches")
    assert total and total.value == "1"


@pytest.mark.asyncio
async def test_search_returns_internal_open_url_when_click_transfer_enabled():
    resource = await add_resource()

    response = await search_service.search("庆余年", res_type="all", cloud_types=["quark"])

    link = response["results"][0]["links"][0]
    merged = response["merged_by_type"]["quark"][0]
    assert link["resource_id"] == resource.id
    assert link["open_url"] == f"http://testserver/r/{resource.id}"
    assert link["url"] == "https://pan.quark.cn/s/a500126895e7"
    assert merged["url"] == "https://pan.quark.cn/s/a500126895e7"


@pytest.mark.asyncio
async def test_search_reports_searching_state_for_empty_results(monkeypatch):
    async def empty_db(*args, **kwargs):
        return []

    async def empty_results(*args, **kwargs):
        return []

    monkeypatch.setattr(search_service, "_search_local_db", empty_db)
    monkeypatch.setattr(search_service, "search_plugins", empty_results)
    monkeypatch.setattr(search_service, "_validate_all_results_deep", empty_results)

    response = await search_service.search("一个不存在的关键字12345", res_type="all", cloud_types=["quark"], force_refresh=True)

    assert response["total"] == 0
    assert response["status"] == "searching"
    assert response["progress"] == 35
    assert "后台仍在搜索" in response["message"]


@pytest.mark.asyncio
async def test_open_resource_reuses_existing_owner_share():
    resource = await add_resource(
        owner_share_url="https://pan.quark.cn/s/owner123",
        owner_share_password="pw12",
        transfer_status="succeeded",
    )
    client = TestClient(app)

    response = client.post(f"/api/resources/{resource.id}/open")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "resource_id": resource.id,
        "url": "https://pan.quark.cn/s/owner123",
        "password": "pw12",
        "message": "资源可用，正在打开",
        "error_code": None,
        "job_id": None,
        "progress": 100,
    }


@pytest.mark.asyncio
async def test_open_resource_wait_runs_mock_transfer():
    resource = await add_resource()
    client = TestClient(app)

    response = client.post(f"/api/resources/{resource.id}/open?wait=true")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["resource_id"] == resource.id
    assert body["url"] == "https://pan.quark.cn/s/mock_a500126895e7"


@pytest.mark.asyncio
async def test_open_resource_without_wait_queues_job():
    resource = await add_resource()
    client = TestClient(app)

    response = client.post(f"/api/resources/{resource.id}/open")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["resource_id"] == resource.id
    assert body["job_id"]
    assert body["progress"] == 0


def test_open_resource_missing_resource_returns_stable_error():
    client = TestClient(app)

    response = client.post("/api/resources/999999/open")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["resource_id"] == 999999
    assert body["error_code"] == "RESOURCE_NOT_FOUND"
    assert body["message"] == "资源记录已失效，请返回搜索页重新搜索。"
    assert body["progress"] == 100


def test_resource_status_missing_resource_returns_stable_error():
    client = TestClient(app)

    response = client.get("/api/resources/999999/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["resource_id"] == 999999
    assert body["error_code"] == "RESOURCE_NOT_FOUND"
    assert body["message"] == "资源记录已失效，请返回搜索页重新搜索。"
    assert body["progress"] == 100


@pytest.mark.asyncio
async def test_redirect_resource_pending_returns_wait_page():
    resource = await add_resource()
    client = TestClient(app)

    response = client.get(f"/r/{resource.id}", follow_redirects=False)

    assert response.status_code == 202
    assert "正在准备资源" in response.text
    assert f"/api/resources/{resource.id}/status" in response.text


@pytest.mark.asyncio
async def test_resource_status_reports_progress_message():
    resource = await add_resource(transfer_status="running")
    result = await transfer_service.open_resource(resource.id, enqueue=True)
    job_id = result["job_id"]
    await transfer_service._update_job_progress(job_id, "正在检查资源...", 40)
    client = TestClient(app)

    response = client.get(f"/api/resources/{resource.id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["resource_id"] == resource.id
    assert body["job_id"] == job_id
    assert body["message"] == "正在检查资源..."
    assert body["transfer_status"] == "running"
    assert body["progress"] == 40


@pytest.mark.asyncio
async def test_resource_status_ignores_abandoned_capacity_failure():
    resource = await add_resource(transfer_status="none", transfer_error=None)
    async with async_session() as session:
        async with session.begin():
            session.add(
                TransferJob(
                    resource_id=resource.id,
                    status="abandoned",
                    error_code="CAPACITY_CHECK_FAILED",
                    error_message="暂时无法确认服务可用空间，请稍后再试。",
                    progress=100,
                )
            )
    client = TestClient(app)

    response = client.get(f"/api/resources/{resource.id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "none"
    assert body["message"] == "等待资源检查开始..."


@pytest.mark.asyncio
async def test_prefetch_resources_does_not_increment_clicks():
    resource = await add_resource()

    job_ids = await transfer_service.prefetch_resources([resource.id], limit=3)

    async with async_session() as session:
        updated_resource = await session.get(Resource, resource.id)

    assert job_ids
    assert updated_resource.click_count == 0
    assert updated_resource.last_clicked_at is None


@pytest.mark.asyncio
async def test_background_transfer_exception_marks_job_failed(monkeypatch):
    resource = await add_resource()
    result = await transfer_service.open_resource(resource.id, enqueue=True)
    job_id = result["job_id"]

    async def fail_process_job(_job_id):
        raise RuntimeError("quark timeout")

    monkeypatch.setattr(transfer_service, "process_job", fail_process_job)

    await transfer_service.run_job_safely(job_id)

    async with async_session() as session:
        job = await session.get(TransferJob, job_id)
        updated_resource = await session.get(Resource, resource.id)

    assert job.status == "failed"
    assert job.error_code == "UNEXPECTED_ERROR"
    assert job.error_message == "quark timeout"
    assert updated_resource.transfer_status == "failed"
    assert updated_resource.transfer_error == "quark timeout"


@pytest.mark.asyncio
async def test_process_job_stops_when_storage_is_insufficient(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_STORAGE_MIN_FREE_GB = 5
    settings.QUARK_STORAGE_STRICT_CAPACITY_CHECK = False
    resource = await add_resource()
    result = await transfer_service.open_resource(resource.id, enqueue=True)
    job_id = result["job_id"]

    async def low_capacity():
        return {"total": 100 * 1024**3, "used": 99 * 1024**3, "free": 1 * 1024**3}

    async def no_cleanup(limit=5):
        assert limit == 5
        return 0

    async def should_not_transfer(*args, **kwargs):
        raise AssertionError("transfer should not run when storage is insufficient")

    monkeypatch.setattr("pansou_py.core.transfer.quark_service.get_capacity", low_capacity)
    monkeypatch.setattr(transfer_service, "cleanup_least_used_owner_resources", no_cleanup)
    monkeypatch.setattr("pansou_py.core.transfer.quark_service.transfer_and_share", should_not_transfer)

    body = await transfer_service.process_job(job_id)

    assert body["status"] == "failed"
    assert "空间不足" in body["message"]
    async with async_session() as session:
        job = await session.get(TransferJob, job_id)
        updated_resource = await session.get(Resource, resource.id)

    assert job.error_code == "INSUFFICIENT_STORAGE"
    assert updated_resource.transfer_status == "failed"


@pytest.mark.asyncio
async def test_process_job_continues_when_capacity_check_is_unavailable(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_STORAGE_MIN_FREE_GB = 5
    settings.QUARK_STORAGE_STRICT_CAPACITY_CHECK = False
    resource = await add_resource()
    result = await transfer_service.open_resource(resource.id, enqueue=True)
    job_id = result["job_id"]

    async def capacity_unavailable():
        raise RuntimeError("empty capacity response")

    async def transfer_success(*args, **kwargs):
        return QuarkTransferResult(
            status="succeeded",
            url="https://pan.quark.cn/s/checked",
            password="",
            saved_fids=["fid-new"],
        )

    monkeypatch.setattr("pansou_py.core.transfer.quark_service.get_capacity", capacity_unavailable)
    monkeypatch.setattr("pansou_py.core.transfer.quark_service.transfer_and_share", transfer_success)

    body = await transfer_service.process_job(job_id)

    assert body["status"] == "ready"
    assert body["url"] == "https://pan.quark.cn/s/checked"
    async with async_session() as session:
        job = await session.get(TransferJob, job_id)
        updated_resource = await session.get(Resource, resource.id)

    assert job.status == "succeeded"
    assert updated_resource.transfer_status == "succeeded"


@pytest.mark.asyncio
async def test_cleanup_old_owner_resources_deletes_saved_files(monkeypatch):
    old_time = datetime.utcnow() - timedelta(days=10)
    resource = await add_resource(
        owner_share_url="https://pan.quark.cn/s/owner-old",
        owner_share_password="pw12",
        owner_fids=["fid-old-1", "fid-old-2"],
        transfer_status="succeeded",
        transferred_at=old_time,
        last_clicked_at=old_time,
    )
    deleted = []

    async def fake_delete(fids):
        deleted.extend(fids)
        return True

    monkeypatch.setattr("pansou_py.core.transfer.quark_service.delete_saved_files", fake_delete)

    cleaned = await transfer_service.cleanup_old_owner_resources(limit=5)

    assert cleaned == 1
    assert deleted == ["fid-old-1", "fid-old-2"]
    async with async_session() as session:
        updated_resource = await session.get(Resource, resource.id)

    assert updated_resource.owner_share_url is None
    assert updated_resource.owner_fids is None
    assert updated_resource.transfer_status == "none"


@pytest.mark.asyncio
async def test_cleanup_least_used_owner_resources_deletes_five(monkeypatch):
    now = datetime.utcnow()
    resources = []
    for index, clicks in enumerate([5, 1, 4, 0, 3, 2]):
        resources.append(await add_resource(
            url=f"https://pan.quark.cn/s/least-used-{index}",
            owner_share_url=f"https://pan.quark.cn/s/owner-{index}",
            owner_fids=[f"fid-{index}"],
            transfer_status="succeeded",
            transferred_at=now,
            last_clicked_at=now,
            click_count=clicks,
        ))
    deleted = []

    async def fake_delete(fids):
        deleted.extend(fids)
        return True

    monkeypatch.setattr("pansou_py.core.transfer.quark_service.delete_saved_files", fake_delete)

    cleaned = await transfer_service.cleanup_least_used_owner_resources(limit=5)

    assert cleaned == 5
    assert set(deleted) == {"fid-1", "fid-2", "fid-3", "fid-4", "fid-5"}
    async with async_session() as session:
        most_used = await session.get(Resource, resources[0].id)
    assert most_used.owner_share_url is not None
