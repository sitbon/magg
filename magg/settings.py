"""Configuration management for Magg - Using pydantic-settings."""
import json
import logging
import os
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from .reload import ConfigChange

from pydantic import field_validator, Field, model_validator, AnyUrl, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .util.system import get_project_root
from .util.paths import get_contrib_paths

__all__ = "ServerConfig", "MaggConfig", "ConfigManager", "AuthConfig", "BearerAuthConfig", "ClientSettings", "KitInfo"

logger = logging.getLogger(__name__)


class KitInfo(BaseModel):
    """Information about a loaded kit."""
    model_config = {
        "extra": "allow",
        "validate_assignment": True,
    }
    
    name: str = Field(..., description="Kit name")
    description: str | None = Field(None, description="Kit description")
    path: str | None = Field(None, description="Path to kit file (if file-based)")
    source: str | None = Field(None, description="Source of the kit (file, inline, etc)")


class ClientSettings(BaseSettings):
    """Client settings loaded from environment."""
    model_config = SettingsConfigDict(
        env_prefix="MAGG_",
        env_file=".env",
        extra="ignore",
        validate_assignment=True,
    )

    jwt: str | None = Field(
        default=None,
        description="JWT token for authentication (env: MAGG_JWT)"
    )


class BearerAuthConfig(BaseSettings):
    """Bearer token authentication configuration."""
    model_config = SettingsConfigDict(
        extra="allow",
        validate_assignment=True,
    )
    issuer: str = Field(default="https://magg.local", description="Token issuer identifier")
    audience: str = Field(default="magg", description="Token audience")
    key_path: Path = Field(
        default_factory=lambda: Path.home() / ".ssh" / "magg",
        description="Path for private & public key storage"
    )

    @property
    def private_key_env(self) -> str | None:
        """Get private key from MAGG_PRIVATE_KEY environment variable."""
        return os.environ.get('MAGG_PRIVATE_KEY')

    @property
    def private_key_path(self) -> Path:
        """Get the path to the private key file."""
        return self.key_path / f"{self.audience}.key"

    @property
    def public_key_path(self) -> Path:
        """Get the path to the public SSH key file."""
        return self.key_path / f"{self.audience}.key.pub"

    @property
    def private_key_data(self) -> str | None:
        """Get private key data from env var or file."""
        # Try env var first
        if self.private_key_env:
            # Handle single-line format (literal \n)
            return self.private_key_env.replace('\\n', '\n')

        # Try file
        if self.private_key_path.exists():
            return self.private_key_path.read_text()

        return None

    @property
    def public_key_data(self) -> str | None:
        """Get public key data from file."""
        if self.public_key_path.exists():
            return self.public_key_path.read_text()
        return None

    @property
    def private_key_exists(self) -> bool:
        """Check if private key exists (either in env var or file)."""
        return bool(self.private_key_env) or self.private_key_path.exists()

    @property
    def public_key_exists(self) -> bool:
        """Check if public key file exists."""
        return self.public_key_path.exists()


class AuthConfig(BaseSettings):
    """Top-level authentication configuration."""
    model_config = SettingsConfigDict(
        extra="allow",
        validate_assignment=True,
    )
    bearer: BearerAuthConfig = Field(
        default_factory=BearerAuthConfig,
        description="Bearer token authentication config"
    )


