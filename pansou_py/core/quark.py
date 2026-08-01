import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

import aiohttp

from pansou_py.core.config import settings


@dataclass
class QuarkTransferResult:
    status: str
    url: Optional[str] = None
    password: str = ""
    error_code: Optional[str] = None
    message: str = ""
    saved_fids: Optional[List[str]] = None


@dataclass
class QuarkShareFile:
    fid: str
    fid_token: str
    name: str = ""


class QuarkService:
    DRIVE_H_BASE = "https://drive-h.quark.cn/1/clouddrive"
    DRIVE_PC_BASE = "https://drive-pc.quark.cn/1/clouddrive"

    def __init__(self):
        self._last_request_at = 0.0

    @property
    def cookie(self) -> Optional[str]:
        return settings.QUARK_COOKIE

    @property
    def base_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://pan.quark.cn",
            "Referer": "https://pan.quark.cn/",
            "Cookie": self.cookie or "",
        }

    def parse_pwd_id(self, share_url: str) -> Optional[str]:
        match = re.search(r"/s/([a-zA-Z0-9]+)", share_url)
        return match.group(1) if match else None

    async def transfer_and_share(
        self,
        share_url: str,
        password: str = "",
        *,
        title: Optional[str] = None,
        progress: Optional[Callable[[str, int], Awaitable[None]]] = None,
    ) -> QuarkTransferResult:
        """Save a Quark share to the owner drive and create an owner share link."""
        pwd_id = self.parse_pwd_id(share_url)
        if not pwd_id:
            return QuarkTransferResult(
                status="failed",
                error_code="INVALID_SHARE_URL",
                message="Invalid Quark share URL",
            )

        if settings.QUARK_MOCK_TRANSFER:
            await self._progress(progress, "正在检查资源可用性...", 50)
            await asyncio.sleep(0.1)
            return QuarkTransferResult(
                status="succeeded",
                url=f"https://pan.quark.cn/s/mock_{pwd_id}",
                password=settings.QUARK_SHARE_PASSWORD or "",
                message="资源检查完成",
                saved_fids=[f"mock_{pwd_id}"],
            )

        if not self.cookie:
            return QuarkTransferResult(
                status="failed",
                error_code="MISSING_COOKIE",
                message="QUARK_COOKIE is not configured",
            )

        try:
            await self._progress(progress, "正在检查资源链接...", 10)
            stoken = await self._get_share_token(pwd_id, password or "")
            await self._progress(progress, "正在读取资源信息...", 25)
            files = await self._list_share_files(pwd_id, stoken)
            if not files:
                return QuarkTransferResult(
                    status="failed",
                    error_code="EMPTY_SHARE",
                    message="No files found in Quark share",
                )

            await self._progress(progress, f"正在准备资源（{len(files)} 个项目）...", 40)
            saved_fids = await self._save_share_files(pwd_id, stoken, files, progress=progress)
            if not saved_fids:
                return QuarkTransferResult(
                    status="failed",
                    error_code="SAVE_TASK_FAILED",
                    message="Quark save task did not return saved file ids",
                )

            share_title = (title or "").strip() or files[0].name or "PanSou 资源"
            await self._progress(progress, "正在生成可访问链接...", 80)
            share = await self._create_owner_share(saved_fids, share_title, progress=progress)
            owner_url = share.get("url") or share.get("share_url")
            if not owner_url:
                pwd_id_value = share.get("pwd_id") or share.get("share_id")
                if pwd_id_value:
                    owner_url = f"https://pan.quark.cn/s/{pwd_id_value}"

            if not owner_url:
                return QuarkTransferResult(
                    status="failed",
                    error_code="SHARE_CREATE_FAILED",
                    message="Quark share-create response did not contain a share URL",
                )

            return QuarkTransferResult(
                status="succeeded",
                url=owner_url,
                password=share.get("passcode") or settings.QUARK_SHARE_PASSWORD or "",
                message="资源检查完成",
                saved_fids=saved_fids,
            )
        except QuarkApiError as exc:
            return QuarkTransferResult(
                status="failed",
                error_code=exc.code,
                message=exc.message,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return QuarkTransferResult(
                status="failed",
                error_code="NETWORK_ERROR",
                message=str(exc),
            )
        except Exception as exc:
            return QuarkTransferResult(
                status="failed",
                error_code="UNEXPECTED_ERROR",
                message=str(exc),
            )

    async def save_to_drive(self, share_url: str, password: str = "") -> bool:
        result = await self.transfer_and_share(share_url, password)
        return result.status == "succeeded"

    async def generate_share_link(self, file_id: str) -> Optional[str]:
        result = await self._create_owner_share([file_id], "PanSou 资源")
        return result.get("url") or result.get("share_url")

    async def auto_transfer_flow(self, share_url: str, password: str = "") -> Optional[str]:
        result = await self.transfer_and_share(share_url, password)
        if result.status == "succeeded":
            return result.url
        return None

    async def get_capacity(self) -> Dict[str, int]:
        if settings.QUARK_MOCK_TRANSFER:
            return {
                "total": 100 * 1024**3,
                "used": 10 * 1024**3,
                "free": 90 * 1024**3,
            }

        if not self.cookie:
            raise QuarkApiError("MISSING_COOKIE", "QUARK_COOKIE is not configured")

        data = await self._request_json(
            "GET",
            f"{self.DRIVE_PC_BASE}/member",
            params={
                **self._common_params(),
                "fetch_subscribe": "true",
                "fetch_identity": "true",
            },
            error_code="CAPACITY_CHECK_FAILED",
        )
        total = self._first_int(
            data,
            [
                "data.total_capacity",
                "data.total",
                "data.capacity",
                "data.cap_total",
            ],
        )
        used = self._first_int(
            data,
            [
                "data.use_capacity",
                "data.used_capacity",
                "data.used",
                "data.cap_used",
            ],
        )
        free = self._first_int(
            data,
            [
                "data.free_capacity",
                "data.available_capacity",
                "data.available",
                "data.cap_free",
            ],
        )
        if free is None and total is not None and used is not None:
            free = max(total - used, 0)
        if free is None:
            raise QuarkApiError("CAPACITY_PARSE_FAILED", "Quark capacity response did not contain free space")
        return {
            "total": int(total or 0),
            "used": int(used or 0),
            "free": int(free),
        }

    async def delete_saved_files(self, fids: Iterable[str]) -> bool:
        fid_list = [str(fid) for fid in fids if fid]
        if not fid_list:
            return True
        if settings.QUARK_MOCK_TRANSFER:
            return True
        if not self.cookie:
            raise QuarkApiError("MISSING_COOKIE", "QUARK_COOKIE is not configured")

        try:
            data = await self._request_json(
                "POST",
                f"{self.DRIVE_PC_BASE}/file/delete",
                params=self._common_params(),
                json={
                    "action_type": 2,
                    "filelist": fid_list,
                    "exclude_fids": [],
                },
                error_code="FILE_DELETE_FAILED",
            )
        except QuarkApiError as exc:
            if "已经删除" not in exc.message:
                raise
            data = {}
        task_id = self._dig(data, "data.task_id")
        if task_id:
            await self._poll_task(str(task_id), label="正在清理资源")

        recycle = await self._request_json(
            "GET",
            f"{self.DRIVE_PC_BASE}/file/recycle/list",
            params={**self._common_params(), "_page": 1, "_size": 100},
            error_code="RECYCLE_LIST_FAILED",
        )
        fid_set = set(fid_list)
        record_ids = [
            str(row["record_id"])
            for row in self._dig(recycle, "data.list") or []
            if str(row.get("fid")) in fid_set and row.get("record_id")
        ]
        if record_ids:
            removed = await self._request_json(
                "POST",
                f"{self.DRIVE_PC_BASE}/file/recycle/remove",
                params=self._common_params(),
                json={"select_mode": 2, "record_list": record_ids},
                error_code="RECYCLE_REMOVE_FAILED",
            )
            remove_task_id = self._dig(removed, "data.task_id")
            if remove_task_id:
                await self._poll_task(str(remove_task_id), label="正在释放空间")
        return True

    async def _get_share_token(self, pwd_id: str, password: str) -> str:
        data = await self._request_json(
            "POST",
            f"{self.DRIVE_H_BASE}/share/sharepage/token",
            params=self._common_params(),
            json={
                "pwd_id": pwd_id,
                "passcode": password,
                "support_visit_limit_private_share": True,
            },
            error_code="SHARE_TOKEN_FAILED",
        )
        token = self._dig(data, "data.stoken") or self._dig(data, "data.share_token")
        if not token:
            raise QuarkApiError("SHARE_TOKEN_FAILED", self._message(data, "Quark did not return stoken"))
        return str(token)

    async def _list_share_files(self, pwd_id: str, stoken: str) -> List[QuarkShareFile]:
        data = await self._request_json(
            "GET",
            f"{self.DRIVE_H_BASE}/share/sharepage/detail",
            params={
                **self._common_params(),
                "pwd_id": pwd_id,
                "stoken": stoken,
                "pdir_fid": "0",
                "_page": 1,
                "_size": 50,
                "_fetch_banner": 0,
                "_fetch_share": 0,
                "_fetch_total": 1,
                "_sort": "file_type:asc,updated_at:desc",
            },
            error_code="SHARE_DETAIL_FAILED",
        )
        rows = self._dig(data, "data.list") or self._dig(data, "data.file_list") or []
        files = []
        for row in rows:
            fid = row.get("fid") or row.get("file_id")
            fid_token = row.get("share_fid_token") or row.get("fid_token") or row.get("share_file_token")
            if fid and fid_token:
                files.append(QuarkShareFile(fid=str(fid), fid_token=str(fid_token), name=row.get("file_name") or row.get("name") or ""))
        return files

    async def _save_share_files(
        self,
        pwd_id: str,
        stoken: str,
        files: List[QuarkShareFile],
        *,
        progress: Optional[Callable[[str, int], Awaitable[None]]] = None,
    ) -> List[str]:
        data = await self._request_json(
            "POST",
            f"{self.DRIVE_PC_BASE}/share/sharepage/save",
            params=self._common_params(),
            json={
                "fid_list": [file.fid for file in files],
                "fid_token_list": [file.fid_token for file in files],
                "to_pdir_fid": settings.QUARK_SAVE_FOLDER_ID or "0",
                "pwd_id": pwd_id,
                "stoken": stoken,
                "pdir_fid": "0",
                "scene": "link",
            },
            error_code="SAVE_SHARE_FAILED",
        )
        task_id = self._dig(data, "data.task_id") or self._dig(data, "data.task.task_id")
        if not task_id:
            direct_fids = self._extract_saved_fids(data)
            if direct_fids:
                return direct_fids
            raise QuarkApiError("SAVE_SHARE_FAILED", self._message(data, "Quark save response did not contain task_id"))

        task_data = await self._poll_task(str(task_id), progress=progress, label="正在等待资源准备完成")
        return self._extract_saved_fids(task_data)

    async def _poll_task(
        self,
        task_id: str,
        *,
        progress: Optional[Callable[[str, int], Awaitable[None]]] = None,
        label: str = "正在等待任务完成",
        start_progress: int = 55,
        end_progress: int = 75,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + max(settings.QUARK_TRANSFER_TIMEOUT, 5)
        last_data: Dict[str, Any] = {}
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            percent = min(start_progress + (attempt - 1) * 5, end_progress)
            await self._progress(progress, f"{label}...", percent)
            data = await self._request_json(
                "GET",
                f"{self.DRIVE_PC_BASE}/task",
                params={**self._common_params(), "task_id": task_id, "retry_index": 0},
                error_code="TASK_POLL_FAILED",
            )
            last_data = data
            status = str(self._dig(data, "data.status") or self._dig(data, "data.task.status") or "")
            if status in {"2", "success", "finished", "done"} or self._extract_saved_fids(data):
                return data
            if status in {"-1", "3", "4", "failed", "error"}:
                raise QuarkApiError("TASK_FAILED", self._message(data, "Quark save task failed"))
            await asyncio.sleep(1)
        raise QuarkApiError("TASK_TIMEOUT", self._message(last_data, "Quark save task timed out"))

    async def _create_owner_share(
        self,
        fid_list: Iterable[str],
        title: str,
        *,
        progress: Optional[Callable[[str, int], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        password = settings.QUARK_SHARE_PASSWORD or ""
        expired_type = 1 if settings.QUARK_SHARE_EXPIRE_DAYS <= 0 else 2
        payload: Dict[str, Any] = {
            "fid_list": list(fid_list),
            "title": title[:80],
            "url_type": 1,
            "expired_type": expired_type,
        }
        if settings.QUARK_SHARE_EXPIRE_DAYS > 0:
            payload["expired_at"] = int(time.time() + settings.QUARK_SHARE_EXPIRE_DAYS * 86400)
        if password:
            payload["passcode"] = password

        data = await self._request_json(
            "POST",
            f"{self.DRIVE_PC_BASE}/share",
            params=self._common_params(),
            json=payload,
            error_code="SHARE_CREATE_FAILED",
        )
        share = self._dig(data, "data") or data
        if share.get("url") or share.get("share_url") or share.get("pwd_id"):
            return share

        task_id = share.get("task_id")
        if task_id:
            task_data = await self._poll_task(
                str(task_id),
                progress=progress,
                label="正在生成访问链接",
                start_progress=85,
                end_progress=95,
            )
            share_id = self._dig(task_data, "data.share_id")
            if share_id:
                await self._progress(progress, "正在确认访问链接...", 96)
                return await self._find_owner_share(str(share_id))
            return self._dig(task_data, "data") or task_data

        return share

    async def _progress(self, callback: Optional[Callable[[str, int], Awaitable[None]]], message: str, progress: int) -> None:
        if callback:
            await callback(message, progress)

    async def _find_owner_share(self, share_id: str) -> Dict[str, Any]:
        data = await self._request_json(
            "GET",
            f"{self.DRIVE_PC_BASE}/share/mypage/detail",
            params={
                **self._common_params(),
                "_page": 1,
                "_size": 20,
                "_order_field": "created_at",
                "_order_type": "desc",
                "_fetch_total": 1,
                "_fetch_notify_follow": 1,
            },
            error_code="SHARE_LOOKUP_FAILED",
        )
        for item in self._dig(data, "data.list") or []:
            if str(item.get("share_id")) == share_id:
                return item
        raise QuarkApiError("SHARE_LOOKUP_FAILED", "Created Quark share was not found in owner share list")

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        error_code: str,
    ) -> Dict[str, Any]:
        await self._rate_limit()
        timeout = aiohttp.ClientTimeout(total=max(settings.QUARK_TRANSFER_TIMEOUT, 5))
        async with aiohttp.ClientSession(headers=self.base_headers, timeout=timeout) as session:
            async with session.request(method, url, params=params, json=json) as response:
                if response.status in {401, 403}:
                    raise QuarkApiError("AUTH_FAILED", "QUARK_COOKIE is invalid or expired")
                if response.status == 429:
                    raise QuarkApiError("RATE_LIMITED", "Quark API rate limited the request")
                data = await response.json(content_type=None)
        self._assert_api_success(data, error_code)
        return data

    async def _rate_limit(self) -> None:
        min_interval = 1 / max(settings.QUARK_TRANSFER_CONCURRENCY, 1)
        now = time.monotonic()
        wait_seconds = self._last_request_at + min_interval - now
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        self._last_request_at = time.monotonic()

    def _assert_api_success(self, data: Dict[str, Any], error_code: str) -> None:
        code = data.get("code")
        status = data.get("status")
        if code in (None, 0, "0") and status in (None, 200, "200", 0, "0"):
            return
        raise QuarkApiError(error_code, self._message(data, "Quark API request failed"))

    def _extract_saved_fids(self, data: Dict[str, Any]) -> List[str]:
        candidates = [
            self._dig(data, "data.save_as.save_as_top_fids"),
            self._dig(data, "data.save_as_top_fids"),
            self._dig(data, "data.fid_list"),
            self._dig(data, "data.file_ids"),
            self._dig(data, "data.saved_fids"),
            self._dig(data, "data.task.save_as.save_as_top_fids"),
        ]
        for candidate in candidates:
            if isinstance(candidate, list) and candidate:
                return [str(item) for item in candidate]
        return []

    def _first_int(self, data: Dict[str, Any], paths: List[str]) -> Optional[int]:
        for path in paths:
            value = self._dig(data, path)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _common_params(self) -> Dict[str, Any]:
        return {"pr": "ucpro", "fr": "pc"}

    def _dig(self, data: Dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _message(self, data: Dict[str, Any], default: str) -> str:
        return str(data.get("message") or data.get("msg") or data.get("error") or default)


class QuarkApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


quark_service = QuarkService()
