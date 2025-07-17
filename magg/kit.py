"""Kit management for Magg - bundling related MCP servers."""
import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings import ConfigManager, ServerConfig, MaggConfig, KitInfo

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class KitConfig(BaseSettings):
    """Configuration for a kit - a bundle of related MCP servers."""
    model_config = SettingsConfigDict(
        extra="allow",
        validate_assignment=True,
    )

    name: str = Field(..., description="Unique kit name")
    description: str = Field("", description="What this kit provides")
    author: str | None = Field(None, description="Kit author/maintainer")
    version: str | None = Field(None, description="Kit version")
    keywords: list[str] = Field(default_factory=list, description="Keywords for discovery")
    links: dict[str, str] = Field(default_factory=dict, description="Related links (homepage, docs, etc)")

    servers: dict[str, ServerConfig] = Field(
        default_factory=dict,
        description="Servers included in this kit"
    )

    @field_validator('servers', mode='before')
    def validate_servers(cls, v: dict[str, Any]) -> dict[str, ServerConfig]:
        """Convert raw server data to ServerConfig objects."""
        if not isinstance(v, dict):
            return {}

        servers = {}
        for name, server_data in v.items():
            try:
                if isinstance(server_data, ServerConfig):
                    servers[name] = server_data
                else:
                    if isinstance(server_data, dict):
                        server_data = server_data.copy()
                        server_data.pop('kits', None)  # Remove any kits field, only allowed in config.json

                    server_data['name'] = name
                    servers[name] = ServerConfig(**server_data)
            except Exception as e:
                logger.error("Error loading server %r in kit: %s", name, e)
                continue

        return servers


