"""Server management for MAGG - mounting, unmounting, and tracking MCP servers.
"""
from functools import cached_property
import logging

from fastmcp import FastMCP, Client

from .defaults import MAGG_INSTRUCTIONS
from ..settings import ConfigManager, MAGGConfig, ServerConfig
from ..util import get_transport_for_command, get_transport_for_uri

LOG = logging.getLogger(__name__)


class ServerManager:
    """Manages MCP servers - mounting, unmounting, and tracking."""
    config_manager: ConfigManager
    mcp: FastMCP
    mounted_servers: dict

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.mcp = FastMCP(
            name=self.self_prefix,
            instructions=MAGG_INSTRUCTIONS.format(self_prefix=self.self_prefix),
        )
        self.mounted_servers = {}

    @property
    def config(self) -> MAGGConfig:
        """Get the current MAGG configuration."""
        return self.config_manager.load_config()

    def save_config(self, config: MAGGConfig):
        """Save the current configuration to disk."""
        return self.config_manager.save_config(config)

    @cached_property
    def prefix_separator(self) -> str:
        """Get the prefix separator for this MAGG server - cannot be changed during process lifetime."""
        return ServerConfig.PREFIX_SEP

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this MAGG server - cannot be changed during process lifetime."""
        return self.config.self_prefix

    async def mount_server(self, server: ServerConfig) -> bool:
        """Mount a server using FastMCP."""
        if not server.enabled:
            LOG.info("Server %s is disabled, skipping mount", server.name)
            return False

        if server.name in self.mounted_servers:
            LOG.warning("Server %s is already mounted, skipping", server.name)
            return False

        try:
            if server.command:
                # Command-based server
                transport = get_transport_for_command(
                    command=server.command,
                    args=server.args or [],
                    env=server.env,
                    working_dir=server.working_dir,
                    transport_config=server.transport
                )
                client = Client(transport)

            elif server.uri:
                # URI-based server
                transport = get_transport_for_uri(
                    uri=server.uri,
                    transport_config=server.transport
                )
                client = Client(transport)

            else:
                LOG.error("No command or URI specified for %s", server.name)
                return False

            # Create proxy and mount
            proxy_server = FastMCP.as_proxy(client)
            self.mcp.mount(server.prefix, proxy_server, as_proxy=True)
            # Store both proxy and client for resource/prompt access
            self.mounted_servers[server.name] = {
                'proxy': proxy_server,
                'client': client
            }

            LOG.debug("Mounted server %s with prefix %s", server.name, server.prefix)
            return True

        except Exception as e:
            LOG.error("Failed to mount server %s: %s", server.name, e)
            return False

    # noinspection PyProtectedMember
    async def unmount_server(self, name: str) -> bool:
        """Unmount a server."""
        if name in self.mounted_servers:
            # Get the server config to find the prefix
            config = self.config
            server = config.servers.get(name)
            if server and server.prefix in self.mcp._mounted_servers:
                # Properly unmount from FastMCP
                self.mcp.unmount(server.prefix)
                LOG.debug("Called unmount for prefix %s", server.prefix)

            # Remove from our tracking
            del self.mounted_servers[name]
            LOG.info("Unmounted server %s", name)
            return True

        else:
            LOG.warning("Server %s is not mounted, cannot unmount", name)
            return False

    async def mount_all_enabled(self):
        """Mount all enabled servers from config."""
        config = self.config
        enabled_servers = config.get_enabled_servers()

        if not enabled_servers:
            LOG.info("No enabled servers to mount")
            return

        LOG.info("Mounting %d enabled servers...", len(enabled_servers))

        results = []
        for name, server in enabled_servers.items():
            try:
                success = await self.mount_server(server)
                results.append((name, success))
            except Exception as e:
                LOG.error("Error mounting %s: %s", name, e)
                results.append((name, False))

        # Log results
        successful = [name for name, success in results if success]
        failed = [name for name, success in results if not success]

        if successful:
            LOG.info("Successfully mounted: %s", ', '.join(successful))
        if failed:
            LOG.warning("Failed to mount: %s", ', '.join(failed))


class ManagedServer:
    server_manager: ServerManager

    def __init__(self, server_manager: ServerManager):
        self.server_manager = server_manager

    @property
    def mcp(self) -> FastMCP:
        return self.server_manager.mcp

    @property
    def config(self) -> MAGGConfig:
        """Get the current MAGG configuration.
        """
        return self.server_manager.config

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this MAGG server.

        Cannot be changed during process lifetime.
        """
        return self.server_manager.self_prefix

    @cached_property
    def self_prefix_(self) -> str:
        """self_prefix with trailing separator.
        """
        return f"{self.self_prefix}{self.server_manager.prefix_separator}"

    def save_config(self, config: MAGGConfig):
        """Save the current configuration to disk."""
        return self.server_manager.save_config(config)
