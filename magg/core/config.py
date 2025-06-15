"""Configuration management for MAGG - Simplified data model."""

import json
import logging
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict
from enum import Enum


@dataclass
class MCPSource:
    """Enhanced source with rich metadata for server configuration."""
    url: str  # Canonical URL - primary identifier
    name: str | None = None  # Optional hint, can be auto-generated from URL
    metadata: list[dict[str, Any]] | None = None  # Flexible metadata from multiple sources
    
    def __post_init__(self):
        """Auto-generate name from URL if not provided and initialize metadata."""
        if not self.name:
            # Extract name from URL (GitHub repo, NPM package, etc.)
            if 'github.com' in self.url:
                parts = self.url.rstrip('/').split('/')
                if len(parts) >= 2:
                    self.name = parts[-1]  # repo name
                else:
                    self.name = "github_source"
            elif 'npmjs.com' in self.url:
                parts = self.url.split('/')
                if 'package' in parts:
                    pkg_idx = parts.index('package')
                    if pkg_idx + 1 < len(parts):
                        self.name = parts[pkg_idx + 1]
                    else:
                        self.name = "npm_package"
                else:
                    self.name = "npm_source"
            elif 'glama.ai' in self.url:
                self.name = "glama_source"
            else:
                # Fallback to domain name
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(self.url)
                    if parsed.netloc:
                        self.name = parsed.netloc.replace('.', '_')
                    else:
                        # If URL parsing fails, use a simple fallback
                        self.name = "unknown_source"
                except:
                    self.name = "unknown_source"
        
        # Initialize metadata list if not provided
        if self.metadata is None:
            self.metadata = []
    
    def add_metadata(self, source_name: str, data: dict[str, Any]) -> None:
        """Add metadata from a specific source (e.g., 'glama', 'github', 'http_check')."""
        metadata_entry = {
            "source": source_name,
            "collected_at": None,  # Will be set when actually collected
            "data": data
        }
        self.metadata.append(metadata_entry)
    
    def get_metadata_by_source(self, source_name: str) -> list[dict[str, Any]]:
        """Get all metadata entries from a specific source."""
        return [entry for entry in self.metadata if entry.get("source") == source_name]
    
    def get_setup_hints(self) -> list[str]:
        """Extract setup/installation hints from all metadata sources."""
        hints = []
        for entry in self.metadata:
            data = entry.get("data", {})
            # Extract various setup-related fields
            if "install_command" in data:
                hints.append(f"Install: {data['install_command']}")
            if "setup_instructions" in data:
                hints.append(f"Setup: {data['setup_instructions']}")
            if "command" in data:
                hints.append(f"Command: {data['command']}")
            if "port" in data:
                hints.append(f"Port: {data['port']}")
            if "requirements" in data:
                hints.append(f"Requirements: {data['requirements']}")
        return hints
    
    def is_direct_mcp_server(self) -> bool:
        """Check if this appears to be a direct MCP server based on metadata."""
        for entry in self.metadata:
            if entry.get("source") == "http_check":
                return entry.get("data", {}).get("is_mcp_server", False)
        return False


@dataclass
class MCPServer:
    """Server configuration - how to actually run an MCP server from a source."""
    name: str  # Unique server name
    source_url: str  # Reference to source URL
    prefix: str | None = None  # Tool prefix for this server
    notes: str | None = None  # Setup notes for LLM and humans
    
    # Connection details
    command: str | None = None  # Main command (e.g., "python", "node", "uvx", "npx")
    args: list[str] | None = None  # Command arguments
    uri: str | None = None  # URI for HTTP servers
    env: dict[str, str] | None = None  # Environment variables
    working_dir: str | None = None  # Working directory
    transport: dict[str, Any] | None = None  # Transport-specific configuration
    
    def __post_init__(self):
        """Set default prefix to server name if not provided."""
        if not self.prefix:
            self.prefix = self.name


@dataclass
class MAGGConfig:
    """Main MAGG configuration - sources and servers."""
    sources: dict[str, MCPSource] = None  # URL -> MCPSource
    servers: dict[str, MCPServer] = None  # name -> MCPServer
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = {}
        if self.servers is None:
            self.servers = {}
    
    def add_source(self, source: MCPSource) -> None:
        """Add a source."""
        self.sources[source.url] = source
    
    def remove_source(self, url: str) -> bool:
        """Remove a source and all its servers."""
        if url in self.sources:
            # Remove all servers that reference this source
            servers_to_remove = [name for name, server in self.servers.items() 
                               if server.source_url == url]
            for server_name in servers_to_remove:
                del self.servers[server_name]
            
            del self.sources[url]
            return True
        return False
    
    def add_server(self, server: MCPServer) -> None:
        """Add a server."""
        self.servers[server.name] = server
    
    def remove_server(self, name: str) -> bool:
        """Remove a server."""
        if name in self.servers:
            del self.servers[name]
            return True
        return False
    
    def get_servers_for_source(self, source_url: str) -> list[MCPServer]:
        """Get all servers for a given source."""
        return [server for server in self.servers.values() if server.source_url == source_url]


class ConfigManager:
    """Manages MAGG configuration persistence."""
    
    def __init__(self, config_path: str | None = None):
        """Initialize config manager."""
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path.cwd() / ".magg" / "config.json"
        
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> MAGGConfig:
        """Load configuration from disk."""
        if not self.config_path.exists():
            return MAGGConfig()
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            # Deserialize sources
            sources = {}
            for url, source_data in data.get('sources', {}).items():
                sources[url] = MCPSource(**source_data)
            
            # Deserialize servers
            servers = {}
            for name, server_data in data.get('servers', {}).items():
                servers[name] = MCPServer(**server_data)
            
            config = MAGGConfig(sources=sources, servers=servers)
            return config
        
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return MAGGConfig()
    
    def save_config(self, config: MAGGConfig) -> bool:
        """Save configuration to disk."""
        try:
            data = {
                'sources': {url: asdict(source) for url, source in config.sources.items()},
                'servers': {name: asdict(server) for name, server in config.servers.items()}
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            return False