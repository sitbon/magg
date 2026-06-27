"""MCP proxy tool, making it easier to work with proxied MCP capabilities."""

from .client import ProxyClient
from .mixin import ProxyMCP
from .server import ProxyFastMCP

__all__ = (
    "ProxyMCP",
    "ProxyClient",
    "ProxyFastMCP",
)
