from fastapi import APIRouter
from pansou_py.plugins import plugin_manager
from pansou_py.core.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    plugins = plugin_manager.get_plugins()
    return {
        "status": "ok",
        "auth_enabled": settings.AUTH_ENABLED,
        "plugin_count": len(plugins),
        "plugins": [p.name for p in plugins],
        "channels_count": len(settings.default_channels),
        "channels": settings.default_channels,
        "wechat_enabled": bool(settings.WECHAT_TOKEN),
        "quark_click_transfer": settings.QUARK_CLICK_TRANSFER,
        "quark_mock_transfer": settings.QUARK_MOCK_TRANSFER,
        "discovery_enabled": settings.DISCOVERY_ENABLED,
    }
