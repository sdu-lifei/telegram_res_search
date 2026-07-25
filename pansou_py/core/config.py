import os
from typing import List, Optional, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    CHANNELS: str = Field(default="tgsearchers5,Quark_Movies,Aliyun_4K_Movies,vip115hot,dianying4K,Quark_qhy,shareAliyun,aliyungaoqingshipin")
    PORT: int = Field(default=8888)
    PROXY: Optional[str] = Field(default=None)

    # Cache
    CACHE_ENABLED: bool = Field(default=True)
    CACHE_PATH: str = "/tmp/pansou_cache"
    CACHE_MAX_SIZE: int = Field(default=100)  # MB
    CACHE_TTL: int = Field(default=60)  # minutes

    # Plugin
    PLUGIN_TIMEOUT: int = Field(default=30)
    ENABLED_PLUGINS: Optional[str] = Field(default=None)

    # Auth
    AUTH_ENABLED: bool = Field(default=False)
    AUTH_USERS: Optional[str] = Field(default=None)
    AUTH_TOKEN_EXPIRY: int = Field(default=24)  # hours
    AUTH_JWT_SECRET: str = Field(default_factory=lambda: "pansou-default-secret-" + os.urandom(16).hex())

    # WeChat Official Account
    WECHAT_TOKEN: Optional[str] = Field(default=None)   # Token set in WeChat backend
    WECHAT_APPID: Optional[str] = Field(default=None)
    WECHAT_APPSECRET: Optional[str] = Field(default=None)

    # Quark settings
    QUARK_COOKIE: Optional[str] = Field(default=None)
    QUARK_AUTO_TRANSFER: bool = Field(default=False)
    QUARK_CLICK_TRANSFER: bool = Field(default=False)
    QUARK_MOCK_TRANSFER: bool = Field(default=True)
    QUARK_SAVE_FOLDER_ID: Optional[str] = Field(default=None)
    QUARK_SHARE_EXPIRE_DAYS: int = Field(default=7)
    QUARK_SHARE_PASSWORD: Optional[str] = Field(default=None)
    QUARK_TRANSFER_TIMEOUT: int = Field(default=30)
    QUARK_TRANSFER_CONCURRENCY: int = Field(default=2)
    QUARK_STORAGE_MIN_FREE_GB: float = Field(default=100.0)
    QUARK_STORAGE_STRICT_CAPACITY_CHECK: bool = Field(default=False)
    QUARK_STORAGE_CLEANUP_ENABLED: bool = Field(default=True)
    QUARK_STORAGE_CLEANUP_KEEP_DAYS: int = Field(default=7)
    QUARK_STORAGE_CLEANUP_MAX_ITEMS: int = Field(default=20)
    PUBLIC_BASE_URL: Optional[str] = Field(default=None)
    
    # Task Queue / Scheduler
    SCHEDULE_INTERVAL: int = Field(default=30)  # minutes
    SEARCH_MAX_RETRIES: int = Field(default=6)

    # Discovery
    DISCOVERY_ENABLED: bool = Field(default=False)
    DISCOVERY_INTERVAL_MINUTES: int = Field(default=1440)
    DISCOVERY_SEED_KEYWORDS: str = Field(default="电影,电视剧,综艺,动漫,纪录片")
    DISCOVERY_MAX_KEYWORDS_PER_RUN: int = Field(default=20)
    DISCOVERY_MAX_RESULTS_PER_KEYWORD: int = Field(default=10)

    # Validation
    VALIDATE_LINKS: bool = Field(default=True)
    VALIDATE_TIMEOUT: int = Field(default=3)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def default_channels(self) -> List[str]:
        return [c.strip() for c in self.CHANNELS.split(",") if c.strip()]

    @property
    def enabled_plugins(self) -> Optional[List[str]]:
        if self.ENABLED_PLUGINS is None:
            return None
        if self.ENABLED_PLUGINS == "":
            return []
        return [p.strip() for p in self.ENABLED_PLUGINS.split(",") if p.strip()]

    @property
    def auth_users_map(self) -> Dict[str, str]:
        users = {}
        if self.AUTH_USERS:
            for pair in self.AUTH_USERS.split(","):
                parts = pair.split(":", 1)
                if len(parts) == 2:
                    users[parts[0].strip()] = parts[1].strip()
        return users

    @property
    def discovery_seed_keywords(self) -> List[str]:
        return [kw.strip() for kw in self.DISCOVERY_SEED_KEYWORDS.split(",") if kw.strip()]

settings = Settings()
