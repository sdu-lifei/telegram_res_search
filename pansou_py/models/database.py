import datetime as dt_module
from typing import List, Optional
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, ForeignKey, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.future import select
import os

Base = declarative_base()

class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(255), index=True)
    title = Column(Text)
    url = Column(String(512), unique=True, index=True)
    password = Column(String(50))
    disk_type = Column(String(50))
    source = Column(String(100))
    datetime = Column(DateTime, default=dt_module.datetime.utcnow)
    created_at = Column(DateTime, default=dt_module.datetime.utcnow)
    images = Column(JSON)
    description = Column(Text)
    last_validated = Column(DateTime, default=dt_module.datetime.utcnow)
    owner_share_url = Column(String(512))
    owner_share_password = Column(String(50))
    owner_fids = Column(JSON)
    transfer_status = Column(String(50), default="none")  # none, pending, running, succeeded, failed
    transfer_error = Column(Text)
    transferred_at = Column(DateTime)
    last_clicked_at = Column(DateTime)
    click_count = Column(Integer, default=0)
    score = Column(Integer, default=0)

class TransferJob(Base):
    __tablename__ = "transfer_jobs"

    id = Column(Integer, primary_key=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), index=True, nullable=False)
    status = Column(String(50), default="pending", index=True)
    error_code = Column(String(100))
    error_message = Column(Text)
    progress = Column(Integer, default=0)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt_module.datetime.utcnow)
    updated_at = Column(DateTime, default=dt_module.datetime.utcnow)
    completed_at = Column(DateTime)

class HotKeyword(Base):
    __tablename__ = "hot_keywords"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(255), index=True)
    source = Column(String(100), default="manual")
    score = Column(Integer, default=0)
    first_seen = Column(DateTime, default=dt_module.datetime.utcnow)
    last_seen = Column(DateTime, default=dt_module.datetime.utcnow)

class SearchRequest(Base):
    __tablename__ = "search_requests"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(255), unique=True, index=True)
    count = Column(Integer, default=1)
    last_search = Column(DateTime, default=dt_module.datetime.utcnow)
    status = Column(String(50), default="pending")  # pending, found, failed

class HarvestCandidate(Base):
    __tablename__ = "harvest_candidates"

    id = Column(Integer, primary_key=True)
    url = Column(String(512), unique=True, index=True, nullable=False)
    keyword = Column(String(255), index=True)
    title = Column(Text)
    description = Column(Text)
    password = Column(String(50), default="")
    disk_type = Column(String(50), default="quark")
    source = Column(String(100), index=True)
    source_datetime = Column(DateTime)
    status = Column(String(50), default="pending", index=True)
    attempts = Column(Integer, default=0)
    discovered_at = Column(DateTime, default=dt_module.datetime.utcnow)
    last_checked_at = Column(DateTime)
    next_retry_at = Column(DateTime, index=True)
    validation_error = Column(Text)

class HarvestState(Base):
    __tablename__ = "harvest_state"

    key = Column(String(255), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=dt_module.datetime.utcnow)

class HarvestRun(Base):
    __tablename__ = "harvest_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=dt_module.datetime.utcnow, index=True)
    finished_at = Column(DateTime)
    discovered = Column(Integer, default=0)
    confirmed_valid = Column(Integer, default=0)
    inserted = Column(Integer, default=0)
    invalid = Column(Integer, default=0)
    deferred = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    resource_total = Column(Integer, default=0)

db_path = os.getenv("DATABASE_PATH", "./pansou.db")
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_resource_columns(conn)
        await _ensure_transfer_job_columns(conn)

async def _ensure_resource_columns(conn):
    """Additive SQLite migrations for deployments that already have resources."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    result = await conn.execute(text("PRAGMA table_info(resources)"))
    existing = {row[1] for row in result.fetchall()}
    columns = {
        "owner_share_url": "VARCHAR(512)",
        "owner_share_password": "VARCHAR(50)",
        "owner_fids": "JSON",
        "transfer_status": "VARCHAR(50) DEFAULT 'none'",
        "transfer_error": "TEXT",
        "transferred_at": "DATETIME",
        "last_clicked_at": "DATETIME",
        "click_count": "INTEGER DEFAULT 0",
        "score": "INTEGER DEFAULT 0",
        "created_at": "DATETIME",
    }
    for name, ddl in columns.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE resources ADD COLUMN {name} {ddl}"))
    if "created_at" not in existing:
        await conn.execute(text("""
            UPDATE resources
            SET created_at = (
                SELECT discovered_at FROM harvest_candidates
                WHERE harvest_candidates.url = resources.url
            )
            WHERE created_at IS NULL AND EXISTS (
                SELECT 1 FROM harvest_candidates
                WHERE harvest_candidates.url = resources.url AND discovered_at IS NOT NULL
            )
        """))

async def _ensure_transfer_job_columns(conn):
    """Additive SQLite migrations for deployments that already have transfer_jobs."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    result = await conn.execute(text("PRAGMA table_info(transfer_jobs)"))
    existing = {row[1] for row in result.fetchall()}
    columns = {
        "progress": "INTEGER DEFAULT 0",
    }
    for name, ddl in columns.items():
        if name not in existing:
            await conn.execute(text(f"ALTER TABLE transfer_jobs ADD COLUMN {name} {ddl}"))

async def get_session() -> AsyncSession:
    async with async_session() as session:
        return session
