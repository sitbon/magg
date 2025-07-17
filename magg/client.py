"""Magg FastMCP client wrapper with authentication and proxy support."""
from typing import Any

from fastmcp.client import BearerAuth
from fastmcp.client.messages import MessageHandler, MessageHandlerT
from httpx import Auth

from .proxy.client import ProxyClient
from .settings import ClientSettings
from .messaging import MaggMessageHandler


class MaggClient(ProxyClient):
    """Magg-specific client with authentication and proxy support.

    This client is designed for external code that needs to talk to Magg servers.
    It automatically handles JWT authentication from environment variables and
    provides proxy-aware methods for accessing aggregated MCP capabilities.
    """

    def __init__(
        self,
        transport: Any,
        *args,
        settings: ClientSettings | None = None,
        auth: Auth | str | None = None,
        transparent: bool = True,
        message_handler: MessageHandlerT | None = None,
        **kwds,
    ):
        """Initialize Magg client with JWT authentication and proxy support.

        Args:
            transport: Same as FastMCP Client transport argument
            *args: Additional positional arguments for ProxyClient
            settings: Client settings (defaults to loading from env)
            auth: Override auth (if not provided, uses JWT from settings)
            transparent: Enable transparent proxy mode (default: True for Magg)
            message_handler: Optional message handler for notifications/requests
            **kwds: Additional keyword arguments for ProxyClient/FastMCP Client
        """
        self.settings = settings or ClientSettings()

        if auth is None and self.settings.jwt:
            auth = BearerAuth(self.settings.jwt)

        super().__init__(
            transport,
            *args,
            auth=auth,
            transparent=transparent,
            message_handler=message_handler,
            **kwds
        )
