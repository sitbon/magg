"""MCP proxy tool, making it easier to work with proxied MCP capabilities.
"""
from .mixin import ProxyMCP
from .client import ProxyClient
from .server import ProxyFastMCP

__all__ = (
    "ProxyMCP",
    "ProxyClient",
    "ProxyFastMCP",
)
