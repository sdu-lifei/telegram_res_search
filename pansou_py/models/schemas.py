from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class Link(BaseModel):
    type: str
    url: str
    password: Optional[str] = ""
    datetime: Optional[str] = None
    work_title: Optional[str] = None

class SearchResult(BaseModel):
    message_id: str
    unique_id: str
    channel: str
    datetime: str
    title: str
    description: Optional[str] = None
    links: List[Link]
    images: Optional[List[str]] = None

class MergedLink(BaseModel):
    url: str
    password: str = ""
    note: str = ""
    datetime: str
    source: str
    images: Optional[List[str]] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    expires_at: int
    username: str

class SearchRequest(BaseModel):
    kw: str
    channels: Optional[List[str]] = None
    refresh: Optional[bool] = False
    res: Optional[str] = "merge"   # all, results, merge
    src: Optional[str] = "all"     # all, tg, plugin
    plugins: Optional[List[str]] = None
    cloud_types: Optional[List[str]] = None

class SearchResponse(BaseModel):
    total: int
    results: Optional[List[SearchResult]] = None
    merged_by_type: Optional[Dict[str, List[MergedLink]]] = None
