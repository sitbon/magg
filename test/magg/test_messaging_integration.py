"""Integration tests for Magg messaging functionality with server mounting."""
import pytest
from unittest.mock import AsyncMock, Mock

import mcp.types
from magg.server.manager import ServerManager
from magg.settings import MaggConfig, ServerConfig
from magg.messaging import MaggMessageHandler


class TestMessagingIntegration:
    """Test messaging integration with server mounting."""

    @pytest.mark.asyncio
    async def test_message_handler_creation_during_mount(self, tmp_path):
        """Test that message handlers are created when mounting servers."""
        from magg.settings import ConfigManager

        # Create config with a test server
        config = MaggConfig(
            servers={
                "test_server": ServerConfig(
                    name="test_server",
                    source="test://local",
                    prefix="test",
                    enabled=True,
                    command="echo",  # Simple command that exists
                    args=["hello"]
                )
            }
        )

        # Create config manager with test config
        config_file = tmp_path / "test_config.yaml"
        config_manager = ConfigManager(config_path=config_file)
        config_manager._cached_config = config  # Bypass file loading

        # Create server manager
        server_manager = ServerManager(config_manager)

        # Verify ProxyFastMCP has message coordinator
        assert hasattr(server_manager.mcp, 'message_coordinator')
        assert server_manager.mcp.message_coordinator is not None

        # Mount the test server
        server_config = config.servers["test_server"]
        result = await server_manager.mount_server(server_config)

        # Verify mounting succeeded
        assert result is True
        assert "test_server" in server_manager.mounted_servers

        # Verify client has message handler (we can't directly test this without
        # starting the actual server, but we can verify the setup doesn't break)
        mounted_server = server_manager.mounted_servers["test_server"]
        assert mounted_server.client is not None

        # Clean up
        await server_manager.unmount_server("test_server")

    @pytest.mark.asyncio
    async def test_message_forwarding_flow(self):
        """Test the complete message forwarding flow."""
        from magg.proxy.server import BackendMessageHandler
        from magg.messaging import MessageRouter, ServerMessageCoordinator

        # Set up message routing infrastructure
        router = MessageRouter()
        coordinator = ServerMessageCoordinator(router)

        # Create backend handler
        backend_handler = BackendMessageHandler("test_server", coordinator)

        # Set up client message handler mock
        client_handler = AsyncMock()
        await router.register_handler(client_handler, server_id=None)

        # Simulate a tool list changed notification
        notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )

        # Send through backend handler
        await backend_handler.on_tool_list_changed(notification)

        # Verify client handler was called with wrapped notification
        assert client_handler.call_count == 1
        called_message = client_handler.call_args[0][0]
        assert isinstance(called_message, mcp.types.ServerNotification)
        assert called_message.root == notification

    @pytest.mark.asyncio
    async def test_magg_client_with_message_handler(self):
        """Test MaggClient with message handler functionality."""
        from magg import MaggClient, MaggMessageHandler
        from fastmcp.client.transports import FastMCPTransport
        from fastmcp import FastMCP

        # Create a test FastMCP server
        test_server = FastMCP(name="test")

        # Create transport that connects to the test server
        transport = FastMCPTransport(test_server)

        # Create message handler
        callback_mock = AsyncMock()
        handler = MaggMessageHandler(
            on_tool_list_changed=callback_mock
        )

        # Create MaggClient with message handler
        client = MaggClient(transport, message_handler=handler)

        # Verify client was created successfully
        assert client is not None
        assert hasattr(client, 'settings')

        # Note: We can't easily test the actual message flow without starting
        # real servers, but we can verify the setup doesn't break

    def test_message_handler_backward_compatibility(self):
        """Test that messaging functionality doesn't break existing code."""
        from magg import MaggClient
        from fastmcp.client.transports import FastMCPTransport
        from fastmcp import FastMCP

        # Create a test FastMCP server
        test_server = FastMCP(name="test")

        # Create transport that connects to the test server
        transport = FastMCPTransport(test_server)

        # Create MaggClient WITHOUT message handler (existing usage)
        client = MaggClient(transport)

        # Verify client was created successfully
        assert client is not None
        assert hasattr(client, 'settings')

        # Verify transparent mode is still default
        assert client._transparent is True

    @pytest.mark.asyncio
    async def test_server_mounting_without_messaging(self, tmp_path):
        """Test that server mounting fails gracefully without messaging support."""
        from magg.settings import ConfigManager
        from magg.proxy.mixin import ProxyMCP  # Use base ProxyMCP without messaging
        from fastmcp import FastMCP

        # Create a basic FastMCP server without messaging extensions
        basic_server = FastMCP(name="basic")

        # Verify it doesn't have message_coordinator
        assert not hasattr(basic_server, 'message_coordinator')

        # Create config with a test server
        config = MaggConfig(
            servers={
                "test_server": ServerConfig(
                    name="test_server",
                    source="test://local",
                    prefix="test",
                    enabled=True,
                    command="echo",
                    args=["hello"]
                )
            }
        )

        # Create config manager
        config_file = tmp_path / "test_config.yaml"
        config_manager = ConfigManager(config_path=config_file)
        config_manager._cached_config = config

        # Create server manager with basic server (no messaging)
        server_manager = ServerManager(config_manager)
        server_manager.mcp = basic_server  # Replace with basic server

        # Mount should fail without message coordinator
        server_config = config.servers["test_server"]
        result = await server_manager.mount_server(server_config)
        assert result is False  # Should fail gracefully

        # Verify server was not mounted
        assert "test_server" not in server_manager.mounted_servers
