"""Message handling for Magg MCP aggregation.

This module provides message handlers and coordination for routing notifications
and requests between clients and multiple backend MCP servers.
"""
import asyncio
from typing import Any, Callable
import logging

import mcp.types
from fastmcp.client.messages import MessageHandler

logger = logging.getLogger(__name__)

__all__ = [
    "MaggMessageHandler",
    "MessageRouter",
    "ServerMessageCoordinator",
]


class MessageRouter:
    """Routes messages between clients and backend servers with support for aggregation."""

    def __init__(self):
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._global_handlers: list[MessageHandler] = []
        self._lock = asyncio.Lock()

    async def register_handler(
        self,
        handler: MessageHandler,
        server_id: str | None = None
    ) -> None:
        """Register a message handler for a specific server or globally.

        Args:
            handler: Message handler to register
            server_id: Optional server ID to filter messages for this handler.
                      If None, handler receives all messages.
        """
        async with self._lock:
            if server_id is None:
                self._global_handlers.append(handler)
            else:
                if server_id not in self._handlers:
                    self._handlers[server_id] = []
                self._handlers[server_id].append(handler)

    async def unregister_handler(
        self,
        handler: MessageHandler,
        server_id: str | None = None
    ) -> None:
        """Unregister a message handler."""
        async with self._lock:
            try:
                if server_id is None:
                    self._global_handlers.remove(handler)
                else:
                    if server_id in self._handlers:
                        self._handlers[server_id].remove(handler)
                        if not self._handlers[server_id]:
                            del self._handlers[server_id]
            except ValueError:
                pass

    async def route_message(
        self,
        message: Any,
        server_id: str | None = None
    ) -> None:
        """Route a message to appropriate handlers.

        Args:
            message: Message to route
            server_id: Optional server ID that generated the message
        """
        async with self._lock:
            handlers_to_call = self._global_handlers.copy()

            if server_id and server_id in self._handlers:
                handlers_to_call.extend(self._handlers[server_id])

        if handlers_to_call:
            await asyncio.gather(
                *[handler(message) for handler in handlers_to_call],
                return_exceptions=True
            )


class ServerMessageCoordinator:
    """Coordinates messages from multiple backend servers."""

    def __init__(self, router: MessageRouter):
        self.router = router
        self._notification_state: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def handle_tool_list_changed(
        self,
        notification: mcp.types.ToolListChangedNotification,
        server_id: str
    ) -> None:
        """Handle tool list change from a specific server."""
        async with self._lock:
            self._notification_state.setdefault("tool_changes", set()).add(server_id)

            # Wrap in ServerNotification for proper MessageHandler dispatch
            server_notification = mcp.types.ServerNotification(root=notification)

            # For now, forward all tool list changes immediately
            # Future: could implement debouncing/aggregation logic here
            await self.router.route_message(server_notification, server_id)

    async def handle_resource_list_changed(
        self,
        notification: mcp.types.ResourceListChangedNotification,
        server_id: str
    ) -> None:
        """Handle resource list change from a specific server."""
        async with self._lock:
            self._notification_state.setdefault("resource_changes", set()).add(server_id)
            server_notification = mcp.types.ServerNotification(root=notification)
            await self.router.route_message(server_notification, server_id)

    async def handle_prompt_list_changed(
        self,
        notification: mcp.types.PromptListChangedNotification,
        server_id: str
    ) -> None:
        """Handle prompt list change from a specific server."""
        async with self._lock:
            self._notification_state.setdefault("prompt_changes", set()).add(server_id)
            server_notification = mcp.types.ServerNotification(root=notification)
            await self.router.route_message(server_notification, server_id)

    async def handle_progress(
        self,
        notification: mcp.types.ProgressNotification,
        server_id: str
    ) -> None:
        """Handle progress notification from a specific server."""
        # Progress notifications don't need aggregation, forward immediately
        server_notification = mcp.types.ServerNotification(root=notification)
        await self.router.route_message(server_notification, server_id)

    async def handle_logging_message(
        self,
        notification: mcp.types.LoggingMessageNotification,
        server_id: str
    ) -> None:
        """Handle logging message from a specific server."""
        # Log messages don't need aggregation, forward immediately
        server_notification = mcp.types.ServerNotification(root=notification)
        await self.router.route_message(server_notification, server_id)

    async def get_notification_state(self) -> dict[str, Any]:
        """Get current notification state for debugging."""
        async with self._lock:
            return self._notification_state.copy()


class MaggMessageHandler(MessageHandler):
    """Magg-specific message handler that coordinates multiple backend servers.

    This handler can be used with MaggClient to receive aggregated notifications
    from all backend MCP servers managed by a Magg instance.
    """

    def __init__(
        self,
        on_tool_list_changed: Callable[[mcp.types.ToolListChangedNotification], None] | None = None,
        on_resource_list_changed: Callable[[mcp.types.ResourceListChangedNotification], None] | None = None,
        on_prompt_list_changed: Callable[[mcp.types.PromptListChangedNotification], None] | None = None,
        on_progress: Callable[[mcp.types.ProgressNotification], None] | None = None,
        on_logging_message: Callable[[mcp.types.LoggingMessageNotification], None] | None = None,
        on_message: Callable[[Any], None] | None = None,
    ):
        """Initialize the Magg message handler.

        Args:
            on_tool_list_changed: Callback for tool list change notifications
            on_resource_list_changed: Callback for resource list change notifications
            on_prompt_list_changed: Callback for prompt list change notifications
            on_progress: Callback for progress notifications
            on_logging_message: Callback for logging notifications
            on_message: Callback for all messages (called first)
        """
        super().__init__()
        self._on_tool_list_changed = on_tool_list_changed
        self._on_resource_list_changed = on_resource_list_changed
        self._on_prompt_list_changed = on_prompt_list_changed
        self._on_progress = on_progress
        self._on_logging_message = on_logging_message
        self._on_message = on_message

    async def on_message(self, message: Any) -> None:
        """Handle all messages - called before specific handlers."""
        if self._on_message:
            try:
                result = self._on_message(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in message handler: %s", e)

    async def on_tool_list_changed(
        self,
        notification: mcp.types.ToolListChangedNotification
    ) -> None:
        """Handle tool list changed notification."""
        if self._on_tool_list_changed:
            try:
                result = self._on_tool_list_changed(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in tool list changed handler: %s", e)

    async def on_resource_list_changed(
        self,
        notification: mcp.types.ResourceListChangedNotification
    ) -> None:
        """Handle resource list changed notification."""
        if self._on_resource_list_changed:
            try:
                result = self._on_resource_list_changed(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in resource list changed handler: %s", e)

    async def on_prompt_list_changed(
        self,
        notification: mcp.types.PromptListChangedNotification
    ) -> None:
        """Handle prompt list changed notification."""
        if self._on_prompt_list_changed:
            try:
                result = self._on_prompt_list_changed(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in prompt list changed handler: %s", e)

    async def on_progress(
        self,
        notification: mcp.types.ProgressNotification
    ) -> None:
        """Handle progress notification."""
        if self._on_progress:
            try:
                result = self._on_progress(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in progress handler: %s", e)

    async def on_logging_message(
        self,
        notification: mcp.types.LoggingMessageNotification
    ) -> None:
        """Handle logging message notification."""
        if self._on_logging_message:
            try:
                result = self._on_logging_message(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in logging message handler: %s", e)
