# MCP Proxy Extension Specification

**Version**: 0.1.0 (Draft)  
**Status**: Proposed  
**Authors**: Magg Contributors  

## Abstract

This specification defines the Model Context Protocol (MCP) Proxy Extension, which enables dynamic access to MCP capabilities through a single, unified tool interface. The proxy pattern allows MCP servers to aggregate, gateway, and dynamically expose capabilities from other servers without requiring clients to manage multiple connections.

This specification is based on the implementation in Magg (MCP Aggregator) and serves as a reference for other MCP servers that want to implement similar proxy functionality. The reference implementation can be found in the `magg.proxy` package.

## 1. Introduction

The MCP Proxy Extension provides a standardized way for MCP servers to expose capabilities from other servers through a single tool. This enables powerful aggregation scenarios while maintaining the simplicity of the MCP protocol.

### 1.1 Requirements Notation

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

### 1.2 Terminology

- **Proxy Tool**: The MCP tool that provides unified access to capabilities
- **Capability**: An MCP tool, resource, or prompt
- **Query Action**: Operations that return metadata (list, info)
- **Call Action**: Operations that execute capabilities

## 2. Proxy Tool Interface

### 2.1 Tool Name

The proxy tool SHOULD be named `proxy`. Servers MAY use an alternative name (e.g., `mcp:proxy`) if documented.

### 2.2 Tool Parameters

The proxy tool MUST accept the following parameters:

#### 2.2.1 action (required)

- **Type**: String enumeration
- **Values**: `"list"` | `"info"` | `"call"`
- **Description**: The operation to perform

#### 2.2.2 type (required)

- **Type**: String enumeration  
- **Values**: `"tool"` | `"resource"` | `"prompt"`
- **Description**: The type of MCP capability to interact with
- **Note**: Implementations MAY use parameter aliasing to avoid language keyword conflicts

#### 2.2.3 path (conditional)

- **Type**: String
- **Description**: Name or URI of the specific capability
- **Requirements**:
  - REQUIRED for `info` and `call` actions
  - MUST NOT be provided for `list` action

#### 2.2.4 args (optional)

- **Type**: Object (key-value pairs)
- **Description**: Arguments for the capability being called
- **Requirements**:
  - ONLY allowed for `call` action
  - MUST NOT be provided for `list` and `info` actions

### 2.3 Parameter Validation

Servers MUST validate parameters and return clear error messages for:
- Missing required parameters
- Invalid parameter combinations
- Unknown action or type values

## 3. Response Formats

### 3.1 Query Actions (list and info)

Query actions MUST return a list containing a single embedded resource with:

#### 3.1.1 Structure

```json
[
  {
    "type": "resource",
    "resource": {
      "uri": "<proxy-uri>",
      "mimeType": "application/json",
      "text": "<json-encoded-capability-data>"
    },
    "annotations": {
      "proxyAction": "<action>",
      "proxyType": "<type>",
      "proxyPath": "<path>",  // Only for info action
      "pythonType": "<type-identifier>",
      "many": <boolean>
    }
  }
]
```

#### 3.1.2 Annotations

Query responses MUST include:
- `proxyAction`: The action performed (`"list"` or `"info"`)
- `proxyType`: The capability type (`"tool"`, `"resource"`, or `"prompt"`)
- `proxyPath`: The specific capability path (ONLY for `info` action)

Query responses SHOULD include type preservation annotations:
- `pythonType`: A type identifier for deserialization (language-specific name to be generalized)
- `many`: Boolean indicating if the data represents multiple objects

### 3.2 Call Actions

Call actions MUST return the actual result from the called capability with proxy annotations.

#### 3.2.1 Tool Calls

Returns a list of content items (TextContent, ImageContent, or EmbeddedResource) with each item annotated:

```json
[
  {
    "type": "text",
    "text": "Result content",
    "annotations": {
      "proxyType": "tool",
      "proxyAction": "call",
      "proxyPath": "<tool-name>"
    }
  }
]
```

#### 3.2.2 Resource Reads

Resource results MUST be converted to tool result format (EmbeddedResource) with annotations.

