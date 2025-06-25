"""Configuration management for Magg - Using pydantic-settings."""
import json
import logging
import os
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

from pydantic import field_validator, Field, model_validator, AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from .util.system import get_project_root

__all__ = "ServerConfig", "MaggConfig", "ConfigManager", "AuthConfig", "BearerAuthConfig", "ClientSettings"

logger = logging.getLogger(__name__)


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

    PREFIX_SEP: ClassVar[str] = "_"

    name: str = Field(..., description="Unique server name - can contain any characters")
    source: str = Field(..., description="URL/URI/path of the server package, repository, or listing")
    prefix: str = Field(
        default="",
        description=f"Tool prefix for this server - must be a valid Python identifier without {PREFIX_SEP!r}."
    )
    notes: str | None = Field(None, description="Setup notes for LLM and humans")

    # Connection details
    command: str | None = Field(None, description='Main command (e.g., "python", "node", "uvx", "npx")')
    args: list[str] | None = Field(None, description="Command arguments")
    uri: str | None = Field(None, description="URI for HTTP servers")
    env: dict[str, str] | None = Field(None, description="Environment variables")
    working_dir: Path | None = Field(None, description="Working directory")
    transport: dict[str, Any] | None = Field(None, description="Transport-specific configuration")
    enabled: bool = Field(True, description="Whether server is enabled")

    @model_validator(mode='after')
    def set_default_prefix(self) -> 'ServerConfig':
        """Set default prefix from name if not provided."""
        if not self.prefix:
            self.prefix = self.generate_prefix_from_name(self.name)
        return self

    @field_validator('prefix')
    def validate_prefix(cls, v: str | None) -> str | None:
        """Validate that prefix is a valid Python identifier without underscores."""
        if v:  # Only validate if non-empty
            if not v.isidentifier():
                raise ValueError(
                    f"Server prefix {v!r} must be a valid Python identifier (letters and numbers only, not starting with a number)"
                )
            if cls.PREFIX_SEP in v:
                raise ValueError(
                    f"Server prefix {v!r} must be a valid Python identifier and cannot contain {cls.PREFIX_SEP!r}"
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
            AnyUrl(v)  # Validate as URL
        return v

    @classmethod
    def generate_prefix_from_name(cls, name: str) -> str:
        """Generate a valid prefix from a server name.

        Removes special characters and ensures it's a valid Python identifier
        without underscores.
        """
        prefix = (
            name.replace('-', '')
                .replace('_', '')
                .replace('.', '')
                .replace(' ', '')
                .replace(cls.PREFIX_SEP, '')
        )

        prefix = ''.join(c for c in prefix if c.isalnum())

        if prefix and prefix[0].isdigit():
            prefix = 'srv' + prefix

        if not prefix or not prefix.isidentifier():
            prefix = 'server'

        return prefix.lower()[:30]


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

    config_path: Path = Field(
        default_factory=lambda: get_project_root() / ".magg" / "config.json",
        description="Configuration file path (can be overridden by MAGG_CONFIG_PATH)"
    )
    read_only: bool = Field(default=False, description="Run in read-only mode (env: MAGG_READ_ONLY)")
    quiet: bool = Field(default=False, description="Suppress output unless errors occur (env: MAGG_QUIET)")
    debug: bool = Field(default=False, description="Enable debug mode for Magg (env: MAGG_DEBUG)")
    log_level: str | None = Field(default=None, description="Logging level for Magg (default: INFO) (env: MAGG_LOG_LEVEL)")
    self_prefix: str = Field(
        default="magg",
        description="Prefix for Magg tools and commands - must be a valid Python identifier without underscores (env: MAGG_SELF_PREFIX)"
    )
    servers: dict[str, ServerConfig] = Field(default_factory=dict, description="Servers configuration (loaded from config_path)")

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
        if v:  # Only validate if non-empty
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

    def __init__(self, config_path: Path | str | None = None):
        """Initialize config manager."""
        config = MaggConfig()
        self.read_only = config.read_only

        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = config.config_path

        self.auth_config_path = self.config_path.parent / "auth.json"

    @cached_property
    def logger(self) -> logging.Logger:
        """Get logger for this manager."""
        return logging.getLogger(__name__)

    def load_config(self) -> MaggConfig:
        """Load configuration from disk.

        Note: The only dynamic part of the config is the servers.
        """
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
                    servers[name] = ServerConfig(**server_data)
                except Exception as e:
                    self.logger.error(f"Error loading server '{name}': {e}")
                    continue

            config.servers = servers

            for key, value in data.items():
                if not hasattr(config, key):
                    self.logger.warning(f"Setting unknown config key '{key}' in {self.config_path}.")
                setattr(config, key, value)

            return config

        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return config

    def save_config(self, config: MaggConfig) -> bool:
        """Save configuration to disk."""
        if config.read_only:
            self.logger.warning("Config is read-only, not saving.")
            return False

        if self.read_only:
            raise RuntimeError("Config read_only value cannot be changed after initialization.")

        try:
            # Only save servers to JSON, other settings come from env
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

            if not self.config_path.parent.exists():
                self.logger.warning(f"Creating new directory: {self.config_path.parent}")
                self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with self.config_path.open("w") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            return False

    def load_auth_config(self) -> AuthConfig:
        """Load authentication configuration from disk or return defaults."""
        if self.auth_config is not None:
            return self.auth_config

        if not self.auth_config_path.exists():
            self.logger.debug(f"No auth.json found, using default auth config")
            return AuthConfig()

        try:
            with self.auth_config_path.open("r") as f:
                data = json.load(f)

            self.auth_config = AuthConfig.model_validate(data)
            return self.auth_config

        except Exception as e:
            self.logger.error(f"Error loading auth config: {e}")
            return AuthConfig()

    def save_auth_config(self, auth_config: AuthConfig) -> bool:
        """Save authentication configuration to disk."""
        if self.read_only:
            self.logger.warning("Auth config is read-only, not saving.")
            return False

        try:
            if not self.auth_config_path.parent.exists():
                self.logger.warning(f"Creating new directory: {self.auth_config_path.parent}")
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
            self.logger.error(f"Error saving auth config: {e}")
            return False
