"""Magg server ProxyMCP mixin.
"""
from functools import cached_property

from fastmcp import FastMCP, Client
from fastmcp.client import FastMCPTransport
from fastmcp.tools import FunctionTool

from .mixin import ProxyMCP

__all__ = "ProxyFastMCP",


class ProxyFastMCP(ProxyMCP, FastMCP):
    """FastMCP server with ProxyMCP capabilities."""

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
