# MCP Proxy Tool Pattern

The proxy tool pattern enables dynamic access to MCP capabilities through a single, unified tool interface. This pattern is particularly useful for aggregators, gateways, and other scenarios where MCP servers need to expose capabilities from other servers.

## Overview

The proxy tool provides a single entry point for:
- Listing available tools, resources, or prompts across servers
- Getting detailed information about specific capabilities
- Calling tools, reading resources, or getting prompts

This approach simplifies client implementation and enables powerful aggregation scenarios without requiring clients to manage multiple connections.

## Tool Interface

### Parameters

The proxy tool accepts the following parameters:

- **action** (required): `"list"` | `"info"` | `"call"`
  - `list`: List all capabilities of the specified type
  - `info`: Get detailed information about a specific capability
  - `call`: Execute a tool, read a resource, or get a prompt

- **type** (required): `"tool"` | `"resource"` | `"prompt"`
  - Specifies which type of MCP capability to interact with
  - Parameter is aliased as `a_type` in the server implementation to avoid Python keyword conflict

- **path** (optional): string
  - Name or URI of the specific capability
  - Required for `info` and `call` actions
  - Not allowed for `list` action

- **args** (optional): object
  - Arguments to pass when using the `call` action
  - Only allowed for `call` action
  - Not allowed for `list` and `info` actions
  - For tools: tool-specific arguments
  - For resources: typically not used (URI is in path)
  - For prompts: prompt-specific arguments

### Examples

```json
// List all tools
{
  "action": "list",
  "type": "tool"
}

// Get info about a specific tool
{
  "action": "info", 
  "type": "tool",
  "path": "calculator_add"
}

// Call a tool
{
  "action": "call",
  "type": "tool", 
  "path": "calculator_add",
  "args": {"a": 5, "b": 3}
}

// Read a resource
{
  "action": "call",
  "type": "resource",
  "path": "config://settings.json"
}
```

## Response Format

### Query Actions (list/info)

For `list` and `info` actions, the proxy tool returns a list containing a single `EmbeddedResource` with:
- JSON-encoded representation of the MCP objects
- Annotations indicating the proxy context and metadata

Example list response structure:
```python
[
    EmbeddedResource(
        resource=TextResourceContents(
            uri="proxy:list/tool",
            mimeType="application/json",
            text='[{"name": "tool1", "description": "...", ...}]'
        ),
        annotations=Annotations(
            proxyAction="list",
            proxyType="tool",
            pythonType="Tool",  # Or "Resource | ResourceTemplate", "Prompt"
            many=True  # For list actions
        )
    )
]
```

Example info response structure:
```python
[
    EmbeddedResource(
        resource=TextResourceContents(
            uri="proxy:info/tool/calculator_add",
            mimeType="application/json",
            text='{"name": "calculator_add", "description": "...", ...}'
        ),
        annotations=Annotations(
            proxyAction="info",
            proxyType="tool",
            proxyPath="calculator_add",
            pythonType="Tool",
            many=False  # Single object
        )
    )
]
```

### Call Actions

For `call` actions, the proxy tool returns the actual result from the called capability:

- **Tools**: List of `TextContent`, `ImageContent`, or `EmbeddedResource` with proxy annotations
- **Resources**: List of `EmbeddedResource` (resource results converted to tool result format)
- **Prompts**: List with single `EmbeddedResource` containing the prompt result

All call results include annotations with:
- `proxyType`: The capability type ("tool", "resource", or "prompt")
- `proxyAction`: Always "call" for call actions
- `proxyPath`: The name/URI of the called capability

## Client Implementation

Magg provides a `ProxyClient` class that simplifies interaction with proxy-enabled servers:

