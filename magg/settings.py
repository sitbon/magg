"""Configuration management for MAGG - Using pydantic-settings."""

import json
import logging
from functools import cached_property
from pathlib import Path
from typing import Any
from pydantic import field_validator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Server configuration - defines how to run an MCP server."""
    model_config = SettingsConfigDict(
        # Environment variable prefix
        env_prefix="MAGG_SERVER_",
        # Allow .env file
        env_file=".env",
        # Allow extra fields
        extra="ignore",
        # Use nested delimiter for complex configs
        env_nested_delimiter="__",
        # Validate on assignment
        validate_assignment=True,
        # Allow arbitrary types
        arbitrary_types_allowed=True
    )
    
    name: str = Field(..., description="Unique server name - can contain any characters")
    source: str = Field(..., description="URL/URI of the server package, repository, or listing")
    prefix: str = Field(default="", description="Tool prefix for this server - must be a valid Python identifier without underscores")
    notes: str | None = Field(None, description="Setup notes for LLM and humans")
    
    # Connection details
    command: str | None = Field(None, description='Main command (e.g., "python", "node", "uvx", "npx")')
    args: list[str] | None = Field(None, description="Command arguments")
    uri: str | None = Field(None, description="URI for HTTP servers")
    env: dict[str, str] | None = Field(None, description="Environment variables")
    working_dir: str | None = Field(None, description="Working directory")
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
                raise ValueError(f"Server prefix '{v}' must be a valid Python identifier (letters and numbers only, not starting with a number)")
            if '_' in v:
                raise ValueError("Server prefix cannot contain underscores ('_')")
        return v
    
    @classmethod
    def generate_prefix_from_name(cls, name: str) -> str:
        """Generate a valid prefix from a server name.
        
        Removes special characters and ensures it's a valid Python identifier
        without underscores.
        """
        # Replace common separators with nothing
        prefix = name.replace('-', '').replace('_', '').replace('.', '').replace(' ', '')
        
        # Remove any remaining non-alphanumeric characters
        prefix = ''.join(c for c in prefix if c.isalnum())
        
        # Ensure it doesn't start with a number
        if prefix and prefix[0].isdigit():
            prefix = 'srv' + prefix
        
        # If empty or still invalid, use a default
        if not prefix or not prefix.isidentifier():
            prefix = 'server'
        
        return prefix.lower()[:30]


class MAGGConfig(BaseSettings):
    """Main MAGG configuration."""
    model_config = SettingsConfigDict(
        # Environment variable prefix
        env_prefix="MAGG_",
        # Allow .env file
        env_file=".env",
        # Allow extra fields
        extra="ignore",
        # Use nested delimiter
        env_nested_delimiter="__",
        # Validate on assignment
        validate_assignment=True,
        # Allow arbitrary types
        arbitrary_types_allowed=True
    )

    debug: bool = Field(default=False, description="Enable debug mode for MAGG")
    log_level: str = Field(default="INFO", description="Logging level for MAGG")
    config_path: Path = Field(default_factory=lambda: Path.cwd() / ".magg" / "config.json", description="Configuration file path (can be overridden by MAGG_CONFIG_PATH)")
    servers: dict[str, ServerConfig] = Field(default_factory=dict, description="Servers configuration (loaded from JSON file)")

    @model_validator(mode='after')
    def export_environment_variables(self) -> 'MAGGConfig':
        """Export log_level and config_path as environment variables, in case they were not set that way.
        """
        import os

        if 'MAGG_LOG_LEVEL' not in os.environ:
            os.environ['MAGG_LOG_LEVEL'] = self.log_level

        if 'MAGG_CONFIG_PATH' not in os.environ:
            os.environ['MAGG_CONFIG_PATH'] = str(self.config_path)

        return self

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
    """Manages MAGG configuration persistence."""
    
    def __init__(self, config_path: str | None = None):
        """Initialize config manager."""
        # Load base settings (gets env vars)
        self.settings = MAGGConfig()
        
        # Override config path if provided
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = self.settings.config_path
        
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    @cached_property
    def logger(self) -> logging.Logger:
        """Get logger for this manager."""
        return logging.getLogger(__name__)

    def load_config(self) -> MAGGConfig:
        """Load configuration from disk."""
        # Start with settings from environment
        config = self.settings
        
        if not self.config_path.exists():
            return config
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            # Deserialize servers from JSON file
            servers = {}
            for name, server_data in data.get('servers', {}).items():
                try:
                    server_data['name'] = name  # Ensure name is set and same as key
                    servers[name] = ServerConfig(**server_data)
                except Exception as e:
                    self.logger.error(f"Error loading server '{name}': {e}")
                    # Skip invalid servers
                    continue
            
            config.servers = servers
            return config
        
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return config
    
    def save_config(self, config: MAGGConfig) -> bool:
        """Save configuration to disk."""
        try:
            # Only save servers to JSON, other settings come from env
            data = {
                'servers': {
                    name: server.model_dump(
                        exclude_unset=True, exclude_none=True, exclude_defaults=True, by_alias=True,
                        exclude={'name'},
                    )
                    for name, server in config.servers.items()
                }
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            return False
