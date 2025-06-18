MAGG_INSTRUCTIONS = """
MAGG (MCP Aggregator) manages and aggregates other MCP servers.

Key capabilities:
- Add and manage MCP servers with intelligent configuration
- Aggregate tools from multiple servers with prefixes to avoid conflicts
- Search for new MCP servers online
- Export/import configurations
- Smart configuration assistance using LLM sampling
- Expose server metadata as resources for LLM consumption

Use {self_prefix}_add_server to register new MCP servers, then they will be automatically mounted.
Tools from mounted servers are available with their configured prefixes.
"""
