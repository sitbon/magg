"""Server management for Magg - mounting, unmounting, and tracking MCP servers.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from functools import cached_property
from typing import Annotated

from fastmcp import FastMCP, Client
from pydantic import Field

from .defaults import MAGG_INSTRUCTIONS
from .response import MaggResponse
from ..auth import BearerAuthManager
from ..kit import KitManager
from ..proxy.server import ProxyFastMCP, BackendMessageHandler
from ..reload import ConfigChange, ServerChange
from ..settings import ConfigManager, MaggConfig, ServerConfig
from ..util.stdio_patch import patch_stdio_transport_stderr
from ..util.transport import get_transport_for_command, get_transport_for_uri

logger = logging.getLogger(__name__)


@dataclass
class MountedServer:
    """Information about a mounted MCP server."""
    proxy: FastMCP
    client: Client


class ServerManager:
    """Manages MCP servers - mounting, unmounting, and tracking."""
    config_manager: ConfigManager
    mcp: ProxyFastMCP
    mounted_servers: dict[str, MountedServer]
    subprocess_env: dict | None = None

    def __init__(self, config_manager: ConfigManager, *, env: dict | None = None):
        self.config_manager = config_manager
        self.subprocess_env = env.copy() if env else None

        auth_config = config_manager.load_auth_config()
        auth_provider = None

        if auth_config.bearer.private_key_exists:
            auth_manager = BearerAuthManager(auth_config.bearer)
            try:
                auth_provider = auth_manager.provider
                logger.debug("Authentication enabled (bearer)")
            except RuntimeError as e:
                logger.warning("Authentication disabled: %s", e)

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
        return self.config.prefix_sep

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this Magg server - cannot be changed during process lifetime."""
        return self.config.self_prefix

    async def mount_server(self, server: ServerConfig) -> bool:
        """Mount a server using FastMCP."""
        logger.debug("Attempting to mount server %s (enabled=%s)", server.name, server.enabled)

        if not server.enabled:
            logger.debug("Server %s is disabled, skipping mount", server.name)
            return False

        if server.name in self.mounted_servers:
            logger.warning("Server %s is already mounted, skipping", server.name)
            return False

        try:
            message_handler = BackendMessageHandler(
                server_id=server.name,
                coordinator=self.mcp.message_coordinator
            )

            if server.command:
                env = None

                if server.env or self.subprocess_env:
                    env = {}

                    if server.env:
                        env.update(server.env)

                    if self.subprocess_env:
                        env.update(self.subprocess_env)

                transport = get_transport_for_command(
                    command=server.command,
                    args=server.args or [],
                    env=env,
                    cwd=server.cwd,
                    transport_config=server.transport
                )

                if not self.config.stderr_show:
                    transport = patch_stdio_transport_stderr(transport)

                client = Client(transport, message_handler=message_handler)

            elif server.uri:
                transport = get_transport_for_uri(
                    uri=server.uri,
                    transport_config=server.transport
                )

                client = Client(transport, message_handler=message_handler)

            else:
                logger.error("No command or URI specified for %s", server.name)
                return False

            proxy_server = FastMCP.as_proxy(client, name=server.name)
            self.mcp.mount(server=proxy_server, prefix=server.prefix)

            self.mounted_servers[server.name] = MountedServer(
                proxy=proxy_server,
                client=client
            )

            logger.debug("Mounted server %s with prefix %r", server.name, server.prefix)
            return True

        except Exception as e:
            logger.error("Failed to mount server %s: %s", server.name, e)
            return False

    def _unmount_from_fastmcp(self, server_name: str) -> bool:
        """Remove a mounted server from FastMCP's internal structures.

        This is a workaround until FastMCP provides an official unmount method.
        Returns True if server was found and removed.
        """
        # We need to find and remove the MountedServer object from all managers
        found = False

        # Check tool manager
        if hasattr(self.mcp, '_tool_manager') and hasattr(self.mcp._tool_manager, '_mounted_servers'):
            mounted_servers = self.mcp._tool_manager._mounted_servers
            for i, ms in enumerate(mounted_servers):
                if hasattr(ms, 'server') and hasattr(ms.server, 'name') and ms.server.name == server_name:
                    mounted_servers.pop(i)
                    found = True
                    logger.debug("Removed server %s from tool manager", server_name)
                    break

        # Check resource manager
        if hasattr(self.mcp, '_resource_manager') and hasattr(self.mcp._resource_manager, '_mounted_servers'):
            mounted_servers = self.mcp._resource_manager._mounted_servers
            for i, ms in enumerate(mounted_servers):
                if hasattr(ms, 'server') and hasattr(ms.server, 'name') and ms.server.name == server_name:
                    mounted_servers.pop(i)
                    found = True
                    logger.debug("Removed server %s from resource manager", server_name)
                    break

        # Check prompt manager
        if hasattr(self.mcp, '_prompt_manager') and hasattr(self.mcp._prompt_manager, '_mounted_servers'):
            mounted_servers = self.mcp._prompt_manager._mounted_servers
            for i, ms in enumerate(mounted_servers):
                if hasattr(ms, 'server') and hasattr(ms.server, 'name') and ms.server.name == server_name:
                    mounted_servers.pop(i)
                    found = True
                    logger.debug("Removed server %s from prompt manager", server_name)
                    break

        return found

    async def unmount_server(self, name: str) -> bool:
        """Unmount a server."""
        if name in self.mounted_servers:
            unmounted = self._unmount_from_fastmcp(name)
            if unmounted:
                logger.debug("Unmounted server %s from FastMCP", name)
            else:
                logger.debug("Server %s was not found in FastMCP's mounted servers", name)

            server_info = self.mounted_servers.get(name)
            if server_info and server_info.client:
                try:
                    await server_info.client.close()
                    logger.debug("Closed client for server %s", name)
                except Exception as e:
                    logger.warning("Error closing client for server %s: %s", name, e)

            del self.mounted_servers[name]
            logger.debug("Unmounted server %s", name)
            return True

        else:
            logger.warning("Server %s is not mounted, cannot unmount", name)
            return False

    async def mount_all_enabled(self):
        """Mount all enabled servers from config."""
        config = self.config
        enabled_servers = config.get_enabled_servers()

        if not enabled_servers:
            logger.debug("No enabled servers to mount")
            return

        logger.debug("Mounting %d enabled servers...", len(enabled_servers))

        results = []
        for name, server in enabled_servers.items():
            try:
                success = await self.mount_server(server)
                results.append((name, success))
            except Exception as e:
                logger.error("Error mounting %s: %s", name, e)
                results.append((name, False))

        successful = [name for name, success in results if success]
        failed = [name for name, success in results if not success]

        if successful:
            logger.debug("Successfully mounted: %s", ', '.join(successful))
        if failed:
            logger.warning("Failed to mount: %s", ', '.join(failed))

    async def handle_config_reload(self, config_change: ConfigChange) -> None:
        """Handle configuration changes by applying server updates.

        Args:
            config_change: The configuration change object with old/new configs and changes
        """
        logger.debug("Applying configuration changes...")

        # Process changes in order: remove, disable, update, enable, add
        # This ensures clean transitions

        for change in config_change.server_changes:
            if change.action == 'remove':
                await self._handle_server_remove(change)

        for change in config_change.server_changes:
            if change.action == 'disable':
                await self._handle_server_disable(change)

        for change in config_change.server_changes:
            if change.action == 'update':
                await self._handle_server_update(change)

        for change in config_change.server_changes:
            if change.action == 'enable':
                await self._handle_server_enable(change)

        for change in config_change.server_changes:
            if change.action == 'add':
                await self._handle_server_add(change)

        logger.debug("Configuration reload complete")

    async def _handle_server_add(self, change: ServerChange) -> None:
        """Handle adding a new server."""
        if change.new_config:
            logger.debug("Adding new server: %s", change.name)
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to add server: %s", change.name)

    async def _handle_server_remove(self, change: ServerChange) -> None:
        """Handle removing a server."""
        logger.debug("Removing server: %s", change.name)
        success = await self.unmount_server(change.name)
        if not success:
            logger.warning("Failed to remove server: %s", change.name)

    async def _handle_server_update(self, change: ServerChange) -> None:
        """Handle updating a server (requires unmount and remount)."""
        logger.debug("Updating server: %s", change.name)

        await self.unmount_server(change.name)

        # Give transports time to clean up
        await asyncio.sleep(0.1)

        if change.new_config:
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to remount updated server: %s", change.name)

    async def _handle_server_enable(self, change: ServerChange) -> None:
        """Handle enabling a server."""
        if change.new_config:
            logger.debug("Enabling server: %s", change.name)
            success = await self.mount_server(change.new_config)
            if not success:
                logger.error("Failed to enable server: %s", change.name)
            else:
                logger.debug("Successfully enabled server: %s", change.name)

    async def _handle_server_disable(self, change: ServerChange) -> None:
        """Handle disabling a server."""
        logger.debug("Disabling server: %s", change.name)
        # If server is not mounted, that's fine - it's already in the desired state
        if change.name not in self.mounted_servers:
            logger.debug("Server %s is already unmounted", change.name)
        else:
            success = await self.unmount_server(change.name)
            if not success:
                logger.warning("Failed to disable server: %s", change.name)


