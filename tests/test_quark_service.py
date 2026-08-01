import pytest

from pansou_py.core.config import settings
from pansou_py.core.quark import QuarkApiError, QuarkService


@pytest.fixture(autouse=True)
def reset_quark_settings():
    original = {
        "QUARK_COOKIE": settings.QUARK_COOKIE,
        "QUARK_MOCK_TRANSFER": settings.QUARK_MOCK_TRANSFER,
        "QUARK_SAVE_FOLDER_ID": settings.QUARK_SAVE_FOLDER_ID,
        "QUARK_SHARE_PASSWORD": settings.QUARK_SHARE_PASSWORD,
        "QUARK_SHARE_EXPIRE_DAYS": settings.QUARK_SHARE_EXPIRE_DAYS,
        "QUARK_TRANSFER_TIMEOUT": settings.QUARK_TRANSFER_TIMEOUT,
        "QUARK_STORAGE_MIN_FREE_GB": settings.QUARK_STORAGE_MIN_FREE_GB,
    }
    yield
    for key, value in original.items():
        setattr(settings, key, value)


@pytest.mark.asyncio
async def test_real_transfer_flow_saves_and_creates_owner_share(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = "test-cookie"
    settings.QUARK_SAVE_FOLDER_ID = "owner-folder"
    settings.QUARK_SHARE_PASSWORD = "pw12"
    settings.QUARK_SHARE_EXPIRE_DAYS = 7

    service = QuarkService()
    calls = []

    async def fake_request(method, url, *, params=None, json=None, error_code):
        calls.append((method, url, params, json, error_code))
        if url.endswith("/share/sharepage/token"):
            assert json["pwd_id"] == "a500126895e7"
            return {"status": 200, "code": 0, "data": {"stoken": "share-token"}}
        if url.endswith("/share/sharepage/detail"):
            return {
                "status": 200,
                "code": 0,
                "data": {
                    "list": [
                        {
                            "fid": "source-fid",
                            "share_fid_token": "source-token",
                            "file_name": "测试资源",
                        }
                    ]
                },
            }
        if url.endswith("/share/sharepage/save"):
            assert json["to_pdir_fid"] == "owner-folder"
            assert json["fid_list"] == ["source-fid"]
            assert json["fid_token_list"] == ["source-token"]
            return {"status": 200, "code": 0, "data": {"task_id": "task-1"}}
        if url.endswith("/task"):
            return {
                "status": 200,
                "code": 0,
                "data": {"status": 2, "save_as": {"save_as_top_fids": ["owner-fid"]}},
            }
        if url.endswith("/share"):
            assert json["fid_list"] == ["owner-fid"]
            assert json["passcode"] == "pw12"
            return {"status": 200, "code": 0, "data": {"task_id": "share-task-1"}}
        if url.endswith("/share/mypage/detail"):
            return {
                "status": 200,
                "code": 0,
                "data": {
                    "list": [
                        {
                            "share_id": "owner-share-id",
                            "share_url": "https://pan.quark.cn/s/owner123",
                            "pwd_id": "owner123",
                            "passcode": "pw12",
                        }
                    ]
                },
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(service, "_request_json", fake_request)

    async def fake_poll_task(task_id, **kwargs):
        if task_id == "task-1":
            return {"data": {"status": 2, "save_as": {"save_as_top_fids": ["owner-fid"]}}}
        if task_id == "share-task-1":
            return {"data": {"status": 2, "share_id": "owner-share-id"}}
        raise AssertionError(f"unexpected task_id: {task_id}")

    monkeypatch.setattr(service, "_poll_task", fake_poll_task)

    progress_messages = []

    async def progress(message, percent):
        progress_messages.append((message, percent))

    result = await service.transfer_and_share(
        "https://pan.quark.cn/s/a500126895e7",
        title="庆余年 第二季",
        progress=progress,
    )

    assert result.status == "succeeded"
    assert result.url == "https://pan.quark.cn/s/owner123"
    assert result.password == "pw12"
    assert any("正在准备资源" in message for message, _ in progress_messages)
    assert max(percent for _, percent in progress_messages) >= 80
    share_call = next(call for call in calls if call[1].endswith("/share"))
    assert share_call[3]["title"] == "庆余年 第二季"
    assert [call[4] for call in calls] == [
        "SHARE_TOKEN_FAILED",
        "SHARE_DETAIL_FAILED",
        "SAVE_SHARE_FAILED",
        "SHARE_CREATE_FAILED",
        "SHARE_LOOKUP_FAILED",
    ]


@pytest.mark.asyncio
async def test_real_transfer_requires_cookie():
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = None

    result = await QuarkService().transfer_and_share("https://pan.quark.cn/s/a500126895e7")

    assert result.status == "failed"
    assert result.error_code == "MISSING_COOKIE"


@pytest.mark.asyncio
async def test_real_transfer_returns_api_error(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = "test-cookie"

    service = QuarkService()

    async def fail_token(*args, **kwargs):
        raise QuarkApiError("AUTH_FAILED", "QUARK_COOKIE is invalid or expired")

    monkeypatch.setattr(service, "_request_json", fail_token)

    result = await service.transfer_and_share("https://pan.quark.cn/s/a500126895e7")

    assert result.status == "failed"
    assert result.error_code == "AUTH_FAILED"
    assert "QUARK_COOKIE" in result.message


@pytest.mark.asyncio
async def test_capacity_parses_free_space(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = "test-cookie"
    service = QuarkService()

    async def fake_request(method, url, *, params=None, json=None, error_code=None):
        assert method == "GET"
        assert url == "https://drive-pc.quark.cn/1/clouddrive/member"
        assert params["fetch_subscribe"] == "true"
        assert params["fetch_identity"] == "true"
        return {
            "status": 200,
            "code": 0,
            "data": {
                "total_capacity": 1000,
                "use_capacity": 250,
            },
        }

    monkeypatch.setattr(service, "_request_json", fake_request)

    capacity = await service.get_capacity()

    assert capacity == {"total": 1000, "used": 250, "free": 750}


@pytest.mark.asyncio
async def test_delete_saved_files_uses_file_delete_api(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = "test-cookie"
    service = QuarkService()
    calls = []

    async def fake_request(method, url, *, params=None, json=None, error_code=None):
        calls.append((method, url, json, error_code))
        if url.endswith("/file/recycle/list"):
            return {
                "status": 200,
                "code": 0,
                "data": {"list": [
                    {"fid": "fid-1", "record_id": "record-1"},
                    {"fid": "fid-2", "record_id": "record-2"},
                ]},
            }
        return {"status": 200, "code": 0, "data": {}}

    monkeypatch.setattr(service, "_request_json", fake_request)

    result = await service.delete_saved_files(["fid-1", "fid-2"])

    assert result is True
    assert calls == [
        (
            "POST",
            f"{service.DRIVE_PC_BASE}/file/delete",
            {
                "action_type": 2,
                "filelist": ["fid-1", "fid-2"],
                "exclude_fids": [],
            },
            "FILE_DELETE_FAILED",
        ),
        (
            "GET",
            f"{service.DRIVE_PC_BASE}/file/recycle/list",
            None,
            "RECYCLE_LIST_FAILED",
        ),
        (
            "POST",
            f"{service.DRIVE_PC_BASE}/file/recycle/remove",
            {"select_mode": 2, "record_list": ["record-1", "record-2"]},
            "RECYCLE_REMOVE_FAILED",
        ),
    ]


@pytest.mark.asyncio
async def test_delete_saved_files_treats_already_deleted_as_success(monkeypatch):
    settings.QUARK_MOCK_TRANSFER = False
    settings.QUARK_COOKIE = "test-cookie"
    service = QuarkService()
    calls = []

    async def fake_request(method, url, *, params=None, json=None, error_code=None):
        calls.append((method, url))
        if url.endswith("/file/delete"):
            raise QuarkApiError("FILE_DELETE_FAILED", "文件已经删除,请稍后重试")
        if url.endswith("/file/recycle/list"):
            return {"status": 200, "code": 0, "data": {"list": []}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(service, "_request_json", fake_request)

    assert await service.delete_saved_files(["already-gone"]) is True
    assert calls[-1][1].endswith("/file/recycle/list")