class ServerConfig(BaseSettings):
    """Server configuration - defines how to run an MCP server."""
    model_config = SettingsConfigDict(
        extra="allow",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    name: str = Field(..., description="Unique server name - can contain any characters")
    source: str = Field(..., description="URL/URI/path of the server package, repository, or listing")
    prefix: str | None = Field(
        default=None,
        description="Tool prefix for this server - must be a valid Python identifier without underscores."
    )
    notes: str | None = Field(None, description="Setup notes for LLM and humans")

    # Connection details
    command: str | None = Field(None, description='Main command (e.g., "python", "node", "uvx", "npx")')
    args: list[str] | None = Field(None, description="Command arguments")
    uri: str | None = Field(None, description="URI for HTTP servers")
    env: dict[str, str] | None = Field(None, description="Environment variables")
    cwd: Path | None = Field(None, description="Working directory")
    transport: dict[str, Any] | None = Field(None, description="Transport-specific configuration")
    enabled: bool = Field(True, description="Whether server is enabled")
    kits: list[str] = Field(default_factory=list, description="List of kits this server was added from")

    @model_validator(mode='after')
    def set_default_prefix(self) -> 'ServerConfig':
        """No longer set default prefix - None is allowed."""
        return self

    @field_validator('prefix')
    def validate_prefix(cls, v: str | None) -> str | None:
        """Validate that prefix is a valid Python identifier without underscores."""
        if v:
            if not v.isidentifier():
                raise ValueError(
                    f"Server prefix {v!r} must be a valid Python identifier (letters and numbers only, not starting with a number)"
                )
            if "_" in v:
                raise ValueError(
                    f"Server prefix {v!r} must be a valid Python identifier and cannot contain underscores"
                )
        return v

    @field_validator('transport')
    def validate_transport(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and not v:
            v = None  # Normalize empty dict to None
        return v

    @field_validator('uri')
    def validate_uri(cls, v: str | None) -> str | None:
        if v:
            AnyUrl(v)
        return v


class MaggConfig(BaseSettings):
    """Main Magg configuration."""
    model_config = SettingsConfigDict(
        env_prefix="MAGG_",
        env_file=".env",
        extra="allow",
        validate_assignment=True,
        arbitrary_types_allowed=True,
        env_ignore_empty=True,
    )

    path: str | list[Path] = Field(
        default_factory=lambda: [
            get_project_root() / ".magg",
            Path.home() / ".magg", 
            *get_contrib_paths()
        ],
        description="Multi-path search list for config.json and kit.d directories (env: MAGG_PATH, colon-separated)"
    )
    config_path: Path | None = Field(
        default=None,
        description="Explicit configuration file path (overrides path search) (env: MAGG_CONFIG_PATH)"
    )
    read_only: bool = Field(default=False, description="Run in read-only mode (env: MAGG_READ_ONLY)")
    quiet: bool = Field(default=False, description="Suppress output unless errors occur (env: MAGG_QUIET)")
    debug: bool = Field(default=False, description="Enable debug mode for Magg (env: MAGG_DEBUG)")
    log_level: str | None = Field(default=None, description="Logging level for Magg (default: INFO) (env: MAGG_LOG_LEVEL)")
    self_prefix: str = Field(
        default="magg",
        description="Prefix for Magg tools and commands - must be a valid Python identifier without underscores (env: MAGG_SELF_PREFIX)"
    )
    prefix_sep: str = Field(
        default="_",
        description="Separator between prefix and tool name (env: MAGG_PREFIX_SEP)"
    )
    auto_reload: bool = Field(default=True, description="Enable automatic config reloading on file changes (env: MAGG_AUTO_RELOAD)")
    reload_poll_interval: float = Field(default=1.0, description="Config file poll interval in seconds (env: MAGG_RELOAD_POLL_INTERVAL)")
    reload_use_watchdog: bool | None = Field(default=None, description="Use file system notifications if available, None=auto-detect (env: MAGG_RELOAD_USE_WATCHDOG)")
    stderr_show: bool = Field(default=False, description="Show stderr output from subprocess MCP servers (env: MAGG_STDERR_SHOW)")
    servers: dict[str, ServerConfig] = Field(default_factory=dict, description="Servers configuration (loaded from config_path)")
    kits: dict[str, KitInfo] = Field(default_factory=dict, description="Loaded kits with metadata")

    @field_validator('path', mode='after')
    @classmethod
    def parse_path(cls, v) -> list[Path]:
        """Parse MAGG_PATH environment variable or return default."""
        if isinstance(v, str):
            return [Path(p.strip()).expanduser() for p in v.split(':') if p.strip()]
        elif isinstance(v, list) and v and not isinstance(v[0], Path):
            return [Path(p).expanduser() for p in v]
        elif isinstance(v, list):
            return v
        else:
            return [
                get_project_root() / ".magg",
                Path.home() / ".magg", 
                *get_contrib_paths()
            ]

    def get_config_path(self) -> Path:
        """Get the actual config path, either explicit or searched from path list."""
        if self.config_path:
            return self.config_path
        
        for search_path in self.path:
            config_file = search_path / "config.json"
            if config_file.exists():
                return config_file
        
        # Return first path location for new config creation
        return self.path[0] / "config.json"

    def get_kitd_paths(self) -> list[Path]:
        """Get all kit.d directories from the path list."""
        kitd_paths = []
        for search_path in self.path:
            kitd_path = search_path / "kit.d"
            if kitd_path.exists() and kitd_path.is_dir():
                kitd_paths.append(kitd_path)
        return kitd_paths

    def get_script_paths(self) -> list[Path]:
        """Get all *.mbro script files recursively from the path list."""
        script_files = []
        for search_path in self.path:
            if search_path.exists() and search_path.is_dir():
                script_files.extend(search_path.rglob("*.mbro"))
        return script_files

    @model_validator(mode='after')
    def export_environment_variables(self) -> 'MaggConfig':
        """Export log_level and config_path as environment variables, in case they were not set that way.
        """
        if self.quiet and self.log_level is None:
            self.log_level = 'CRITICAL'

        if 'MAGG_LOG_LEVEL' not in os.environ and self.log_level is not None:
            os.environ['MAGG_LOG_LEVEL'] = self.log_level

        return self

    @field_validator('self_prefix')
    def validate_self_prefix(cls, v: str) -> str:
        """Validate that self_prefix is a valid Python identifier without underscores."""
        if v:
            if not v.isidentifier():
                raise ValueError(f"Server prefix '{v}' must be a valid Python identifier (letters and numbers only, not starting with a number)")
            if '_' in v:
                raise ValueError("Server prefix cannot contain underscores ('_')")
        return v

    def add_server(self, server: ServerConfig) -> None:
        """Add a server."""
        self.servers[server.name] = server

    def remove_server(self, name: str) -> bool:
        """Remove a server."""
        if name in self.servers:
            del self.servers[name]
            return True
        return False

    def get_enabled_servers(self) -> dict[str, ServerConfig]:
        """Get all enabled servers."""
        return {name: server for name, server in self.servers.items() if server.enabled}


class ConfigManager:
    """Manages Magg configuration persistence."""
    config_path: Path
    auth_config_path: Path
    auth_config: AuthConfig | None = None
    read_only: bool
    _reload_manager: Any = None  # ReloadManager instance

    def __init__(self, config_path: Path | str | None = None):
        """Initialize config manager."""
        config = MaggConfig()
        self.read_only = config.read_only

        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = config.get_config_path()

        self.auth_config_path = self.config_path.parent / "auth.json"

    @cached_property
    def logger(self) -> logging.Logger:
        """Get logger for this manager."""
        return logging.getLogger(__name__)

    def load_config(self) -> MaggConfig:
        """Load configuration from disk or return cached version if reload is enabled.

        Note: The only dynamic part of the config is the servers.
        """
        if self._reload_manager:
            cached = self._reload_manager.cached_config
            if cached:
                return cached

        config = MaggConfig()

        if not self.config_path.exists():
            return config

        try:
            with self.config_path.open("r") as f:
                data = json.load(f)

            servers = {}

            for name, server_data in data.pop('servers', {}).items():
                try:
                    server_data['name'] = name
                    servers[name] = ServerConfig.model_validate(server_data)
                except Exception as e:
                    self.logger.error("Error loading server %r: %s", name, e)
                    continue

            config.servers = servers

            if 'kits' in data:
                # Handle both old format (list of strings) and new format (dict)
                kits_data = data.pop('kits', {})
                if isinstance(kits_data, list):
                    # Convert old format to new format
                    config.kits = {
                        kit_name: KitInfo(name=kit_name, source="legacy")
                        for kit_name in kits_data
                    }
                else:
                    # Load new format
                    config.kits = {
                        name: KitInfo.model_validate(kit_data) if isinstance(kit_data, dict) else KitInfo(name=name)
                        for name, kit_data in kits_data.items()
                    }

            for key, value in data.items():
                if not hasattr(config, key):
                    self.logger.warning("Setting unknown config key %r in %s.", key, self.config_path)
                setattr(config, key, value)

            return config

        except Exception as e:
            self.logger.error("Error loading config: %s", e)
            return config

    def save_config(self, config: MaggConfig) -> bool:
        """Save configuration to disk."""
        if config.read_only:
            self.logger.warning("Config is read-only, not saving.")
            return False

        if self.read_only:
            raise RuntimeError("Config read_only value cannot be changed after initialization.")

        try:
            # Notify the reloader to ignore the next file change since we're making it
            if self._reload_manager:
                self._reload_manager.ignore_next_change()

            data = {
                'servers': {
                    name: server.model_dump(
                        mode="json",
                        exclude_unset=True, exclude_none=True, exclude_defaults=True, by_alias=True,
                        exclude={'name'},
                    )
                    for name, server in config.servers.items()
                }
            }

            if config.kits:
                data['kits'] = {
                    name: kit_info.model_dump(
                        mode="json",
                        exclude_unset=True, exclude_none=True, exclude_defaults=True
                    )
                    for name, kit_info in config.kits.items()
                }

            if not self.config_path.parent.exists():
                self.logger.warning("Creating new directory: %s", self.config_path.parent)
                self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with self.config_path.open("w") as f:
                json.dump(data, f, indent=2)

            # Update the reload manager's cached config to stay in sync
            if self._reload_manager:
                self._reload_manager.update_cached_config(config)

            return True

        except Exception as e:
            self.logger.error("Error saving config: %s", e)
            return False

    async def setup_config_reload(self, reload_callback: Callable[['ConfigChange'], Coroutine[None, None, None]]) -> None:
        """Setup config file watching with a callback.

        Args:
            reload_callback: Async callback to handle config changes
        """
        # Import here to avoid circular dependency
        from .reload import ReloadManager

        if not self._reload_manager:
            self._reload_manager = ReloadManager(self)

        await self._reload_manager.setup(reload_callback)

    async def stop_config_reload(self) -> None:
        """Stop config file watching."""
        if self._reload_manager:
            await self._reload_manager.stop()
            self._reload_manager = None

    async def reload_config(self) -> bool:
        """Manually trigger a configuration reload.

        Returns:
            True if reload was successful, False otherwise
        """
        if not self._reload_manager:
            self.logger.error("Config reload not setup")
            return False

        return await self._reload_manager.reload()

    def load_auth_config(self) -> AuthConfig:
        """Load authentication configuration from disk or return defaults."""
        if self.auth_config is not None:
            return self.auth_config

        if not self.auth_config_path.exists():
            self.logger.debug("No auth.json found, using default auth config")
            return AuthConfig()

        try:
            with self.auth_config_path.open("r") as f:
                data = json.load(f)

            self.auth_config = AuthConfig.model_validate(data)
            return self.auth_config

        except Exception as e:
            self.logger.error("Error loading auth config: %s", e)
            return AuthConfig()

    def save_auth_config(self, auth_config: AuthConfig) -> bool:
        """Save authentication configuration to disk."""
        if self.read_only:
            self.logger.warning("Auth config is read-only, not saving.")
            return False

        try:
            if not self.auth_config_path.parent.exists():
                self.logger.warning("Creating new directory: %s", self.auth_config_path.parent)
                self.auth_config_path.parent.mkdir(parents=True, exist_ok=True)

            data = auth_config.model_dump(
                mode="json",
                exclude_none=True
            )

            with self.auth_config_path.open("w") as f:
                json.dump(data, f, indent=2)

            self.auth_config = auth_config
            return True

        except Exception as e:
            self.logger.error("Error saving auth config: %s", e)
            return False
