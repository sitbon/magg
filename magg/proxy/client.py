"""Proxy-aware FastMCP client wrapper.

This module provides a FastMCP client wrapper that simplifies interaction with
Magg's proxy tool, making it easier to work with proxied MCP capabilities.
"""
import datetime
from typing import Any

from fastmcp import Client
from fastmcp.client.progress import ProgressHandler
from mcp.types import (
    Tool, Resource, Prompt,
    TextContent, ImageContent, EmbeddedResource,
    GetPromptResult, TextResourceContents, BlobResourceContents, ResourceTemplate
)

from .mixin import ProxyMCP
from .types import LiteralProxyType, LiteralProxyAction
from ..util.transform import tool_result_as_prompt_result, tool_result_as_resource_result

__all__ = "ProxyClient",


class ProxyClient(Client):
    """FastMCP client with proxy-aware convenience methods.

    This client wrapper provides:
    - Natural proxy() method for calling the proxy tool
    - Automatic result decoding for proxy responses
    - Transparent mode for redirecting standard operations through proxy
    """

    def __init__(
        self,
        *args,
        transparent: bool = False,
        proxy_tool_name: str | None = None,
        **kwds
    ):
        """Initialize the proxy client.

        Args:
            *args: Positional arguments for FastMCP Client
            transparent: If True, override standard methods to use proxy
            proxy_tool_name: Name of the proxy tool to use (default: ProxyMCP.PROXY_TOOL_NAME)
            **kwds: Keyword arguments for FastMCP Client
        """
        super().__init__(*args, **kwds)
        self._transparent = transparent
        self._proxy_tool_name = proxy_tool_name or ProxyMCP.PROXY_TOOL_NAME

    async def proxy(
        self,
        proxy_type: LiteralProxyType,
        action: LiteralProxyAction,
        path: str | None = None,
        arguments: dict[str, Any] | None = None,
        timeout: datetime.timedelta | float | int | None = None,
        progress_handler: ProgressHandler | None = None,
    ) -> Any:
        """Call the proxy tool with natural parameter structure.

        Args:
            proxy_type: Type of capability (tool, resource, prompt)
            action: Action to perform (list, info, call)
            path: Name/URI of specific capability (required for info/call)
            arguments: Additional arguments for the action (optional)
            timeout: Optional timeout for the operation
            progress_handler: Optional progress handler for async operations

        Returns:
            Raw proxy tool result - caller knows what to expect based on action/type

        Raises:
            ValueError: If parameters are invalid
        """
        ProxyMCP.validate_operation(action=action, a_type=proxy_type)

        if action in frozenset({"info", "call"}) and not path:
            raise ValueError(f"path is required for action '{action}'")

        if action == "list" and path:
            raise ValueError("path should not be provided for 'list' action")

        proxy_args: dict[str, Any] = {
            "action": action,
            "type": proxy_type,
        }

        if path:
            proxy_args["path"] = path

        if arguments:
            proxy_args["args"] = arguments

        return await super().call_tool(
            self._proxy_tool_name,
            arguments=proxy_args,
            timeout=timeout,
            progress_handler=progress_handler,
        )

    async def list_tools(self) -> list[Tool]:
        """List tools through the proxy (in transparent mode)."""
        return await self._list_for("tool")

    async def list_resources(self) -> list[Resource | ResourceTemplate]:
        """List resources through the proxy (in transparent mode).

        NOTE: The proxy tool returns BOTH resources and resource templates together,
        unlike the client. This may be addressed in the future.
        """
        return await self._list_for("resource")

    async def list_prompts(self) -> list[Prompt]:
        """List prompts through the proxy (in transparent mode)."""
        return await self._list_for("prompt")

    async def _list_for(
            self,
            proxy_type: LiteralProxyType,
    ) -> list[Tool] | list[Resource | ResourceTemplate] | list[Prompt]:
        """List `proxy_type` through the proxy (in transparent mode).
        """
        if not self._transparent:
            super_method = f"list_{proxy_type}"
            return await getattr(super(), super_method)()

        result = await self.proxy(proxy_type=proxy_type, action="list")

        if not result:
            return []

        if len(result) != 1:
            raise ValueError(f"Expected single proxied prompt result, got {len(result)} items")

        response = ProxyMCP.get_proxy_query_result(result[0])

        if response is None:
            raise ValueError(f"Invalid proxied {proxy_type} result item: {result[0]!r}")

        return response

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: datetime.timedelta | float | int | None = None,
        progress_handler: ProgressHandler | None = None,
    ) -> list[TextContent | ImageContent | EmbeddedResource]:
        """Call a tool through the proxy (in transparent mode)."""
        if not self._transparent:
            return await super().call_tool(
                name,
                arguments=arguments,
                timeout=timeout,
                progress_handler=progress_handler
            )

        result = await self.proxy(
            "tool", "call",
            path=name,
            arguments=arguments,
            timeout=timeout,
            progress_handler=progress_handler,
        )

        return result

    async def read_resource(
        self,
        uri: str
    ) -> list[TextResourceContents | BlobResourceContents]:
        """Read a resource through the proxy (in transparent mode)."""
        if not self._transparent:
            return await super().read_resource(uri)

        result = await self.proxy(proxy_type="resource", action="call", path=uri)

        response = []

        for item in result:
            decoded = tool_result_as_resource_result(item)

            if decoded is None:
                raise ValueError(f"Invalid proxied resource result item: {item!r}")

            response.append(decoded)

        return response

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None
    ) -> GetPromptResult:
        """Get a prompt through the proxy (in transparent mode)."""
        if not self._transparent:
            return await super().get_prompt(name, arguments)

        result = await self.proxy("prompt", "call", name, **(arguments or {}))

        if len(result) != 1:
            raise ValueError(f"Expected single proxied prompt result, got {len(result)} items")

        result = result[0]
        response = tool_result_as_prompt_result(result)

        if response is None:
            raise ValueError(f"Invalid proxied prompt result item: {result!r}")

        return response
