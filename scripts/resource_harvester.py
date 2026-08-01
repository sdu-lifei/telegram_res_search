#!/usr/bin/env python3
"""Continuous, rate-limited discovery with strict pre-insert validation."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import email.message
import json
import os
import re
import smtplib
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from pansou_py.core.config import settings
from pansou_py.core.tg_searcher import TelegramSearcher
from pansou_py.models.database import (
    HarvestCandidate, HarvestRun, HarvestState, HotKeyword, Resource, SearchRequest,
    async_session, init_db,
)

QUARK_RE = re.compile(r"https?://pan\.quark\.cn/s/([A-Za-z0-9]+)")
URL_RE = re.compile(r"https?://\S+")
SEARCH_SUFFIX_RE = re.compile(
    r"(?i)\s+(?:19\d{2}|20\d{2}|s\d{1,2}(?:e\d+)?|e\d{1,3}|第?\d+集|更\d+集|"
    r"更新|全\d+集|2160p|1080p|720p|4k|8k|hdr|web[- .]?dl|hiveweb|bluray|remux|"
    r"60fps|flac|杜比|蓝光|中字|字幕|国语|粤语|内封|无删减|全集|完结|"
    r"动作|动画|奇幻|剧情|喜剧|爱情|悬疑|惊悚|犯罪|纪录片)\b.*$"
)
GENERIC_KEYWORDS = {"名称", "描述", "电影", "电视剧", "资源", "合集", "短剧更新目录"}
DEFAULT_KEYWORDS = [
    "电影", "电视剧", "短剧", "韩剧", "美剧", "日剧", "动漫", "综艺", "纪录片",
    "4K", "1080P", "Netflix", "豆瓣", "热门", "完结", "合集", "电子书", "课程",
    "庆余年", "凡人修仙传", "神探狄仁杰", "甄嬛传", "琅琊榜", "权力的游戏",
]
KEYWORD_TIMEZONE = ZoneInfo("Asia/Shanghai")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def daily_keyword_date(now: dt.datetime, last_run_date: str) -> str | None:
    local = now.astimezone(KEYWORD_TIMEZONE)
    today = local.date().isoformat()
    return today if local.hour == 1 and last_run_date != today else None


class ValidationResult(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass
class CandidateRow:
    url: str
    keyword: str
    title: str
    description: str
    password: str
    source: str
    source_datetime: dt.datetime


def normalize_quark_url(value: str) -> str | None:
    match = QUARK_RE.search(value or "")
    return f"https://pan.quark.cn/s/{match.group(1)}" if match else None


def parse_datetime(value: str | None) -> dt.datetime:
    if not value:
        return utcnow()
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return utcnow()


def normalize_search_keyword(value: str | None) -> str | None:
    keyword = URL_RE.sub(" ", value or "")
    keyword = re.split(r"[\r\n|｜]", keyword, maxsplit=1)[0]
    if "更新目录" in keyword or keyword.lstrip().startswith("描述："):
        return None
    keyword = re.sub(r"^\s*(?:名称|片名|资源名)[：:]\s*", "", keyword)
    keyword = re.sub(r"^\s*\d{1,8}[.、_-]\s*", "", keyword)
    keyword = keyword.translate(str.maketrans({character: " " for character in "【】[]（）()#"}))
    keyword = SEARCH_SUFFIX_RE.sub("", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip(" -_:：,，。")
    if len(keyword) < 2 or keyword in GENERIC_KEYWORDS:
        return None
    return keyword[:32]


def parse_pansou_rows(payload: dict, keyword: str, limit: int = 500) -> list[CandidateRow]:
    rows: list[CandidateRow] = []
    for result in (payload.get("data") or {}).get("results") or []:
        for link in result.get("links") or []:
            normalized = normalize_quark_url(str(link.get("url") or ""))
            if not normalized:
                continue
            title = str(result.get("title") or keyword)
            rows.append(CandidateRow(
                normalized, title[:255], title[:1000], str(result.get("content") or title)[:4000],
                str(link.get("password") or ""), "public:so.252035.xyz",
                parse_datetime(result.get("datetime")),
            ))
            if len(rows) >= limit:
                return rows
    return rows


def parse_authenticated_telegram_rows(
    text: str, chat_title: str, source: str, source_datetime: dt.datetime
) -> list[CandidateRow]:
    title = next((line.strip() for line in text.splitlines() if line.strip()), chat_title)
    keyword = normalize_search_keyword(title) or normalize_search_keyword(chat_title) or chat_title[:32]
    return [CandidateRow(
        f"https://pan.quark.cn/s/{match.group(1)}", keyword, title[:1000], text[:4000], "",
        source, source_datetime.replace(tzinfo=None),
    ) for match in QUARK_RE.finditer(text)]


def public_channel_chats(search_result) -> list:
    return [chat for chat in search_result.chats if getattr(chat, "username", None)]


async def validate_quark_link(client: httpx.AsyncClient, url: str) -> tuple[ValidationResult, str]:
    """Only explicit Quark success is valid; transport/rate-limit failures are unknown."""
    normalized = normalize_quark_url(url)
    if not normalized:
        return ValidationResult.INVALID, "malformed_url"
    try:
        response = await client.post(
            "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token",
            params={"pr": "ucpro", "fr": "pc"},
            json={
                "pwd_id": normalized.rsplit("/", 1)[-1], "passcode": "",
                "support_visit_limit_private_share": True,
            },
        )
    except httpx.HTTPError as error:
        return ValidationResult.UNKNOWN, type(error).__name__
    if response.status_code in (403, 408, 425, 429) or response.status_code >= 500:
        return ValidationResult.UNKNOWN, f"http_{response.status_code}"
    if response.status_code == 404:
        return ValidationResult.INVALID, "http_404"
    if response.status_code != 200:
        return ValidationResult.INVALID, f"http_{response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return ValidationResult.UNKNOWN, "invalid_json"
    if payload.get("status") == 200 and payload.get("code") == 0 and payload.get("data"):
        return ValidationResult.VALID, "confirmed"
    code = str(payload.get("code", "unknown"))
    message = str(payload.get("message") or payload.get("msg") or "rejected")[:160]
    return ValidationResult.INVALID, f"quark_{code}:{message}"


class ResourceHarvester:
    def __init__(self, *, cycle_seconds: int, validation_batch: int, target: int):
        self.cycle_seconds = cycle_seconds
        self.validation_batch = validation_batch
        self.target = target
        self.telegram_pages = max(1, int(os.getenv("HARVEST_TELEGRAM_PAGES", "8")))
        self.source_concurrency = max(1, int(os.getenv("HARVEST_SOURCE_CONCURRENCY", "4")))
        self.keyword_batch = max(1, int(os.getenv("HARVEST_KEYWORD_BATCH", "40")))
        self.pansou_keyword_batch = max(1, int(os.getenv("HARVEST_PANSOU_KEYWORD_BATCH", "8")))
        self.validation_concurrency = max(1, int(os.getenv("HARVEST_VALIDATION_CONCURRENCY", "6")))
        self.auth_telegram_interval = max(300, int(os.getenv("HARVEST_AUTH_TELEGRAM_INTERVAL", "600")))
        self.auth_telegram_dialogs = max(1, int(os.getenv("HARVEST_AUTH_TELEGRAM_DIALOGS", "100")))
        self.auth_telegram_messages = max(20, int(os.getenv("HARVEST_AUTH_TELEGRAM_MESSAGES", "200")))
        self.auth_global_interval = max(1800, int(os.getenv("HARVEST_AUTH_GLOBAL_INTERVAL", "3600")))
        self.auth_global_messages = max(100, int(os.getenv("HARVEST_AUTH_GLOBAL_MESSAGES", "1000")))
        self.auth_global_chats = max(1, int(os.getenv("HARVEST_AUTH_GLOBAL_CHATS", "30")))
        self.auth_global_queries = [value.strip() for value in os.getenv(
            "HARVEST_AUTH_GLOBAL_QUERIES", "pan.quark.cn/s/,夸克网盘,4K,短剧,合集"
        ).split(",") if value.strip()] or ["pan.quark.cn/s/"]
        self.telegram = TelegramSearcher()
        self.headers = {"User-Agent": "PanSouHarvester/1.0 (+https://panss.dpdns.org/)"}

    async def state_get(self, key: str, default: str = "") -> str:
        async with async_session() as session:
            row = await session.get(HarvestState, key)
            return row.value if row else default

    async def state_set(self, key: str, value: str) -> None:
        async with async_session() as session:
            row = await session.get(HarvestState, key)
            if row:
                row.value, row.updated_at = value, utcnow()
            else:
                session.add(HarvestState(key=key, value=value))
            await session.commit()

    async def keywords(self, limit: int = 12, namespace: str = "default") -> list[str]:
        cursor_key = f"resource_keyword_cursor:{namespace}"
        cursor = int(await self.state_get(cursor_key, "0") or 0)
        scan_limit = max(1000, limit * 60)
        async with async_session() as session:
            resource_rows = (await session.execute(
                select(Resource.id, Resource.title, Resource.keyword).where(
                    Resource.id > cursor
                ).order_by(Resource.id).limit(scan_limit)
            )).all()
            search_rows = (await session.execute(
                select(SearchRequest.keyword).order_by(
                    SearchRequest.count.desc(), SearchRequest.last_search.desc()
                ).limit(100)
            )).scalars().all()
            hot_rows = (await session.execute(
                select(HotKeyword.keyword).order_by(
                    HotKeyword.score.desc(), HotKeyword.last_seen.desc()
                ).limit(100)
            )).scalars().all()

        selected: list[str] = []
        for value in (*hot_rows, *search_rows, *DEFAULT_KEYWORDS):
            normalized = normalize_search_keyword(value)
            if normalized and normalized not in selected:
                selected.append(normalized)
                if len(selected) >= limit:
                    return selected

        next_cursor = cursor
        for resource_id, title, keyword in resource_rows:
            next_cursor = resource_id
            normalized = normalize_search_keyword(keyword) or normalize_search_keyword(title)
            if normalized and normalized not in selected:
                selected.append(normalized)
                if len(selected) >= limit:
                    break

        if next_cursor == cursor or len(resource_rows) < scan_limit:
            next_cursor = 0
        await self.state_set(cursor_key, str(next_cursor))
        return selected

    async def discover_telegram(self, client: httpx.AsyncClient) -> list[CandidateRow]:
        semaphore = asyncio.Semaphore(self.source_concurrency)

        async def crawl_channel(channel: str) -> tuple[str, str, list[CandidateRow]]:
            rows: list[CandidateRow] = []
            key = f"tg_cursor:{channel}"
            cursor = await self.state_get(key)
            head_only = cursor == "done"
            if head_only:
                cursor = ""
            pages = 1 if head_only else self.telegram_pages
            for _ in range(pages):
                url = self.telegram.build_search_url(
                    channel, "", f"before={cursor}" if cursor else ""
                )
                try:
                    async with semaphore:
                        response = await client.get(url)
                    response.raise_for_status()
                    results, next_param = self.telegram.parse_search_results(response.text, channel, "")
                except (httpx.HTTPError, ValueError) as error:
                    print(f"telegram source {channel}: {error}")
                    break
                next_cursor = next_param.removeprefix("before=") if next_param else ""
                for result in results:
                    for link in result.links:
                        normalized = normalize_quark_url(link.url)
                        if normalized:
                            rows.append(CandidateRow(
                                normalized, result.title[:255], result.title[:1000],
                                (result.description or "")[:4000], link.password or "",
                                f"public:t.me/{channel}", parse_datetime(result.datetime),
                            ))
                if head_only:
                    cursor = "done"
                    break
                if not next_cursor or next_cursor == cursor:
                    cursor = "done"
                    break
                cursor = next_cursor
            return key, cursor, rows

        crawled = await asyncio.gather(*(crawl_channel(channel) for channel in settings.default_channels))
        rows: list[CandidateRow] = []
        for key, cursor, channel_rows in crawled:
            if cursor:
                await self.state_set(key, cursor)
            rows.extend(channel_rows)
        return rows

    async def discover_authenticated_telegram(self, _client: httpx.AsyncClient) -> list[CandidateRow]:
        api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        session_path = os.getenv("TELEGRAM_SESSION", "data/telegram-harvester").strip()
        if not api_id or not api_hash:
            return []

        from telethon import TelegramClient, functions

        telegram = TelegramClient(session_path, int(api_id), api_hash)
        await telegram.connect()
        rows: list[CandidateRow] = []
        try:
            if not await telegram.is_user_authorized():
                print("authenticated telegram source: session is not authorized")
                return []

            async def scan_entity(entity, chat_id: int, title: str, prefix: str) -> list[CandidateRow]:
                state_prefix = f"{prefix}:{chat_id}"
                before = await self.state_get(f"{state_prefix}:before", "0")
                head = int(await self.state_get(f"{state_prefix}:head", "0") or 0)
                options = {"min_id": head} if before == "done" else {"offset_id": int(before or 0)}
                try:
                    messages = [message async for message in telegram.iter_messages(
                        entity, limit=self.auth_telegram_messages, **options
                    )]
                except Exception as error:
                    print(f"authenticated telegram chat {chat_id}: {type(error).__name__}")
                    return []
                if not messages:
                    if before != "done":
                        await self.state_set(f"{state_prefix}:before", "done")
                    return []
                message_ids = [message.id for message in messages]
                await self.state_set(f"{state_prefix}:head", str(max(head, max(message_ids))))
                if before != "done":
                    next_before = "done" if len(messages) < self.auth_telegram_messages else str(min(message_ids))
                    await self.state_set(f"{state_prefix}:before", next_before)
                source = f"{prefix}:{chat_id}"
                return [row for message in messages if message.raw_text for row in
                        parse_authenticated_telegram_rows(message.raw_text, title, source, message.date)]

            joined_ids: set[int] = set()
            async for dialog in telegram.iter_dialogs(limit=self.auth_telegram_dialogs):
                if not (dialog.is_channel or dialog.is_group):
                    continue
                joined_ids.add(dialog.id)
                rows.extend(await scan_entity(
                    dialog.entity, dialog.id, dialog.name or "Telegram", "telegram"
                ))
            global_last = float(await self.state_get("auth_tg:global_last", "0") or 0)
            if utcnow().timestamp() - global_last >= self.auth_global_interval:
                limit = max(20, self.auth_global_messages // len(self.auth_global_queries))
                global_chats = {}
                for query in self.auth_global_queries:
                    async for message in telegram.iter_messages(None, search=query, limit=limit):
                        if message.chat_id and message.chat:
                            global_chats.setdefault(message.chat_id, message.chat)
                        if message.raw_text:
                            rows.extend(parse_authenticated_telegram_rows(
                                message.raw_text, getattr(message.chat, "title", "Telegram"),
                                f"telegram-global:{message.chat_id}", message.date,
                            ))
                    try:
                        result = await telegram(functions.contacts.SearchRequest(
                            q=query, limit=self.auth_global_chats
                        ))
                    except Exception as error:
                        print(f"authenticated telegram channel search {query}: {type(error).__name__}")
                    else:
                        for chat in public_channel_chats(result):
                            global_chats.setdefault(chat.id, chat)
                for chat_id, entity in list(global_chats.items())[:self.auth_global_chats]:
                    if chat_id not in joined_ids:
                        rows.extend(await scan_entity(
                            entity, chat_id, getattr(entity, "title", "Telegram"),
                            "telegram-global-history",
                        ))
                await self.state_set("auth_tg:global_last", str(utcnow().timestamp()))
        finally:
            await telegram.disconnect()
        return rows

    async def discover_search_apis(self, client: httpx.AsyncClient) -> list[CandidateRow]:
        semaphore = asyncio.Semaphore(self.source_concurrency)

        async def fetch_keyword(keyword: str) -> list[CandidateRow]:
            rows: list[CandidateRow] = []
            try:
                async with semaphore:
                    response = await client.get(
                        "https://uuyue.top/api/search/index",
                        params={"title": keyword, "page_no": 1, "page_size": 50, "search_type": 1},
                )
                response.raise_for_status()
                data = response.json().get("data") or {}
                for item in data.get("items") or []:
                    normalized = normalize_quark_url(str(item.get("url") or ""))
                    if not normalized:
                        continue
                    title = str(item.get("name") or item.get("title") or keyword)
                    rows.append(CandidateRow(
                        normalized, title[:255], title[:1000], title[:4000], str(item.get("code") or ""),
                        "public:uuyue.top", utcnow(),
                    ))
            except (httpx.HTTPError, ValueError) as error:
                print(f"uuyue source {keyword}: {error}")
            return rows

        batches = await asyncio.gather(*(
            fetch_keyword(keyword) for keyword in await self.keywords(self.keyword_batch, "uuyue")
        ))
        rows = [row for batch in batches for row in batch]
        return rows

    async def discover_pansou_api(self, client: httpx.AsyncClient) -> list[CandidateRow]:
        semaphore = asyncio.Semaphore(self.source_concurrency)

        async def fetch_keyword(keyword: str) -> list[CandidateRow]:
            try:
                async with semaphore:
                    response = await client.get(
                        "https://so.252035.xyz/api/search",
                        params={"kw": keyword, "res": "all", "cloud_types": "quark"},
                    )
                response.raise_for_status()
                payload = json.loads(response.content.decode("utf-8", errors="replace"))
                return parse_pansou_rows(payload, keyword)
            except (httpx.HTTPError, ValueError) as error:
                print(f"pansou source {keyword}: {error}")
                return []

        batches = await asyncio.gather(*(
            fetch_keyword(keyword) for keyword in await self.keywords(self.pansou_keyword_batch, "pansou")
        ))
        return [row for batch in batches for row in batch]

    async def queue_candidates(self, rows: list[CandidateRow]) -> int:
        unique = {row.url: row for row in rows}
        if not unique:
            return 0
        inserted = 0
        async with async_session() as session:
            resource_urls = set((await session.execute(
                select(Resource.url).where(Resource.url.in_(list(unique)))
            )).scalars().all())
            candidate_urls = set((await session.execute(
                select(HarvestCandidate.url).where(HarvestCandidate.url.in_(list(unique)))
            )).scalars().all())
            for row in unique.values():
                if row.url in resource_urls or row.url in candidate_urls:
                    continue
                session.add(HarvestCandidate(
                    url=row.url, keyword=row.keyword, title=row.title, description=row.description,
                    password=row.password, source=row.source, source_datetime=row.source_datetime,
                ))
                inserted += 1
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
        return inserted

    async def validate_pending(self, client: httpx.AsyncClient) -> dict[str, int]:
        now = utcnow()
        async with async_session() as session:
            candidates = (await session.execute(
                select(HarvestCandidate).where(
                    HarvestCandidate.status.in_(("pending", "retry")),
                    or_(HarvestCandidate.next_retry_at.is_(None), HarvestCandidate.next_retry_at <= now),
                ).order_by(HarvestCandidate.discovered_at).limit(self.validation_batch)
            )).scalars().all()
        stats = {"confirmed_valid": 0, "inserted": 0, "invalid": 0, "deferred": 0}
        semaphore = asyncio.Semaphore(self.validation_concurrency)

        async def check(candidate: HarvestCandidate):
            async with semaphore:
                result = await validate_quark_link(client, candidate.url)
                await asyncio.sleep(0.1)
                return candidate.id, result

        checked = await asyncio.gather(*(check(candidate) for candidate in candidates))
        async with async_session() as session:
            for candidate_id, (status, detail) in checked:
                candidate = await session.get(HarvestCandidate, candidate_id)
                if not candidate:
                    continue
                candidate.attempts = (candidate.attempts or 0) + 1
                candidate.last_checked_at = now
                candidate.validation_error = detail
                if status == ValidationResult.VALID:
                    candidate.status, candidate.next_retry_at = "valid", None
                    stats["confirmed_valid"] += 1
                    exists = await session.scalar(select(Resource.id).where(Resource.url == candidate.url))
                    if not exists:
                        session.add(Resource(
                            keyword=candidate.keyword, title=candidate.title, description=candidate.description,
                            url=candidate.url, password=candidate.password, disk_type="quark",
                            source=candidate.source, datetime=candidate.source_datetime or now, images=[],
                            last_validated=now, transfer_status="none", score=1,
                        ))
                        stats["inserted"] += 1
                elif status == ValidationResult.INVALID:
                    candidate.status, candidate.next_retry_at = "invalid", None
                    stats["invalid"] += 1
                else:
                    candidate.status = "retry"
                    delay_minutes = min(24 * 60, 5 * (2 ** min(candidate.attempts, 8)))
                    candidate.next_retry_at = now + dt.timedelta(minutes=delay_minutes)
                    stats["deferred"] += 1
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
        return stats

    async def totals(self) -> dict[str, int]:
        async with async_session() as session:
            resources = await session.scalar(select(func.count(Resource.id))) or 0
            pending = await session.scalar(select(func.count(HarvestCandidate.id)).where(
                HarvestCandidate.status.in_(("pending", "retry")))) or 0
            invalid = await session.scalar(select(func.count(HarvestCandidate.id)).where(
                HarvestCandidate.status == "invalid")) or 0
        return {"resource_total": resources, "pending": pending, "invalid_total": invalid}

    async def save_run(self, started: dt.datetime, discovered: int, stats: dict[str, int], errors: int) -> None:
        totals = await self.totals()
        async with async_session() as session:
            session.add(HarvestRun(
                started_at=started, finished_at=utcnow(), discovered=discovered,
                confirmed_valid=stats["confirmed_valid"], inserted=stats["inserted"],
                invalid=stats["invalid"], deferred=stats["deferred"], errors=errors,
                resource_total=totals["resource_total"],
            ))
            await session.commit()

    async def hourly_summary(self) -> str:
        since = utcnow() - dt.timedelta(hours=1)
        async with async_session() as session:
            runs = (await session.execute(select(HarvestRun).where(HarvestRun.started_at >= since))).scalars().all()
        totals = await self.totals()
        sums = {key: sum(getattr(run, key) or 0 for run in runs) for key in (
            "discovered", "confirmed_valid", "inserted", "invalid", "deferred", "errors")}
        return "\n".join([
            "盘搜资源采集每小时报告", f"统计时间：{utcnow():%Y-%m-%d %H:%M} UTC",
            f"当前有效资源总数：{totals['resource_total']:,} / {self.target:,}",
            f"本小时发现候选：{sums['discovered']:,}", f"本小时确认有效：{sums['confirmed_valid']:,}",
            f"本小时新增入库：{sums['inserted']:,}", f"本小时确认失效：{sums['invalid']:,}",
            f"等待验证或重试：{totals['pending']:,}", f"本小时延后重试：{sums['deferred']:,}",
            f"累计隔离失效：{totals['invalid_total']:,}", f"本小时错误：{sums['errors']:,}",
        ])

    async def send_report(self) -> bool:
        username = os.getenv("HARVEST_SMTP_USER", "").strip()
        password = os.getenv("HARVEST_SMTP_APP_PASSWORD", "").strip()
        recipient = os.getenv("HARVEST_REPORT_TO", "").strip()
        if not username or not password or not recipient:
            print("hourly email skipped: Gmail SMTP settings are incomplete")
            return False
        message = email.message.EmailMessage()
        message["Subject"] = f"盘搜采集报告 {utcnow():%Y-%m-%d %H:%M} UTC"
        message["From"], message["To"] = username, recipient
        message.set_content(await self.hourly_summary())

        def send() -> None:
            host = os.getenv("HARVEST_SMTP_HOST", "smtp.gmail.com")
            port = int(os.getenv("HARVEST_SMTP_PORT", "465"))
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)

        await asyncio.to_thread(send)
        return True

    async def cycle(self) -> None:
        started, errors = utcnow(), 0
        keyword_date = daily_keyword_date(
            dt.datetime.now(dt.timezone.utc), await self.state_get("daily_keyword_date")
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(25.0), headers=self.headers, follow_redirects=True
        ) as client:
            async def discover(discoverer):
                try:
                    return await discoverer(client), 0
                except Exception as error:
                    print(f"discovery error: {type(error).__name__}: {error}")
                    return [], 1

            auth_last = float(await self.state_get("auth_tg:last_run", "0") or 0)
            auth_due = bool(os.getenv("TELEGRAM_API_ID")) and started.timestamp() - auth_last >= self.auth_telegram_interval
            discoverers = [self.discover_telegram]
            if auth_due:
                discoverers.append(self.discover_authenticated_telegram)
            if keyword_date:
                discoverers.extend((self.discover_search_apis, self.discover_pansou_api))
            batches = await asyncio.gather(*(discover(discoverer) for discoverer in discoverers))
            if auth_due:
                await self.state_set("auth_tg:last_run", str(started.timestamp()))
            if keyword_date:
                await self.state_set("daily_keyword_date", keyword_date)
            rows = [row for batch, _ in batches for row in batch]
            errors = sum(batch_errors for _, batch_errors in batches)
            discovered = await self.queue_candidates(rows)
            stats = await self.validate_pending(client)
        await self.save_run(started, discovered, stats, errors)
        print(json.dumps({"discovered": discovered, **stats, **await self.totals()}, ensure_ascii=False))

    async def run(self, once: bool = False) -> None:
        await init_db()
        while True:
            try:
                await self.cycle()
            except Exception as error:
                print(f"cycle failed: {type(error).__name__}: {error}")
            if once:
                return
            await asyncio.sleep(self.cycle_seconds)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--send-report", action="store_true")
    parser.add_argument("--cycle-seconds", type=int, default=int(os.getenv("HARVEST_CYCLE_SECONDS", "300")))
    parser.add_argument("--validation-batch", type=int, default=int(os.getenv("HARVEST_VALIDATION_BATCH", "100")))
    parser.add_argument("--target", type=int, default=int(os.getenv("HARVEST_TARGET", "500000")))
    args = parser.parse_args()
    harvester = ResourceHarvester(
        cycle_seconds=max(30, args.cycle_seconds),
        validation_batch=max(1, min(args.validation_batch, 3000)), target=max(1, args.target),
    )
    if args.send_report:
        await init_db()
        if not await harvester.send_report():
            raise SystemExit("Gmail SMTP settings are incomplete")
        print("hourly report sent")
        return
    await harvester.run(once=args.once)


if __name__ == "__main__":
    asyncio.run(main())