```python
from magg.proxy.client import ProxyClient

# Create a proxy-aware client
async with ProxyClient("http://localhost:8080/mcp") as client:
    # Natural method interface - returns raw proxy tool results
    result = await client.proxy("tool", "list")
    # Result is a list with one EmbeddedResource for query actions
    
    result = await client.proxy("tool", "call", "calculator_add", arguments={"a": 5, "b": 3})
    # Result is the tool's actual output (list of content items)

# Transparent mode - redirects standard methods through proxy
async with ProxyClient("http://localhost:8080/mcp", transparent=True) as client:
    tools = await client.list_tools()  # Uses proxy internally, returns list[Tool]
    result = await client.call_tool("calculator_add", {"a": 5, "b": 3})  # Returns content list
    
    # Resources and prompts work transparently too
    resources = await client.list_resources()  # Returns list[Resource | ResourceTemplate]
    resource_data = await client.read_resource("config://settings.json")
    prompt_result = await client.get_prompt("greeting", {"name": "Alice"})
```

### Key Features

1. **Natural Interface**: `proxy(type, action, path, arguments, timeout, progress_handler)` method
2. **Raw Results**: The `proxy()` method returns raw proxy tool results without transformation
3. **Transparent Mode**: Overrides standard client methods to use proxy, with automatic result transformation
4. **Type Safety**: Full type annotations with proper return types
5. **Validation**: Built-in parameter validation matching server requirements
6. **Progress Support**: Optional timeout and progress handler parameters

### ProxyClient Constructor

```python
ProxyClient(
    *args,
    transparent: bool = False,
    proxy_tool_name: str | None = None,
    **kwds
)
```

- `transparent`: If True, override standard methods to use proxy
- `proxy_tool_name`: Name of the proxy tool (default: "proxy")
- Other arguments are passed to the base FastMCP Client

### ProxyClient Methods

#### `proxy(proxy_type, action, path=None, arguments=None, timeout=None, progress_handler=None)`

Direct access to the proxy tool. Returns raw results as returned by the proxy tool:
- For `list`/`info`: List with single EmbeddedResource containing JSON-encoded data
- For `call`: The actual tool/resource/prompt results

#### Transparent Mode Methods

When `transparent=True`, these methods automatically use the proxy tool:

- `list_tools()` → `list[Tool]`
- `list_resources()` → `list[Resource | ResourceTemplate]` (includes templates)
- `list_prompts()` → `list[Prompt]`
- `call_tool(name, arguments)` → `list[TextContent | ImageContent | EmbeddedResource]`
- `read_resource(uri)` → `list[TextResourceContents | BlobResourceContents]`
- `get_prompt(name, arguments)` → `GetPromptResult`

All transparent methods handle result transformation automatically using the transform utilities.

## Server Implementation

Magg's proxy server implementation provides:

1. **Self-introspection**: Server can list its own capabilities via FastMCPTransport
2. **Result transformation**: Automatic conversion between MCP types
3. **Rich annotations**: Metadata for result interpretation with ProxyResponseInfo
4. **Validation**: Parameter validation via `validate_operation()`

### Key Classes

#### `ProxyFastMCP`

A wrapper class that adds proxy functionality to FastMCP instances:

```python
from magg.proxy.server import ProxyFastMCP
from fastmcp import FastMCP

# Wrap an existing FastMCP instance
mcp = FastMCP(name="my-server")
proxy_mcp = ProxyFastMCP(mcp)
```

#### `ProxyMCP`

A mixin class that servers can inherit from:

```python
from magg.proxy.mixin import ProxyMCP
from magg.server.manager import ManagedServer

class MyAggregator(ManagedServer, ProxyMCP):
    def __init__(self):
        super().__init__()
        # ProxyMCP expects server_manager attribute
        self._register_proxy_tool()
```

#### `ProxyResponseInfo`

Metadata extracted from proxy response annotations:

```python
from magg.proxy.server import ProxyResponseInfo

# Extract metadata from annotations
info = ProxyResponseInfo.from_annotations(result.annotations)
# info.proxy_type: "tool" | "resource" | "prompt"
# info.proxy_action: "list" | "info" | "call"
# info.proxy_path: The specific capability name/URI
```

### Helper Methods

- `ProxyMCP.validate_operation(action, a_type)`: Validates proxy parameters
- `ProxyMCP.get_proxy_query_result(result)`: Decodes query action results
- `_register_proxy_tool(wrapper)`: Registers the proxy tool with optional wrapper

