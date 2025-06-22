"""ProxyMCP - Mixin for dynamic MCP server access.
"""
import logging
from typing import Any, Literal, Annotated, Callable, ClassVar, Self

from fastmcp.client import Client, FastMCPTransport
from mcp.types import Tool, Resource, Prompt, EmbeddedResource, ResourceTemplate, Annotations
from pydantic import Field, BaseModel

from .manager import ManagedServer
from ..util.transform import resource_result_as_tool_result, prompt_result_as_tool_result, annotate_content, \
    embed_python_object_list_in_resource, embed_python_object_in_resource, embedded_resource_python_object, \
    deserialize_embedded_resource_python_object

__all__ = (
    "LiteralProxyType",
    "LiteralProxyAction",
    "ProxyResponseInfo",
    "ProxyMCP",
)

LOG = logging.getLogger(__name__)

LiteralProxyType = Literal["tool", "resource", "prompt"]
LiteralProxyAction = Literal["list", "info", "call"]


class ProxyResponseInfo(BaseModel):
    """Metadata for proxy tool responses, pulled from annotations.

    Note that this info cannot always be retrieved, e.g., for empty results.

    It is mostly useful for introspection and debugging, and identifying
    query-typed results (list, info) that can be further processed by the client.
    """
    proxy_type: LiteralProxyType | None = Field(
        None,
        description="Type of the proxied capability (tool, resource, prompt).",
    )
    proxy_action: LiteralProxyAction | None = Field(
        None,
        description="Action performed by the proxy (list, info, call).",
    )
    proxy_path: str | None = Field(
        None,
        description="Name or URI of the specific tool/resource/prompt (with FastMCP prefixing).",
    )

    @classmethod
    def from_annotations(cls, annotations: Annotations) -> Self:
        """Create ProxyResponseInfo from Annotations."""
        return cls(
            proxy_type=getattr(annotations, "proxyType", None),
            proxy_action=getattr(annotations, "proxyAction", None),
            proxy_path=getattr(annotations, "proxyPath", None),
        )


class ProxyMCP(ManagedServer):
    """Mixin that provides proxy functionality for accessing mounted MCP servers.

    This mixin expects the host class to have a `server_manager` attribute
    that provides access to mounted servers and their clients.
    """
    _self_client: Client | None = None
    """Client connected to our own FastMCP server for introspection."""

    PROXY_TYPE_MAP: ClassVar[dict[str, type[BaseModel]]] = {
        "tool": Tool,
        "resource": Resource | ResourceTemplate,
        "prompt": Prompt,
    }

    PROXY_TOOL_NAME: ClassVar[str] = "proxy"

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

        if object_info := embedded_resource_python_object(result):
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

    def _register_proxy_tool(self, wrapper: Callable | None = None) -> None:
        """Register the proxy tool with the MCP server.

        This should be called by the host class after initialization.
        """
        # Access the mcp instance through server_manager
        self.server_manager.mcp.tool(name=self.PROXY_TOOL_NAME)(
            self._proxy_tool if wrapper is None else wrapper(self._proxy_tool)
        )

    async def _get_self_client(self) -> Client:
        """Get or create a client connected to our own FastMCP server."""
        if self._self_client is None:
            # Create a client that connects to ourselves using FastMCPTransport
            # This allows us to introspect our own capabilities
            transport = FastMCPTransport(self.mcp)
            self._self_client = Client(transport)
        return self._self_client

    # noinspection PyShadowingBuiltins
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

    async def _proxy_list(
            self,
            capability_type: str
    ) -> tuple[list[Tool] | list[Resource | ResourceTemplate] | list[Prompt], type[BaseModel]]:
        """List capabilities by connecting to ourselves as a client.
        """
        client = await self._get_self_client()

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
        client = await self._get_self_client()
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
