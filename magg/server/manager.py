"""Server management for Magg - mounting, unmounting, and tracking MCP servers.
"""
import logging
from functools import cached_property

from fastmcp import FastMCP, Client

from .defaults import MAGG_INSTRUCTIONS
from ..auth import BearerAuthManager
from ..proxy.server import ProxyFastMCP
from ..settings import ConfigManager, MaggConfig, ServerConfig
from ..util.transport import get_transport_for_command, get_transport_for_uri

logger = logging.getLogger(__name__)


class ServerManager:
    """Manages MCP servers - mounting, unmounting, and tracking."""
    config_manager: ConfigManager
    mcp: ProxyFastMCP
    mounted_servers: dict

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

        auth_config = config_manager.load_auth_config()
        auth_provider = None

        if auth_config.bearer.private_key_exists:
            auth_manager = BearerAuthManager(auth_config.bearer)
            try:
                auth_provider = auth_manager.provider
                logger.info("Authentication enabled (bearer)")
            except RuntimeError as e:
                logger.warning(f"Authentication disabled: {e}")

        # Create FastMCP instance with optional auth
        self.mcp = ProxyFastMCP(
            name=self.self_prefix,
            instructions=MAGG_INSTRUCTIONS.format(self_prefix=self.self_prefix),
            auth=auth_provider
        )
        self.mounted_servers = {}

    @property
    def config(self) -> MaggConfig:
        """Get the current Magg configuration."""
        return self.config_manager.load_config()

    def save_config(self, config: MaggConfig):
        """Save the current configuration to disk."""
        return self.config_manager.save_config(config)

    @cached_property
    def prefix_separator(self) -> str:
        """Get the prefix separator for this Magg server - cannot be changed during process lifetime."""
        return ServerConfig.PREFIX_SEP

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this Magg server - cannot be changed during process lifetime."""
        return self.config.self_prefix

    async def mount_server(self, server: ServerConfig) -> bool:
        """Mount a server using FastMCP."""
        if not server.enabled:
            logger.info("Server %s is disabled, skipping mount", server.name)
            return False

        if server.name in self.mounted_servers:
            logger.warning("Server %s is already mounted, skipping", server.name)
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
                logger.error("No command or URI specified for %s", server.name)
                return False

            # Create proxy and mount
            proxy_server = FastMCP.as_proxy(client)
            self.mcp.mount(server.prefix, proxy_server, as_proxy=True)
            # Store both proxy and client for resource/prompt access
            self.mounted_servers[server.name] = {
                'proxy': proxy_server,
                'client': client
            }

            logger.debug("Mounted server %s with prefix %s", server.name, server.prefix)
            return True

        except Exception as e:
            logger.error("Failed to mount server %s: %s", server.name, e)
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
                logger.debug("Called unmount for prefix %s", server.prefix)

            # Remove from our tracking
            del self.mounted_servers[name]
            logger.info("Unmounted server %s", name)
            return True

        else:
            logger.warning("Server %s is not mounted, cannot unmount", name)
            return False

    async def mount_all_enabled(self):
        """Mount all enabled servers from config."""
        config = self.config
        enabled_servers = config.get_enabled_servers()

        if not enabled_servers:
            logger.info("No enabled servers to mount")
            return

        logger.info("Mounting %d enabled servers...", len(enabled_servers))

        results = []
        for name, server in enabled_servers.items():
            try:
                success = await self.mount_server(server)
                results.append((name, success))
            except Exception as e:
                logger.error("Error mounting %s: %s", name, e)
                results.append((name, False))

        # Log results
        successful = [name for name, success in results if success]
        failed = [name for name, success in results if not success]

        if successful:
            logger.info("Successfully mounted: %s", ', '.join(successful))
        if failed:
            logger.warning("Failed to mount: %s", ', '.join(failed))


class ManagedServer:
    server_manager: ServerManager

    def __init__(self, server_manager: ServerManager):
        self.server_manager = server_manager

    @property
    def mcp(self) -> FastMCP:
        return self.server_manager.mcp

    @property
    def config(self) -> MaggConfig:
        """Get the current Magg configuration.
        """
        return self.server_manager.config

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this Magg server.

        Cannot be changed during process lifetime.
        """
        return self.server_manager.self_prefix

    @cached_property
    def self_prefix_(self) -> str:
        """self_prefix with trailing separator.
        """
        return f"{self.self_prefix}{self.server_manager.prefix_separator}"

    def save_config(self, config: MaggConfig):
        """Save the current configuration to disk."""
        return self.server_manager.save_config(config)
