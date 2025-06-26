"""Server management for Magg - mounting, unmounting, and tracking MCP servers.
"""
import asyncio
import logging
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import FastMCP, Client

from .defaults import MAGG_INSTRUCTIONS
from ..auth import BearerAuthManager
from ..reload import ConfigChange, ServerChange
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
        logger.debug("Attempting to mount server %s (enabled=%s)", server.name, server.enabled)

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
                    cwd=server.cwd,
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

            # Close the client to clean up background tasks
            server_info = self.mounted_servers.get(name, {})
            client: Client = server_info.get('client')
            if client:
                try:
                    await client.close()
                    logger.debug("Closed client for server %s", name)
                except Exception as e:
                    logger.warning("Error closing client for server %s: %s", name, e)

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

    async def handle_config_reload(self, config_change: ConfigChange) -> None:
        """Handle configuration changes by applying server updates.

        Args:
            config_change: The configuration change object with old/new configs and changes
        """
        logger.info("Applying configuration changes...")

        # Process changes in order: remove, disable, update, enable, add
        # This ensures clean transitions

        # First, remove servers that were deleted
        for change in config_change.server_changes:
            if change.action == 'remove':
                await self._handle_server_remove(change)

        # Disable servers that were disabled
        for change in config_change.server_changes:
            if change.action == 'disable':
                await self._handle_server_disable(change)

        # Update servers that changed (requires unmount/remount)
        for change in config_change.server_changes:
            if change.action == 'update':
                await self._handle_server_update(change)

        # Enable servers that were enabled
        for change in config_change.server_changes:
            if change.action == 'enable':
                await self._handle_server_enable(change)

        # Finally, add new servers
        for change in config_change.server_changes:
            if change.action == 'add':
                await self._handle_server_add(change)

        logger.info("Configuration reload complete")

    async def _handle_server_add(self, change: ServerChange) -> None:
        """Handle adding a new server."""
        if change.new_config:
            logger.info("Adding new server: %s", change.name)
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to add server: %s", change.name)

    async def _handle_server_remove(self, change: ServerChange) -> None:
        """Handle removing a server."""
        logger.info("Removing server: %s", change.name)
        success = await self.unmount_server(change.name)
        if not success:
            logger.warning("Failed to remove server: %s", change.name)

    async def _handle_server_update(self, change: ServerChange) -> None:
        """Handle updating a server (requires unmount and remount)."""
        logger.info("Updating server: %s", change.name)

        # First unmount the old version
        await self.unmount_server(change.name)

        # Give transports time to clean up
        await asyncio.sleep(0.1)

        # Mount the new version
        if change.new_config:
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to remount updated server: %s", change.name)

    async def _handle_server_enable(self, change: ServerChange) -> None:
        """Handle enabling a server."""
        if change.new_config:
            logger.info("Enabling server: %s", change.name)
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to enable server: %s", change.name)
            else:
                logger.info("Successfully enabled server: %s", change.name)

    async def _handle_server_disable(self, change: ServerChange) -> None:
        """Handle disabling a server."""
        logger.info("Disabling server: %s", change.name)
        # If server is not mounted, that's fine - it's already in the desired state
        if change.name not in self.mounted_servers:
            logger.info("Server %s is already unmounted", change.name)
        else:
            success = await self.unmount_server(change.name)
            if not success:
                logger.warning("Failed to disable server: %s", change.name)


class ManagedServer:
    server_manager: ServerManager
    _enable_config_reload: bool | None
    _is_setup = False

    def __init__(self, server_manager: ServerManager, *, enable_config_reload: bool | None = None):
        self.server_manager = server_manager
        self._enable_config_reload = enable_config_reload
        self._register_tools()

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

    def _register_tools(self):
        pass

    def save_config(self, config: MaggConfig):
        """Save the current configuration to disk."""
        return self.server_manager.save_config(config)

    @property
    def is_setup(self) -> bool:
        """Check if the server is fully set up with tools and resources."""
        return self._is_setup

    # ============================================================================
    # endregion
    # region MCP Server Management - Setup and Run Methods
    # ============================================================================

    async def __aenter__(self):
        """Enter the context manager, setting up the server."""
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit the context manager, performing any necessary cleanup."""
        # Stop config reloader if running
        await self.server_manager.config_manager.stop_config_reload()

        # Unmount all servers to clean up clients
        mounted_servers = list(self.server_manager.mounted_servers.keys())
        for server_name in mounted_servers:
            await self.server_manager.unmount_server(server_name)

    async def setup(self):
        """Initialize Magg and mount existing servers.

        This is called automatically by run_stdio() and run_http().
        For in-memory usage via FastMCPTransport, call this manually:

            server = MaggServer()
            await server.setup()
            client = Client(FastMCPTransport(server.mcp))

            OR

            (server task)
            async with server:
                await server.run_http()

            (client task, after server start)
            client = Client(FastMCPTransport(server.mcp))
        """
        if not self._is_setup:
            self._is_setup = True
            await self.server_manager.mount_all_enabled()

            # Start config file watcher if enabled
            if self._enable_config_reload:
                await self.server_manager.config_manager.setup_config_reload(
                    self.server_manager.handle_config_reload
                )

    async def run_stdio(self):
        """Run Magg in stdio mode."""
        await self.setup()
        await self.mcp.run_stdio_async()

    async def run_http(self, host: str = "localhost", port: int = 8000, log_level: str = "CRITICAL"):
        """Run Magg in HTTP mode."""
        await self.setup()
        await self.mcp.run_http_async(host=host, port=port, log_level=log_level)

    async def reload_config(self) -> bool:
        """Manually trigger a configuration reload.

        Returns:
            True if reload was successful, False otherwise
        """
        # First ensure reload is setup
        if not self._enable_config_reload:
            await self.server_manager.config_manager.setup_config_reload(
                self.server_manager.handle_config_reload
            )

        return await self.server_manager.config_manager.reload_config()

    # ============================================================================
    # endregion
    # ============================================================================