##### Resource Objectification

When a text resource can be parsed as JSON, implementations SHOULD:
1. Parse the text content as JSON
2. Re-encode it with consistent formatting
3. Set `mimeType` to `"application/json"`
4. Preserve the original MIME type in a `contentType` field

Example with objectification:
```json
[
  {
    "type": "resource",
    "resource": {
      "uri": "<original-resource-uri>",
      "mimeType": "application/json",
      "text": "{\"key\":\"value\"}",
      "contentType": "text/plain"  // Original MIME type preserved
    },
    "annotations": {
      "proxyType": "resource",
      "proxyAction": "call",
      "proxyPath": "<resource-uri>"
    }
  }
]
```

Example without objectification (binary or non-JSON):
```json
[
  {
    "type": "resource",
    "resource": {
      "uri": "<original-resource-uri>",
      "mimeType": "image/png",
      "blob": "<base64-encoded-data>"
    },
    "annotations": {
      "proxyType": "resource",
      "proxyAction": "call",
      "proxyPath": "<resource-uri>"
    }
  }
]
```

#### 3.2.3 Prompt Gets

Prompt results MUST be wrapped in an EmbeddedResource with the prompt data JSON-encoded:

```json
[
  {
    "type": "resource",
    "resource": {
      "uri": "<prompt-uri>",
      "mimeType": "application/json",
      "text": "<json-encoded-prompt-result>"
    },
    "annotations": {
      "proxyType": "prompt",
      "proxyAction": "call",
      "proxyPath": "<prompt-name>",
      "pythonType": "GetPromptResult"
    }
  }
]
```

## 4. Type Preservation

### 4.1 Type Annotations

To enable proper deserialization, implementations SHOULD include type information in annotations.

#### 4.1.1 Standard Type Annotation

The current Magg implementation uses:
- `pythonType`: String identifier for the data type
- `many`: Boolean indicating if the data represents multiple objects

Future revisions SHOULD generalize these to language-agnostic names such as:
- `dataType` or `objectType` instead of `pythonType`
- `isArray` or `multiple` instead of `many`

#### 4.1.2 Type Identifiers

Type identifiers SHOULD use one of these formats:
1. **Simple names**: `"Tool"`, `"Resource"`, `"Prompt"`
2. **Qualified names**: `"mcp.types.Tool"`, `"mcp.types.Resource"`
3. **Union types**: `"Resource|ResourceTemplate"`

### 4.2 MIME Type Preservation

When converting resources to tool results, implementations MUST preserve type information:

1. **Original MIME Type**: If a resource is objectified (converted to JSON), the original MIME type SHOULD be preserved in a `contentType` field
2. **Objectification**: Text resources that parse as valid JSON SHOULD be re-encoded with `mimeType: "application/json"`
3. **Binary Resources**: Resources with binary content remain unchanged with their original MIME type

This allows clients to understand both the current format and the original format of the resource.

### 4.3 Implementation-Specific Extensions

Implementations MAY add additional type preservation mechanisms using custom annotations:
- Python: `pythonType` annotation with Python type names
- TypeScript: `typescriptType` with TypeScript type names
- Other languages: `<language>Type` pattern

## 5. Error Handling

The proxy tool SHOULD rely on standard MCP error handling mechanisms. Implementations SHOULD raise exceptions (or language-appropriate error mechanisms) that are automatically converted to MCP protocol errors.

### 5.1 Parameter Validation

When the proxy tool receives invalid parameters, it SHOULD raise appropriate errors:
- Missing required parameters (e.g., `path` for info/call actions)
- Invalid parameter combinations (e.g., `args` provided for list action)
- Unknown action or type values

### 5.2 Capability Errors

Errors from proxied capabilities SHOULD be propagated naturally:
- Tool not found
- Resource access errors
- Invalid arguments for the proxied capability

These errors are handled the same way as any other MCP tool error - the implementation raises an exception which the MCP protocol layer converts to a proper error response.

## 6. Discovery

### 6.1 Proxy Tool Discovery