## Benefits

1. **Simplified Clients**: Single tool interface instead of managing multiple connections
2. **Dynamic Discovery**: Capabilities can change at runtime
3. **Reduced Complexity**: No need for clients to understand server mounting
4. **Standardized Interface**: Consistent way to access any MCP capability
5. **Future-proof**: Easy to extend with new capability types

## Advanced Usage

### Result Type Preservation

The proxy tool preserves type information through annotations:
- `pythonType`: Original Python type name (e.g., "Tool", "Resource | ResourceTemplate")
- `many`: Whether the result is a list (True for list actions)
- `proxyType`: The capability type ("tool", "resource", "prompt")
- `proxyAction`: The action performed ("list", "info", "call")
- `proxyPath`: The specific capability path (for info and call actions)

### Transform Utilities

Magg provides transform utilities for working with proxy results:

```python
from magg.util.transform import (
    tool_result_as_prompt_result,
    tool_result_as_resource_result,
    get_embedded_resource_python_object,
    deserialize_embedded_resource_python_object
)

# Extract prompt result from tool result format
prompt_result = tool_result_as_prompt_result(tool_result)

# Extract resource result from tool result format
resource_result = tool_result_as_resource_result(tool_result)

# Get metadata from embedded resource
python_type, json_data, many = get_embedded_resource_python_object(embedded_resource)

# Deserialize to proper MCP types
obj = deserialize_embedded_resource_python_object(
    target_type=Tool,
    python_type=python_type,
    json_data=json_data,
    many=many
)
```

### Error Handling

Proxy errors are returned as standard MCP errors:
- Invalid parameters (e.g., missing path for info/call, args provided for list/info)
- Unknown capability types or actions
- Failed server connections
- Tool execution errors
- Invalid result format

### Performance Considerations

- Self-client connection is reused across calls
- Use targeted queries when possible
- Consider implementing pagination for large result sets
- Transparent mode adds minimal overhead (one extra tool call)

## Future Extensions

Potential enhancements for the proxy pattern:

1. **Streaming Support**: For large list results or real-time updates
2. **Filtering**: Server-side filtering of list results
3. **Batch Operations**: Multiple operations in a single call
4. **Capability Negotiation**: Discover proxy tool capabilities
5. **Security**: Fine-grained access control per capability

## Specification Proposal

The proxy tool pattern could be standardized as part of MCP with:

1. **Well-known tool name**: `proxy` or `mcp:proxy` (configurable via constructor)
2. **Standard parameter schema**: 
   - `action`: "list" | "info" | "call"
   - `type`: "tool" | "resource" | "prompt"
   - `path`: Required for info/call, forbidden for list
   - `args`: Only for call action
3. **Result format conventions**: 
   - Query actions: List with single EmbeddedResource containing JSON
   - Call actions: Direct results with proxy annotations
4. **Annotation standards**:
   - `proxyType`, `proxyAction`, `proxyPath` for tracking
   - `pythonType`, `many` for deserialization
5. **Discovery mechanism**: Check for tool named "proxy" in tool list

This pattern enables powerful aggregation and gateway scenarios while maintaining the simplicity and elegance of the MCP protocol.

## Implementation Notes

### Known Limitations

1. **Resource Templates**: `list_resources()` in transparent mode returns both resources and resource templates together, unlike the standard client which has separate methods.

2. **Prompt Results**: Prompt results are wrapped in EmbeddedResource format when called through proxy, requiring transformation back to GetPromptResult.

3. **Error Messages**: Validation errors from the proxy tool provide clear messages about parameter requirements.

### Best Practices

1. **Use transparent mode** when you want a drop-in replacement for standard MCP client
2. **Use direct proxy() calls** when you need access to raw results or metadata
3. **Validate parameters** early using `ProxyMCP.validate_operation()`
4. **Handle empty results** gracefully - list actions may return empty lists
5. **Check annotations** when you need to distinguish between different result types