class ManagedServer:
    kit_manager: KitManager
    server_manager: ServerManager
    _enable_config_reload: bool | None
    _is_setup = False

    def __init__(self, server_manager: ServerManager, *, enable_config_reload: bool | None = None):
        self.server_manager = server_manager

        config = server_manager.config_manager.load_config()

        if enable_config_reload is None:
            enable_config_reload = config.auto_reload

        self._enable_config_reload = enable_config_reload

        self.kit_manager = KitManager(server_manager.config_manager)
        self.kit_manager.load_kits_from_config(config)

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
        """self_prefix with trailing separator if prefix exists.
        """
        prefix = self.self_prefix
        if prefix:
            return f"{prefix}{self.server_manager.prefix_separator}"
        return ""

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
        await self.server_manager.config_manager.stop_config_reload()

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

            if self._enable_config_reload:
                await self.server_manager.config_manager.setup_config_reload(
                    self.server_manager.handle_config_reload
                )

    async def run_stdio(self):
        """Run Magg in stdio mode.
        """
        await self.setup()
        await self.mcp.run_stdio_async(show_banner=False)

    async def run_http(self, host: str = "localhost", port: int = 8000, log_level: str | None = None):
        """Run Magg in HTTP mode.
        """
        log_level = log_level or os.getenv("FASTMCP_LOG_LEVEL", "CRITICAL").upper() or "CRITICAL"
        await self.setup()
        await self.mcp.run_http_async(host=host, port=port, log_level=log_level, show_banner=False)

    async def run_hybrid(self, host: str = "localhost", port: int = 8000, log_level: str | None = None):
        """Run Magg in hybrid mode - both stdio and HTTP simultaneously.
        """
        log_level = log_level or os.getenv("FASTMCP_LOG_LEVEL", "CRITICAL").upper() or "CRITICAL"

        await self.setup()

        http_task = asyncio.create_task(
            self.mcp.run_http_async(host=host, port=port, log_level=log_level, show_banner=False)
        )

        stdio_task = asyncio.create_task(
            self.mcp.run_stdio_async(show_banner=False)
        )

        try:
            done, pending = await asyncio.wait(
                [http_task, stdio_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            for task in done:
                if task.exception():
                    raise task.exception()

        except Exception:
            http_task.cancel()
            stdio_task.cancel()
            await asyncio.gather(http_task, stdio_task, return_exceptions=True)
            raise

    async def reload_config(self) -> bool:
        """Manually trigger a configuration reload.

        Returns:
            True if reload was successful, False otherwise
        """
        if not self._enable_config_reload:
            await self.server_manager.config_manager.setup_config_reload(
                self.server_manager.handle_config_reload
            )

        return await self.server_manager.config_manager.reload_config()

    # ============================================================================
    # endregion
    # ============================================================================


    # ============================================================================
    # region Kit Management Tools
    # ============================================================================

    async def load_kit(
            self,
            name: Annotated[str, Field(description="Kit name to load (filename without .json)")],
    ) -> MaggResponse:
        """Load a kit and its servers into the configuration."""
        try:
            config = self.config
            success, message = self.kit_manager.load_kit_to_config(name, config)

            if success:
                if not self.save_config(config):
                    return MaggResponse.error("Failed to save configuration")

                for server_name, server in config.servers.items():
                    if server.enabled and server_name not in self.server_manager.mounted_servers:
                        await self.server_manager.mount_server(server)

                return MaggResponse.success({
                    "action": "kit_loaded",
                    "kit": name,
                    "message": message
                })
            else:
                return MaggResponse.error(message)

        except Exception as e:
            return MaggResponse.error(f"Failed to load kit: {str(e)}")

    async def unload_kit(
            self,
            name: Annotated[str, Field(description="Kit name to unload")],
    ) -> MaggResponse:
        """Unload a kit and optionally its servers from the configuration."""
        try:
            config = self.config

            servers_before = set(config.servers.keys())

            success, message = self.kit_manager.unload_kit_from_config(name, config)

            if success:
                if not self.save_config(config):
                    return MaggResponse.error("Failed to save configuration")
                servers_after = set(config.servers.keys())
                removed_servers = servers_before - servers_after

                for server_name in removed_servers:
                    if server_name in self.server_manager.mounted_servers:
                        await self.server_manager.unmount_server(server_name)

                return MaggResponse.success({
                    "action": "kit_unloaded",
                    "kit": name,
                    "message": message
                })
            else:
                return MaggResponse.error(message)

        except Exception as e:
            return MaggResponse.error(f"Failed to unload kit: {str(e)}")

    async def list_kits(self) -> MaggResponse:
        """List all available kits with their status."""
        try:
            kits = self.kit_manager.list_all_kits()

            return MaggResponse.success({
                "kits": kits,
                "summary": {
                    "total": len(kits),
                    "loaded": len([k for k in kits.values() if k['loaded']]),
                    "available": len([k for k in kits.values() if not k['loaded']])
                }
            })

        except Exception as e:
            return MaggResponse.error(f"Failed to list kits: {str(e)}")

    async def kit_info(
            self,
            name: Annotated[str, Field(description="Kit name to get information about")],
    ) -> MaggResponse:
        """Get detailed information about a specific kit."""
        try:
            info = self.kit_manager.get_kit_details(name)

            if info:
                return MaggResponse.success(info)
            else:
                return MaggResponse.error(f"Kit '{name}' not found")

        except Exception as e:
            return MaggResponse.error(f"Failed to get kit info: {str(e)}")

    # ============================================================================
    # endregion
    # region Kit Resources - Kit configurations suitable for saving as JSON files
    # ============================================================================

    async def get_kit_metadata(self, name: str) -> dict:
        """Expose kit metadata as an MCP resource suitable for saving as a kit file.

        Only returns kits that are currently loaded in memory.
        """
        loaded_kits = self.kit_manager.kits

        if name not in loaded_kits:
            raise ValueError(f"Kit '{name}' not found in loaded kits")

        kit_config = loaded_kits[name]

        return kit_config.model_dump(
            mode="json",
            exclude_none=True,
            exclude_defaults=True,
            exclude_unset=True,
            by_alias=True
        )

    async def get_all_kits_metadata(self) -> dict[str, dict]:
        """Expose all loaded kits metadata as an MCP resource.

        Only returns kits that are currently loaded in memory.
        """
        result = {}

        for kit_name, kit_config in self.kit_manager.kits.items():
            result[kit_name] = kit_config.model_dump(
                mode="json",
                exclude_none=True,
                exclude_defaults=True,
                exclude_unset=True,
                by_alias=True
            )

        return result

    # ============================================================================
    # endregion
    # ============================================================================
