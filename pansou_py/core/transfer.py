import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from pansou_py.core.config import settings
from pansou_py.core.quark import quark_service
from pansou_py.models.database import Resource, TransferJob, async_session


class TransferService:
    async def open_resource(self, resource_id: int, enqueue: bool = True, count_click: bool = True) -> dict:
        async with async_session() as session:
            async with session.begin():
                resource = await session.get(Resource, resource_id)
                if not resource:
                    return {
                        "status": "failed",
                        "resource_id": resource_id,
                        "message": self._public_error_message("RESOURCE_NOT_FOUND", None),
                        "error_code": "RESOURCE_NOT_FOUND",
                        "progress": 100,
                    }

                if count_click:
                    resource.click_count = (resource.click_count or 0) + 1
                    resource.last_clicked_at = datetime.utcnow()

                if resource.owner_share_url:
                    return {
                        "status": "ready",
                        "resource_id": resource.id,
                        "url": resource.owner_share_url,
                        "password": resource.owner_share_password or "",
                        "message": "资源可用，正在打开",
                        "progress": 100,
                    }

                if resource.transfer_status == "failed":
                    resource.transfer_status = "pending"
                    resource.transfer_error = None

                job = await self._get_or_create_pending_job(session, resource)
                if enqueue:
                    return {
                        "status": "pending",
                        "resource_id": resource.id,
                        "job_id": job.id,
                        "message": "资源检查已排队",
                        "progress": self._status_progress(job.status, job.progress),
                    }

        return await self.process_job(job.id)

    async def process_job(self, job_id: int) -> dict:
        async with async_session() as session:
            async with session.begin():
                job = await session.get(TransferJob, job_id)
                if not job:
                    return {"status": "failed", "resource_id": 0, "message": "Transfer job not found"}
                resource = await session.get(Resource, job.resource_id)
                if not resource:
                    job.status = "failed"
                    job.error_code = "RESOURCE_NOT_FOUND"
                    job.error_message = self._public_error_message("RESOURCE_NOT_FOUND", None)
                    job.updated_at = datetime.utcnow()
                    return {
                        "status": "failed",
                        "resource_id": job.resource_id,
                        "message": job.error_message,
                        "error_code": "RESOURCE_NOT_FOUND",
                        "progress": 100,
                    }

                if resource.owner_share_url:
                    job.status = "succeeded"
                    job.completed_at = datetime.utcnow()
                    job.updated_at = datetime.utcnow()
                    return {
                        "status": "ready",
                        "resource_id": resource.id,
                        "url": resource.owner_share_url,
                        "password": resource.owner_share_password or "",
                        "message": "资源可用，正在打开",
                    }

                job.status = "running"
                job.attempts = (job.attempts or 0) + 1
                job.error_message = "正在开始资源检查..."
                job.progress = 5
                job.updated_at = datetime.utcnow()
                resource.transfer_status = "running"

        storage_ready = await self._ensure_storage_available(job_id)
        if not storage_ready["ok"]:
            return storage_ready["result"]

        async def progress(message: str, percent: int) -> None:
            await self._update_job_progress(job_id, message, percent)

        result = await quark_service.transfer_and_share(
            resource.url,
            resource.password or "",
            title=resource.title,
            progress=progress,
        )

        async with async_session() as session:
            async with session.begin():
                job = await session.get(TransferJob, job_id)
                resource = await session.get(Resource, resource.id)
                now = datetime.utcnow()

                if not resource:
                    job.status = "failed"
                    job.error_code = "RESOURCE_NOT_FOUND"
                    job.error_message = "Resource was removed before transfer completed"
                    job.progress = 100
                    job.updated_at = now
                    return {
                        "status": "failed",
                        "resource_id": 0,
                        "message": job.error_message,
                    }

                if result.status == "succeeded" and result.url:
                    resource.owner_share_url = result.url
                    resource.owner_share_password = result.password or ""
                    resource.owner_fids = result.saved_fids or []
                    resource.transfer_status = "succeeded"
                    resource.transfer_error = None
                    resource.transferred_at = now
                    job.status = "succeeded"
                    job.error_code = None
                    job.error_message = "资源检查完成"
                    job.progress = 100
                    job.completed_at = now
                    job.updated_at = now
                    return {
                        "status": "ready",
                        "resource_id": resource.id,
                        "url": resource.owner_share_url,
                        "password": resource.owner_share_password or "",
                        "message": "资源检查完成",
                    }

                resource.transfer_status = "failed"
                resource.transfer_error = result.message or result.error_code or "Transfer failed"
                job.status = "failed"
                job.error_code = result.error_code or "TRANSFER_FAILED"
                job.error_message = result.message or "Transfer failed"
                job.progress = 100
                job.updated_at = now
                return {
                    "status": "failed",
                    "resource_id": resource.id,
                    "message": self._public_error_message(job.error_code, job.error_message),
                }

    async def status(self, resource_id: int) -> dict:
        async with async_session() as session:
            resource = await session.get(Resource, resource_id)
            if not resource:
                return {
                    "status": "failed",
                    "resource_id": resource_id,
                    "message": self._public_error_message("RESOURCE_NOT_FOUND", None),
                    "error_code": "RESOURCE_NOT_FOUND",
                    "progress": 100,
                }

            if resource.owner_share_url:
                return {
                    "status": "ready",
                    "resource_id": resource.id,
                    "url": resource.owner_share_url,
                    "password": resource.owner_share_password or "",
                    "message": "资源可用",
                    "progress": 100,
                }

            query = (
                select(TransferJob)
                .where(
                    TransferJob.resource_id == resource.id,
                    TransferJob.status.in_(["pending", "running", "failed"]),
                )
                .order_by(TransferJob.updated_at.desc(), TransferJob.id.desc())
            )
            job = (await session.execute(query)).scalars().first()
            message = resource.transfer_error or "等待资源检查开始..."
            if job and job.error_message:
                message = job.error_message

            status = resource.transfer_status or "none"
            if job and job.status in {"pending", "running", "failed"}:
                status = job.status
            if status == "succeeded":
                status = "ready"

            return {
                "status": status,
                "resource_id": resource.id,
                "message": self._public_error_message(job.error_code if job else None, message) if status == "failed" else message,
                "job_id": job.id if job else None,
                "transfer_status": resource.transfer_status or "none",
                "progress": self._status_progress(status, job.progress if job else None),
            }

    async def prefetch_resources(self, resource_ids: list[int], limit: int = 3) -> list[int]:
        """Queue background transfers for the first few search results."""
        queued_job_ids: list[int] = []
        for resource_id in resource_ids[:limit]:
            result = await self.open_resource(resource_id, enqueue=True, count_click=False)
            if result.get("status") == "pending" and result.get("job_id"):
                queued_job_ids.append(result["job_id"])
        return queued_job_ids

    async def prefetch_and_run_resources(self, resource_ids: list[int], limit: int = 3) -> None:
        job_ids = await self.prefetch_resources(resource_ids, limit=limit)
        if job_ids:
            await asyncio.gather(*(self.run_job_safely(job_id) for job_id in job_ids))

    async def run_job_safely(self, job_id: int) -> None:
        try:
            await self.process_job(job_id)
        except SQLAlchemyError as exc:
            print(f"❌ [Transfer] Database error for job {job_id}: {exc}")
        except Exception as exc:
            print(f"❌ [Transfer] Unexpected error for job {job_id}: {exc}")
            await self._mark_job_failed(job_id, "UNEXPECTED_ERROR", str(exc))

    async def stats(self) -> dict:
        async with async_session() as session:
            resources = await session.scalar(select(func.count(Resource.id)))
            transferred = await session.scalar(
                select(func.count(Resource.id)).where(Resource.owner_share_url.is_not(None))
            )
            pending_jobs = await session.scalar(
                select(func.count(TransferJob.id)).where(TransferJob.status.in_(["pending", "running"]))
            )
            failed_jobs = await session.scalar(
                select(func.count(TransferJob.id)).where(TransferJob.status == "failed")
            )
            clicks = await session.scalar(select(func.coalesce(func.sum(Resource.click_count), 0)))
        return {
            "resources": resources or 0,
            "transferred": transferred or 0,
            "pending_jobs": pending_jobs or 0,
            "failed_jobs": failed_jobs or 0,
            "clicks": clicks or 0,
        }

    async def cleanup_old_owner_resources(self, limit: Optional[int] = None) -> int:
        if not settings.QUARK_STORAGE_CLEANUP_ENABLED:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=max(settings.QUARK_STORAGE_CLEANUP_KEEP_DAYS, 0))
        max_items = max(limit or settings.QUARK_STORAGE_CLEANUP_MAX_ITEMS, 0)
        if max_items <= 0:
            return 0

        async with async_session() as session:
            query = (
                select(Resource)
                .where(
                    Resource.owner_share_url.is_not(None),
                    Resource.owner_fids.is_not(None),
                    or_(Resource.last_clicked_at.is_(None), Resource.last_clicked_at < cutoff),
                    or_(Resource.transferred_at.is_(None), Resource.transferred_at < cutoff),
                )
                .order_by(Resource.last_clicked_at.asc().nullsfirst(), Resource.transferred_at.asc().nullsfirst())
                .limit(max_items)
            )
            resources = (await session.execute(query)).scalars().all()

        return await self._delete_owner_resources(resources)

    async def cleanup_least_used_owner_resources(self, limit: int = 5) -> int:
        if not settings.QUARK_STORAGE_CLEANUP_ENABLED or limit <= 0:
            return 0

        async with async_session() as session:
            resources = (
                await session.execute(
                    select(Resource)
                    .where(
                        Resource.owner_share_url.is_not(None),
                        Resource.owner_fids.is_not(None),
                    )
                    .order_by(
                        func.coalesce(Resource.click_count, 0).asc(),
                        Resource.last_clicked_at.asc().nullsfirst(),
                        Resource.transferred_at.asc().nullsfirst(),
                    )
                    .limit(limit)
                )
            ).scalars().all()

        return await self._delete_owner_resources(resources)

    async def _delete_owner_resources(self, resources: list[Resource]) -> int:
        cleaned = 0
        for resource in resources:
            fids = resource.owner_fids or []
            if not fids:
                continue
            try:
                await quark_service.delete_saved_files(fids)
            except Exception as exc:
                print(f"⚠️ [Storage] Cleanup skipped resource {resource.id}: {exc}")
                continue

            async with async_session() as session:
                async with session.begin():
                    row = await session.get(Resource, resource.id)
                    if not row:
                        continue
                    row.owner_share_url = None
                    row.owner_share_password = None
                    row.owner_fids = None
                    row.transfer_status = "none"
                    row.transfer_error = None
                    row.transferred_at = None
            cleaned += 1
        return cleaned

    async def _get_or_create_pending_job(self, session, resource: Resource) -> TransferJob:
        query = select(TransferJob).where(
            TransferJob.resource_id == resource.id,
            TransferJob.status.in_(["pending", "running"]),
        )
        job = (await session.execute(query)).scalars().first()
        if job:
            return job

        resource.transfer_status = "pending"
        job = TransferJob(resource_id=resource.id, status="pending")
        session.add(job)
        await session.flush()
        return job

    async def _update_job_progress(self, job_id: int, message: str, progress: int) -> None:
        async with async_session() as session:
            async with session.begin():
                job = await session.get(TransferJob, job_id)
                if not job:
                    return
                job.status = "running"
                job.error_message = message
                job.progress = max(0, min(progress, 99))
                job.updated_at = datetime.utcnow()
                resource = await session.get(Resource, job.resource_id)
                if resource:
                    resource.transfer_status = "running"

    async def _mark_job_failed(self, job_id: int, error_code: str, message: str) -> None:
        async with async_session() as session:
            async with session.begin():
                job = await session.get(TransferJob, job_id)
                if not job:
                    return

                now = datetime.utcnow()
                job.status = "failed"
                job.error_code = error_code
                job.error_message = message
                job.progress = 100
                job.updated_at = now

                resource = await session.get(Resource, job.resource_id)
                if resource:
                    resource.transfer_status = "failed"
                    resource.transfer_error = self._public_error_message(error_code, message)

    async def _ensure_storage_available(self, job_id: int) -> dict:
        if settings.QUARK_MOCK_TRANSFER or settings.QUARK_STORAGE_MIN_FREE_GB <= 0:
            return {"ok": True}

        min_free_bytes = int(settings.QUARK_STORAGE_MIN_FREE_GB * 1024**3)
        try:
            capacity = await quark_service.get_capacity()
        except Exception as exc:
            print(f"⚠️ [Storage] Capacity check unavailable, continuing resource check: {exc}")
            if not settings.QUARK_STORAGE_STRICT_CAPACITY_CHECK:
                return {"ok": True}
            result = await self._fail_job(
                job_id,
                "CAPACITY_CHECK_FAILED",
                f"暂时无法确认可用空间，已停止本次资源检查。{exc}",
            )
            return {"ok": False, "result": result}

        if capacity.get("free", 0) >= min_free_bytes:
            return {"ok": True}

        await self.cleanup_least_used_owner_resources(limit=5)

        try:
            capacity = await quark_service.get_capacity()
        except Exception as exc:
            print(f"⚠️ [Storage] Capacity recheck unavailable after cleanup: {exc}")
            if not settings.QUARK_STORAGE_STRICT_CAPACITY_CHECK:
                return {"ok": True}
            result = await self._fail_job(
                job_id,
                "CAPACITY_CHECK_FAILED",
                f"清理后仍无法确认可用空间，已停止本次资源检查。{exc}",
            )
            return {"ok": False, "result": result}

        if capacity.get("free", 0) >= min_free_bytes:
            return {"ok": True}

        result = await self._fail_job(
            job_id,
            "INSUFFICIENT_STORAGE",
            "可用空间不足，已停止本次资源检查。",
        )
        return {"ok": False, "result": result}

    async def _fail_job(self, job_id: int, error_code: str, message: str) -> dict:
        async with async_session() as session:
            async with session.begin():
                job = await session.get(TransferJob, job_id)
                if not job:
                    return {"status": "failed", "resource_id": 0, "message": message}
                job.status = "failed"
                job.error_code = error_code
                job.error_message = self._public_error_message(error_code, message)
                job.progress = 100
                job.updated_at = datetime.utcnow()
                resource = await session.get(Resource, job.resource_id)
                resource_id = job.resource_id
                if resource:
                    resource.transfer_status = "failed"
                    resource.transfer_error = job.error_message
                    resource_id = resource.id
        return {
            "status": "failed",
            "resource_id": resource_id,
            "message": self._public_error_message(error_code, message),
            "progress": 100,
        }

    def _public_error_message(self, error_code: Optional[str], message: Optional[str]) -> str:
        if error_code == "INSUFFICIENT_STORAGE":
            return "服务可用空间不足，暂时无法检查这个资源。"
        if error_code == "CAPACITY_CHECK_FAILED":
            return "暂时无法确认服务可用空间，请稍后再试。"
        if error_code == "AUTH_FAILED":
            return "服务授权已失效，请稍后再试。"
        if error_code == "MISSING_COOKIE":
            return "服务暂未完成资源检查配置。"
        if error_code == "RESOURCE_NOT_FOUND":
            return "资源记录已失效，请返回搜索页重新搜索。"
        return message or "资源检查失败，请稍后再试。"

    def _status_progress(self, status: str, progress: Optional[int]) -> int:
        if status == "ready":
            return 100
        if status == "failed":
            return 100
        if progress is not None:
            return max(0, min(progress, 99))
        if status == "pending":
            return 3
        if status == "running":
            return 10
        return 0


transfer_service = TransferService()
