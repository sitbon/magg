"""Tests for Magg messaging and notification system."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

import mcp.types
from magg.messaging import (
    MaggMessageHandler,
    MessageRouter,
    ServerMessageCoordinator,
)
from magg.proxy.server import BackendMessageHandler


class TestMaggMessageHandler:
    """Test MaggMessageHandler functionality."""

    @pytest.mark.asyncio
    async def test_callback_execution(self):
        """Test that callbacks are executed correctly."""
        tool_callback = AsyncMock()
        progress_callback = Mock()

        handler = MaggMessageHandler(
            on_tool_list_changed=tool_callback,
            on_progress=progress_callback
        )

        # Test tool list changed
        notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )
        await handler.on_tool_list_changed(notification)
        tool_callback.assert_called_once_with(notification)

        # Test progress notification
        progress_notif = mcp.types.ProgressNotification(
            method="notifications/progress",
            params=mcp.types.ProgressNotificationParams(
                progressToken="test-token",
                progress=50,
                total=100
            )
        )
        await handler.on_progress(progress_notif)
        progress_callback.assert_called_once_with(progress_notif)

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test that handler errors don't propagate."""
        def failing_callback(notification):
            raise ValueError("Test error")

        handler = MaggMessageHandler(
            on_tool_list_changed=failing_callback
        )

        notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )

        # Should not raise exception
        await handler.on_tool_list_changed(notification)


class TestMessageRouter:
    """Test MessageRouter functionality."""

    @pytest.mark.asyncio
    async def test_handler_registration(self):
        """Test handler registration and routing."""
        router = MessageRouter()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        # Register handlers
        await router.register_handler(handler1, server_id="server1")
        await router.register_handler(handler2, server_id=None)  # Global

        # Route message
        message = "test message"
        await router.route_message(message, server_id="server1")

        # Both handlers should be called
        handler1.assert_called_once_with(message)
        handler2.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_handler_unregistration(self):
        """Test handler unregistration."""
        router = MessageRouter()
        handler = AsyncMock()

        # Register and then unregister
        await router.register_handler(handler, server_id="server1")
        await router.unregister_handler(handler, server_id="server1")

        # Route message - handler should not be called
        await router.route_message("test", server_id="server1")
        handler.assert_not_called()


class TestServerMessageCoordinator:
    """Test ServerMessageCoordinator functionality."""

    @pytest.mark.asyncio
    async def test_notification_tracking(self):
        """Test that notifications are tracked correctly."""
        router = MessageRouter()
        coordinator = ServerMessageCoordinator(router)

        # Handle tool list change
        notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )
        await coordinator.handle_tool_list_changed(notification, "server1")

        # Check state
        state = await coordinator.get_notification_state()
        assert "tool_changes" in state
        assert "server1" in state["tool_changes"]

    @pytest.mark.asyncio
    async def test_message_forwarding(self):
        """Test that messages are forwarded to router."""
        router = Mock()
        router.route_message = AsyncMock()

        coordinator = ServerMessageCoordinator(router)

        notification = mcp.types.ProgressNotification(
            method="notifications/progress",
            params=mcp.types.ProgressNotificationParams(
                progressToken="test-token",
                progress=25
            )
        )

        await coordinator.handle_progress(notification, "server1")

        # Verify the notification was wrapped in ServerNotification
        expected_call = router.route_message.call_args[0]
        assert len(expected_call) == 2
        server_notification, server_id = expected_call
        assert isinstance(server_notification, mcp.types.ServerNotification)
        assert server_notification.root == notification
        assert server_id == "server1"


class TestBackendMessageHandler:
    """Test BackendMessageHandler functionality."""

    @pytest.mark.asyncio
    async def test_notification_forwarding(self):
        """Test that notifications are forwarded to coordinator."""
        coordinator = Mock()
        coordinator.handle_tool_list_changed = AsyncMock()

        handler = BackendMessageHandler("server1", coordinator)

        notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )

        await handler.on_tool_list_changed(notification)

        coordinator.handle_tool_list_changed.assert_called_once_with(
            notification, "server1"
        )


class TestIntegration:
    """Integration tests for the messaging system."""

    @pytest.mark.asyncio
    async def test_end_to_end_flow(self):
        """Test complete message flow from backend to client."""
        # Set up components
        router = MessageRouter()
        coordinator = ServerMessageCoordinator(router)
        backend_handler = BackendMessageHandler("server1", coordinator)

        # Set up client handler with spy
        client_callback = AsyncMock()

        class TestMessageHandler(MaggMessageHandler):
            async def on_tool_list_changed(self, notification):
                await client_callback(notification)

        client_handler = TestMessageHandler()

        # Register client handler
        await router.register_handler(client_handler, server_id=None)

        # Simulate backend notification
        tool_notification = mcp.types.ToolListChangedNotification(
            method="notifications/tools/list_changed"
        )

        # Send through backend handler (this goes to coordinator, then router, then client handler)
        await backend_handler.on_tool_list_changed(tool_notification)

        # Verify client handler was called with the tool notification (not wrapped)
        client_callback.assert_called_once_with(tool_notification)