class KitManager:
    """Manages kit discovery, loading, and integration.
    """
    config_manager: ConfigManager
    kitd_paths: list[Path]
    _kits: dict[str, KitConfig]

    def __init__(self, config_manager: ConfigManager, kitd_paths: list[Path] | None = None):
        """Initialize kit manager with search paths."""
        self.config_manager = config_manager
        if kitd_paths:
            self.kitd_paths = kitd_paths
        else:
            config = MaggConfig()
            self.kitd_paths = config.get_kitd_paths()
        self._kits: dict[str, KitConfig] = {}


    def discover_kits(self) -> dict[str, Path]:
        """Discover all available kit files."""
        kits = {}

        for kitd_path in self.kitd_paths:
            if not kitd_path.exists():
                continue

            for file_path in kitd_path.glob('*.json'):
                if file_path.is_file():
                    kit_name = file_path.stem
                    if kit_name in kits:
                        logger.warning(
                            "Duplicate kit %r found at %s, "
                            "keeping %s",
                            kit_name, file_path, kits[kit_name]
                        )
                    else:
                        kits[kit_name] = file_path

        return kits

    def load_kit(self, kit_path: Path) -> KitConfig | None:
        """Load a kit from a JSON file."""
        try:
            data = json.loads(kit_path.read_text())
            if 'name' not in data:
                data['name'] = kit_path.stem

            return KitConfig.model_validate(data)

        except Exception as e:
            logger.error("Error loading kit from %s: %s", kit_path, e)
            return None

    @property
    def kits(self) -> dict[str, KitConfig]:
        """Get all currently loaded kits."""
        return self._kits.copy()

    def add_kit(self, name: str, kit: KitConfig) -> bool:
        """Add a kit to the loaded set."""
        if name in self._kits:
            logger.warning("Kit %r already loaded", name)
            return False

        self._kits[name] = kit
        return True

    def remove_kit(self, name: str) -> bool:
        """Remove a kit from the loaded set."""
        if name not in self._kits:
            return False

        del self._kits[name]
        return True

    def get_kit_servers(self, kit_name: str) -> dict[str, ServerConfig]:
        """Get all servers from a specific kit."""
        kit = self._kits.get(kit_name)
        if not kit:
            return {}
        return kit.servers.copy()

    def get_all_servers(self) -> dict[str, tuple[ServerConfig, list[str]]]:
        """Get all servers from all kits with their source kit names."""
        servers = {}

        for kit_name, kit in self._kits.items():
            for server_name, server_config in kit.servers.items():
                if server_name in servers:
                    _, kits = servers[server_name]
                    kits.append(kit_name)
                else:
                    servers[server_name] = (server_config, [kit_name])

        return servers

    def load_kits_from_config(self, config: 'MaggConfig') -> None:
        """Load all kits listed in the configuration.

        If a kit name is not found in any kit.d directory, create it in memory.
        """
        available_kits = self.discover_kits()

        for kit_name in config.kits.keys():
            if kit_name in available_kits:
                kit_path = available_kits[kit_name]
                kit_config = self.load_kit(kit_path)
                if kit_config:
                    self.add_kit(kit_name, kit_config)
                    logger.info("Loaded kit %r from %s", kit_name, kit_path)
                else:
                    logger.error("Failed to load kit %r from %s", kit_name, kit_path)
            else:
                logger.info("Kit %r not found in any kit.d directory - creating in memory", kit_name)
                kit_config = KitConfig(name=kit_name)
                self.add_kit(kit_name, kit_config)

    def load_kit_to_config(self, kit_name: str, config: 'MaggConfig') -> tuple[bool, str]:
        """Load a kit and its servers into the configuration.

        Returns:
            Tuple of (success, message)
        """
        if kit_name in config.kits:
            return False, f"Kit '{kit_name}' is already loaded"

        available_kits = self.discover_kits()
        if kit_name not in available_kits:
            return False, f"Kit '{kit_name}' not found in any kit.d directory"

        kit_path = available_kits[kit_name]
        kit_config = self.load_kit(kit_path)
        if not kit_config:
            return False, f"Failed to load kit '{kit_name}' from {kit_path}"

        self.add_kit(kit_name, kit_config)

        servers_added = []
        servers_updated = []

        for server_name, server_config in kit_config.servers.items():
            if server_name in config.servers:
                if kit_name not in config.servers[server_name].kits:
                    config.servers[server_name].kits.append(kit_name)
                    servers_updated.append(server_name)
            else:
                server_config.kits = [kit_name]
                config.servers[server_name] = server_config
                servers_added.append(server_name)

        config.kits[kit_name] = KitInfo(
            name=kit_name,
            description=kit_config.description,
            path=str(kit_path),
            source="file"
        )

        msg_parts = [f"Kit '{kit_name}' loaded successfully"]
        if servers_added:
            msg_parts.append(f"Added servers: {', '.join(servers_added)}")
        if servers_updated:
            msg_parts.append(f"Updated servers: {', '.join(servers_updated)}")
        return True, ". ".join(msg_parts)

    def unload_kit_from_config(self, kit_name: str, config: 'MaggConfig') -> tuple[bool, str]:
        """Unload a kit and optionally its servers from the configuration.

        Returns:
            Tuple of (success, message)
        """
        if kit_name not in config.kits:
            return False, f"Kit '{kit_name}' is not loaded"

        servers_to_remove = []
        servers_to_update = []

        for server_name, server_config in config.servers.items():
            if kit_name in server_config.kits:
                if len(server_config.kits) == 1:
                    servers_to_remove.append(server_name)
                else:
                    servers_to_update.append(server_name)

        for server_name in servers_to_update:
            config.servers[server_name].kits.remove(kit_name)

        for server_name in servers_to_remove:
            del config.servers[server_name]

        del config.kits[kit_name]
        self.remove_kit(kit_name)

        msg_parts = [f"Kit '{kit_name}' unloaded successfully"]
        if servers_to_remove:
            msg_parts.append(f"Removed servers: {', '.join(servers_to_remove)}")
        if servers_to_update:
            msg_parts.append(f"Updated servers: {', '.join(servers_to_update)}")
        return True, ". ".join(msg_parts)

    def list_all_kits(self) -> dict[str, dict[str, Any]]:
        """List all available kits with their status.

        Returns:
            Dict mapping kit names to their info (loaded, path, description, servers)
        """
        available_kits = self.discover_kits()
        loaded_kits = self.kits

        result = {}

        for kit_name, kit_config in loaded_kits.items():
            result[kit_name] = {
                'loaded': True,
                'path': str(available_kits.get(kit_name, 'unknown')),
                'description': kit_config.description,
                'author': kit_config.author,
                'version': kit_config.version,
                'keywords': kit_config.keywords,
                'servers': list(kit_config.servers.keys())
            }

        for kit_name, kit_path in available_kits.items():
            if kit_name not in result:
                kit_config = self.load_kit(kit_path)
                if kit_config:
                    result[kit_name] = {
                        'loaded': False,
                        'path': str(kit_path),
                        'description': kit_config.description,
                        'author': kit_config.author,
                        'version': kit_config.version,
                        'keywords': kit_config.keywords,
                        'servers': list(kit_config.servers.keys())
                    }
                else:
                    result[kit_name] = {
                        'loaded': False,
                        'path': str(kit_path),
                        'description': 'Failed to load kit metadata',
                        'author': None,
                        'version': None,
                        'keywords': [],
                        'servers': []
                    }

        return result

    def get_kit_details(self, kit_name: str) -> dict[str, Any] | None:
        """Get detailed information about a specific kit.

        Returns:
            Kit information dict or None if not found
        """
        loaded_kits = self.kits
        if kit_name in loaded_kits:
            kit_config = loaded_kits[kit_name]
            return {
                'loaded': True,
                'name': kit_config.name,
                'description': kit_config.description,
                'author': kit_config.author,
                'version': kit_config.version,
                'keywords': kit_config.keywords,
                'links': kit_config.links,
                'servers': {
                    name: server.model_dump(mode="json", exclude_unset=True, exclude_none=True, exclude_defaults=True)
                    for name, server in kit_config.servers.items()
                }
            }

        available_kits = self.discover_kits()
        if kit_name in available_kits:
            kit_path = available_kits[kit_name]
            kit_config = self.load_kit(kit_path)
            if kit_config:
                return {
                    'loaded': False,
                    'path': str(kit_path),
                    'name': kit_config.name,
                    'description': kit_config.description,
                    'author': kit_config.author,
                    'version': kit_config.version,
                    'keywords': kit_config.keywords,
                    'links': kit_config.links,
                    'servers': {
                        name: server.model_dump(mode="json", exclude_unset=True, exclude_none=True, exclude_defaults=True)
                        for name, server in kit_config.servers.items()
                    }
                }

        return None
