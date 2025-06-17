# MAGG Smart Features

This document demonstrates the smart features added back to MAGG.

## Resources

MAGG exposes server metadata as MCP resources that can be consumed by LLM clients:

- `magg://server/{name}` - Get metadata for a specific server
- `magg://servers/all` - Get metadata for all configured servers

These resources allow LLMs to introspect the current MAGG configuration.

## Prompts

MAGG provides prompts for intelligent configuration:

- `configure_server` - Generates a prompt for configuring a server from a URL

## Tools with LLM Integration

### magg_smart_configure

Intelligently configures a server by:
1. Collecting metadata about the URL (GitHub info, file system analysis, etc.)
2. Using LLM sampling to generate optimal configuration
3. Automatically adding the server with the generated config

Example usage:
```python
# With LLM context
result = await magg_smart_configure(
    url="https://github.com/example/weather-mcp",
    server_name="weather",
    ctx=context  # MCP context for sampling
)

# Without LLM context (metadata-based only)
result = await magg_smart_configure(
    url="https://github.com/example/weather-mcp",
    server_name="weather"
)
```

### magg_analyze_servers

Analyzes the current server configuration and provides insights:
- Overview of enabled/disabled servers
- Potential conflicts or issues
- Optimization suggestions
- Missing capabilities

Example usage:
```python
# With LLM insights
result = await magg_analyze_servers(ctx=context)

# Without LLM (just data)
result = await magg_analyze_servers()
```

## Metadata Collection

The smart configuration uses the discovery module to collect metadata:

- **GitHub Analysis**: Stars, language, description, README content
- **File System Analysis**: Project type, dependencies, setup hints
- **HTTP Analysis**: Direct MCP server detection
- **Search Results**: Related tools and packages

This metadata is used to make intelligent configuration decisions even without LLM assistance.

## Example Workflow

1. Search for servers:
   ```
   magg_search_servers("weather forecast")
   ```

2. Smart configure a found server:
   ```
   magg_smart_configure("https://github.com/example/weather-mcp")
   ```

3. Analyze the setup:
   ```
   magg_analyze_servers()
   ```

4. Access server metadata via resources:
   ```
   GET magg://server/weather
   ```

The combination of these features provides a powerful, self-aware MCP aggregation system that can intelligently manage and reflect on its own configuration.