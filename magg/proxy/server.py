"""Magg server ProxyMCP mixin.
"""
import asyncio
import logging
from functools import cached_property

from fastmcp import FastMCP, Client
from fastmcp.client import FastMCPTransport
from fastmcp.client.messages import MessageHandler
from fastmcp.tools import FunctionTool
import mcp.types

from .mixin import ProxyMCP
from ..messaging import MessageRouter, ServerMessageCoordinator

logger = logging.getLogger(__name__)

__all__ = "ProxyFastMCP",


class BackendMessageHandler(MessageHandler):
    """Message handler that forwards notifications from backend servers."""

    def __init__(self, server_id: str, coordinator: ServerMessageCoordinator):
        super().__init__()
        self.server_id = server_id
        self.coordinator = coordinator

    async def on_tool_list_changed(
        self,
        notification: mcp.types.ToolListChangedNotification
    ) -> None:
        """Forward tool list changed notification."""
        await self.coordinator.handle_tool_list_changed(notification, self.server_id)

    async def on_resource_list_changed(
        self,
        notification: mcp.types.ResourceListChangedNotification
    ) -> None:
        """Forward resource list changed notification."""
        await self.coordinator.handle_resource_list_changed(notification, self.server_id)

    async def on_prompt_list_changed(
        self,
        notification: mcp.types.PromptListChangedNotification
    ) -> None:
        """Forward prompt list changed notification."""
        await self.coordinator.handle_prompt_list_changed(notification, self.server_id)

    async def on_progress(
        self,
        notification: mcp.types.ProgressNotification
    ) -> None:
        """Forward progress notification."""
        await self.coordinator.handle_progress(notification, self.server_id)

    async def on_logging_message(
        self,
        notification: mcp.types.LoggingMessageNotification
    ) -> None:
        """Forward logging message notification."""
        await self.coordinator.handle_logging_message(notification, self.server_id)


class ProxyFastMCP(ProxyMCP, FastMCP):
    """FastMCP server with ProxyMCP capabilities and message forwarding."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize message routing
        self._message_router = MessageRouter()
        self._message_coordinator = ServerMessageCoordinator(self._message_router)
        self._backend_handlers: dict[str, BackendMessageHandler] = {}

    @cached_property
    def _proxy_backend_client(self) -> Client:
        """Create a client connected to our own FastMCP server. [cached]"""
        # Create a client that connects to ourselves using FastMCPTransport
        # This allows us to introspect our own capabilities
        transport = FastMCPTransport(self)
        return Client(transport)

    def _register_proxy_tool(self):
        tool = FunctionTool.from_function(
            self._proxy_tool,
            name=self.PROXY_TOOL_NAME,
            serializer=self._tool_serializer,
        )

        self.add_tool(tool)

    async def register_client_message_handler(
        self,
        handler: MessageHandler,
        client_id: str | None = None
    ) -> None:
        """Register a message handler for client notifications.

        Args:
            handler: Message handler to register
            client_id: Optional client ID for targeted messaging
        """
        await self._message_router.register_handler(handler, client_id)

    async def unregister_client_message_handler(
        self,
        handler: MessageHandler,
        client_id: str | None = None
    ) -> None:
        """Unregister a client message handler."""
        await self._message_router.unregister_handler(handler, client_id)

    @property
    def message_coordinator(self) -> ServerMessageCoordinator:
        """Access to the message coordinator for debugging/monitoring."""
        return self._message_coordinator
