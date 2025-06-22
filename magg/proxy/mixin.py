"""ProxyMCP - Mixin for dynamic MCP server access.
"""
import logging
from typing import Any, Annotated, ClassVar

from fastmcp import Client
from mcp.types import Tool, Resource, Prompt, EmbeddedResource, ResourceTemplate
from pydantic import Field, BaseModel

from .types import LiteralProxyType, LiteralProxyAction
from ..util.transform import resource_result_as_tool_result, prompt_result_as_tool_result, annotate_content, \
    embed_python_object_list_in_resource, embed_python_object_in_resource, get_embedded_resource_python_object, \
    deserialize_embedded_resource_python_object

__all__ = (
    "ProxyMCP",
)

logger = logging.getLogger(__name__)


class ProxyMCP:
    """Mixin that provides proxy functionality for accessing mounted MCP servers.

    This mixin expects the host class to implement the `_proxy_backend_client` property,
    which should return a FastMCP Client instance connected to the backend server. The
    host class must also call `_register_proxy_tool` to register the proxy tool function
    with the MCP server.
    """
    PROXY_TYPE_MAP: ClassVar[dict[str, type[BaseModel]]] = {
        "tool": Tool,
        "resource": Resource | ResourceTemplate,
        "prompt": Prompt,
    }

    PROXY_TOOL_NAME: ClassVar[str] = "proxy"

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        logger.debug("Initializing ProxyMCP mixin")
        self._register_proxy_tool()

    @property
    def _proxy_backend_client(self) -> Client:
        """Get the backend (proxied server) client for this proxy.
        """
        raise NotImplementedError("This method should be implemented by the host class.")

    async def _get_proxy_backend_client(self) -> Client:
        """Async wrapper to get the backend client.

        The ProxyMCP mixin uses this method to retrieve the Client,
        in case overriding in an asynchronous context is needed.
        """
        return self._proxy_backend_client

    def _register_proxy_tool(self):
        """Register the `self._proxy_tool` tool function with the MCP server.

        This should be implemented by the host class after initialization.

        Called from ProxyMCP.__init__() to ensure the tool is registered.
        """
        raise NotImplementedError(
            "This method should be implemented by the host class to register the proxy tool."
        )

    async def _proxy_tool(
        self,
        action: Annotated[LiteralProxyAction, Field(
            description="Action to perform: list, info, or call."
        )],
        a_type: Annotated[LiteralProxyType, Field(
            description="Type of MCP capability to interact with: tool, resource, or prompt.",
            alias="type"
        )],
        args: Annotated[dict[str, Any] | None, Field(
            description="Arguments for a 'call' action (call tool, read resource, or get prompt)."
        )] = None,
        path: Annotated[str | None, Field(
            description="Name or URI of the specific tool/resource/prompt (with FastMCP prefixing).\n"
                        "Not allowed for 'list' and 'info' actions.",
            # validation_alias=AliasChoices("name", "uri"),
        )] = None,
    ) -> Any:
        """Main proxy tool for dynamic access to mounted MCP servers.

        This tool provides a unified interface for:
        - Listing available tools, resources, or prompts across servers
        - Getting detailed info about specific capabilities
        - Calling tools, reading resources, or getting prompts

        Annotations are used to provide rich type information for results,
        which can generally be expected to ultimately include JSON-encoded
        EmbeddedResource results that can be interpreted by the client.
        """
        self.validate_operation(action=action, a_type=a_type)

        if action in frozenset({"info", "call"}) and not path:
            raise ValueError(
                f"Parameter 'path' is required for action {action!r}"
            )

        if action in frozenset({"list", "info"}) and args:
            raise ValueError(
                f"Parameter 'args' should not be provided for action {action!r}"
            )

        if action == "list" and path:
            raise ValueError(
                "Parameter 'path' should not be provided for action 'list'"
            )

        if action == "list":
            result, result_type = await self._proxy_list(a_type)

            if result:
                # Send results as a single json/object-encoded EmbeddedResource result
                result = embed_python_object_list_in_resource(
                    typ=result_type,
                    obj=result,
                    uri=f"{self.PROXY_TOOL_NAME}:{action}/{a_type}",
                    proxyAction=action,
                    proxyType=a_type,
                )

        elif action == "info":
            result = await self._proxy_info(a_type, path)

            if result:
                # Send results as a json/object-encoded EmbeddedResource result
                result = embed_python_object_in_resource(
                    obj=result,
                    uri=f"{self.PROXY_TOOL_NAME}:{action}/{a_type}/{path}",
                    proxyAction=action,
                    proxyType=a_type,
                    proxyPath=path,
                )

        elif action == "call":
            result = await self._proxy_call(a_type, path, args or {})
        else:
            raise ValueError(
                f"Unknown action: {action!r}. Supported actions are 'list', 'info', and 'call'."
            )

        return result

    # noinspection PyShadowingBuiltins
    async def _proxy_list(
            self,
            capability_type: str
    ) -> tuple[list[Tool] | list[Resource | ResourceTemplate] | list[Prompt], type[BaseModel]]:
        """List capabilities by connecting to ourselves as a client.
        """
        client = await self._get_proxy_backend_client()

        async with client:
            if capability_type == "tool":
                result = await client.list_tools()
                result_type = Tool
            elif capability_type == "resource":
                result = await client.list_resources()
                result.extend(
                    await client.list_resource_templates()  # type: ignore[return-value]
                )
                result_type = Resource | ResourceTemplate
            elif capability_type == "prompt":
                result = await client.list_prompts()
                result_type = Prompt
            else:
                raise ValueError(f"Unknown capability type: {capability_type}")

        return result, result_type

    async def _proxy_info(self, capability_type: str, name: str) -> Prompt | Tool | Resource | ResourceTemplate:
        """Get detailed info about a specific capability.
        """
        capabilities, _ = await self._proxy_list(capability_type)

        for cap in capabilities:
            if cap.name == name:
                return cap

        raise ValueError(f"{capability_type.capitalize()} '{name}' not found")

    async def _proxy_call(self, capability_type: str, path: str, args: dict[str, Any]) -> Any:
        """Call a tool, read a resource, or get a prompt by connecting to ourselves as a client.
        """
        client = await self._get_proxy_backend_client()

        annotations = {
            "proxyType": capability_type,
            "proxyAction": "call",
            "proxyPath": path,
        }

        async with client:
            if capability_type == "tool":
                result = await client.call_tool(path, args)  # Returns list[TextContent | ImageContent | EmbeddedResource]
                result = [annotate_content(item, **annotations) for item in result]

            elif capability_type == "resource":
                # For resources, the 'path' is the URI
                result = await client.read_resource(path)  # Returns list[TextResourceContents | BlobResourceContents]
                result = [resource_result_as_tool_result(item, **annotations) for item in result]

            elif capability_type == "prompt":
                result = await client.get_prompt(path, args)  # Returns GetPromptResult
                result = prompt_result_as_tool_result(result, f"proxy:{path}", **annotations)

            else:
                raise ValueError(f"Unknown capability type: {capability_type}")

            return result

    @classmethod
    def validate_operation(
        cls,
        action: LiteralProxyAction,
        a_type: LiteralProxyType
    ) -> None:
        """Validate the proxy operation parameters."""
        if action not in frozenset({"list", "info", "call"}):
            raise ValueError(f"Invalid proxy action '{action}'")

        if a_type not in frozenset({"tool", "resource", "prompt"}):
            raise ValueError(f"Invalid proxy type '{a_type}'")

    @classmethod
    def get_proxy_query_result(
            cls,
            result: EmbeddedResource
    ) -> list[Tool] | list[Resource] | list[Prompt] | Tool | Resource | Prompt | None:
        """
        A proxy query is a non-call proxy action: currently only 'list' and 'info'.

        Proxy query results are always returned as a single EmbeddedResource with JSON-encoded text content.

        These results can be further interpreted by the calling code to emulate native MCP behavior,
        for example, using CLI preferences to control tool or prompt list display format.
        """
        decoded = None

        if object_info := get_embedded_resource_python_object(result):
            python_type, json_data, many = object_info
            target_type = getattr(result.annotations, "proxyType", None)
            target_type = cls.PROXY_TYPE_MAP.get(target_type)

            # TODO: More in-depth validation before deserialization
            if target_type and getattr(result.annotations, "proxyAction", None) in {"list", "info"}:

                decoded = deserialize_embedded_resource_python_object(
                    target_type=target_type,
                    python_type=python_type,
                    json_data=json_data,
                    many=many,
                )

        return decoded