Clients SHOULD check for proxy support by:
1. Looking for a tool named `proxy` in the tool list
2. Checking tool description for proxy-related keywords
3. Attempting to call the proxy tool with valid parameters

### 6.2 Capability Discovery

The proxy tool enables dynamic capability discovery without maintaining persistent connections:
1. Use `action: "list"` to enumerate available capabilities
2. Use `action: "info"` to get detailed metadata
3. Cache results as appropriate for performance

## 7. Security Considerations

### 7.1 Access Control

Proxy implementations SHOULD:
- Respect access controls of proxied servers
- Implement per-capability access policies
- Log proxy operations for auditing

### 7.2 Information Disclosure

Proxy tools MUST NOT:
- Expose internal server details in error messages
- Include sensitive information in annotations
- Bypass authentication of proxied servers

## 8. Compatibility

### 8.1 Backward Compatibility

The proxy extension is designed to be backward compatible:
- Clients unaware of proxy tools can ignore them
- Standard MCP operations continue to work normally
- No changes required to existing MCP tools

### 8.2 Forward Compatibility

Future extensions SHOULD:
- Use new annotation namespaces for additional metadata
- Add new capability types through the existing interface
- Maintain the core parameter structure

## 9. Implementation Guidelines

### 9.1 Client Implementation

Clients supporting proxy tools SHOULD:
1. Detect proxy tool availability
2. Provide convenience methods for proxy operations
3. Handle type preservation based on annotations
4. Support transparent mode for drop-in compatibility

### 9.2 Server Implementation

Servers implementing proxy tools SHOULD:
1. Validate all parameters before processing
2. Include comprehensive annotations in responses
3. Handle errors gracefully with clear messages
4. Optimize for performance with connection pooling

## 10. Examples

### 10.1 List Tools

Request arguments:
```json
{
  "action": "list",
  "type": "tool"
}
```

Response (tool result):
```json
[
  {
    "type": "resource",
    "resource": {
      "uri": "proxy:list/tool",
      "mimeType": "application/json",
      "text": "[{\"name\":\"calculator_add\",\"description\":\"Add two numbers\"}]"
    },
    "annotations": {
      "proxyAction": "list",
      "proxyType": "tool",
      "pythonType": "Tool",
      "many": true
    }
  }
]
```

### 10.2 Call Tool

Request arguments:
```json
{
  "action": "call",
  "type": "tool",
  "path": "calculator_add",
  "args": {"a": 5, "b": 3}
}
```

Response (tool result):
```json
[
  {
    "type": "text",
    "text": "8",
    "annotations": {
      "proxyType": "tool",
      "proxyAction": "call",
      "proxyPath": "calculator_add"
    }
  }
]
```

## 11. References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/docs)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Magg Implementation](https://github.com/sitbon/magg)

## 12. Reference Implementation

The reference implementation in Magg includes:

1. **Server-side proxy** (`magg/proxy/server.py` and `magg/proxy/mixin.py`):
   - `ProxyFastMCP` wrapper class that adds proxy capabilities to FastMCP instances
   - `ProxyMCP` mixin class for servers that want built-in proxy support
   - Automatic tool registration and capability aggregation
   - Result transformation and annotation

2. **Client-side wrapper** (`magg/proxy/client.py`):
   - `ProxyClient` class that provides transparent access to proxied servers
   - Automatic result unwrapping and type conversion
   - Lazy connection management

## Appendix A: Future Considerations

### A.1 Batch Operations

Future versions MAY support batch operations:
```json
{
  "action": "batch",
  "operations": [
    {"action": "call", "type": "tool", "path": "tool1", "args": {}},
    {"action": "call", "type": "tool", "path": "tool2", "args": {}}
  ]
}
```

### A.2 Streaming Support

Large result sets could benefit from streaming:
- Use HTTP streaming for progressive results
- Add pagination parameters for list operations
- Support partial result delivery

### A.3 Advanced Filtering

Enhanced discovery through filtering:
```json
{
  "action": "list",
  "type": "tool",
  "filter": {
    "prefix": "calculator_",
    "tags": ["math", "arithmetic"]
  }
}
```