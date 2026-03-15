from typing import List, Dict, Type
from pansou_py.plugins.base import BasePlugin
from pansou_py.core.config import settings

class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register(self, plugin: BasePlugin):
        self._plugins[plugin.name] = plugin

    def get_plugins(self) -> List[BasePlugin]:
        if settings.enabled_plugins is None:
            return list(self._plugins.values())
        return [p for p in self._plugins.values() if p.name in settings.enabled_plugins]

    def get_plugin(self, name: str) -> BasePlugin:
        return self._plugins.get(name)

plugin_manager = PluginManager()
