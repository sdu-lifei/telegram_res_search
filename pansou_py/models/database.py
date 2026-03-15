import datetime as dt_module
from typing import List, Optional
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
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
    images = Column(JSON)
    description = Column(Text)
    last_validated = Column(DateTime, default=dt_module.datetime.utcnow)

class SearchRequest(Base):
    __tablename__ = "search_requests"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(255), unique=True, index=True)
    count = Column(Integer, default=1)
    last_search = Column(DateTime, default=dt_module.datetime.utcnow)
    status = Column(String(50), default="pending")  # pending, found, failed

db_path = os.getenv("DATABASE_PATH", "./pansou.db")
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        return session
