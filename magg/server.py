"""MAGG - MCP Aggregator Server - Simplified Implementation

Clean separation: Sources (metadata) vs Servers (runtime configuration)
"""
import json
import logging
from typing import Any

from fastmcp import FastMCP, Client, Context

from .core.config import ConfigManager, MCPSource, MCPServer
from .utils import (
    TRANSPORT_DOCS, 
    get_transport_for_command, 
    get_transport_for_uri,
    validate_working_directory
)

# Create the main FastMCP server with instructions
MAGG_INSTRUCTIONS = """
MAGG (MCP Aggregator) is a self-aware MCP server that manages and aggregates other MCP tools/servers.

Key capabilities:
- Add and manage MCP sources (packages/repositories)
- Configure and mount MCP servers from sources
- Aggregate tools from multiple servers with prefixes to avoid conflicts
- Search for new MCP tools online
- Export/import configurations
- Smart configuration assistance using LLM sampling

Use magg_add_source to register new MCP packages, then magg_add_server to create runnable server instances.
"""

mcp = FastMCP(name="magg", instructions=MAGG_INSTRUCTIONS, log_level="INFO")

# Global instances
config_manager: ConfigManager | None = None
mounted_servers: dict[str, Any] = {}  # Track mounted proxy servers by name


@mcp.tool
async def magg_add_source(name: str, uri: str | None = None) -> str:
    """Add a new MCP source with enhanced metadata collection.
    
    Args:
        name: Unique source name (required)
        uri: Optional URI of the source (defaults to local file:// URI)
             For remote sources: GitHub, NPM, HTTP/HTTPS URLs
             For local sources: omit to auto-create in .magg/sources/<name>
    """
    try:
        # Check if source already exists by name
        config = config_manager.load_config()
        if name in config.sources:
            return f"❌ Source '{name}' already exists"
        
        # Create source - URI will be auto-generated if not provided
        source = MCPSource(name=name, uri=uri)
        
        # Create local directory if it's a file:// URI
        if source.uri.startswith('file://'):
            import os
            from pathlib import Path
            path = source.uri.replace('file://', '')
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Collect rich metadata from multiple sources
        from .discovery.metadata import SourceMetadataCollector
        collector = SourceMetadataCollector()
        
        result_lines = [f"🔍 Collecting metadata for '{source.name}'..."]
        
        try:
            metadata_entries = await collector.collect_metadata(source.uri, source.name)
            
            # Add collected metadata to source
            for entry in metadata_entries:
                source.metadata.append(entry)
            
            # Generate summary of collected metadata
            metadata_summary = []
            for entry in metadata_entries:
                source_name = entry.get("source", "unknown")
                data = entry.get("data", {})
                
                if source_name == "http_check":
                    if data.get("is_mcp_server"):
                        metadata_summary.append("🔗 Direct MCP server detected")
                    elif data.get("accessible"):
                        metadata_summary.append("🌐 HTTP accessible")
                
                elif source_name == "github":
                    stars = data.get("stars", 0)
                    language = data.get("language", "Unknown")
                    metadata_summary.append(f"⭐ GitHub: {stars} stars, {language}")
                    
                    setup_instructions = data.get("setup_instructions", [])
                    if setup_instructions:
                        metadata_summary.append(f"📋 Found {len(setup_instructions)} setup hints")
                
                elif source_name == "filesystem":
                    if data.get("exists"):
                        if data.get("is_directory"):
                            project_type = data.get("project_type", "unknown")
                            if project_type != "unknown":
                                metadata_summary.append(f"📁 {project_type.replace('_', ' ').title()}")
                            
                            project_files = data.get("project_files", {})
                            key_files = [f for f in project_files.keys() if f in ['package.json', 'pyproject.toml', 'requirements.txt', 'CLAUDE.md']]
                            if key_files:
                                metadata_summary.append(f"📄 Found {', '.join(key_files)}")
                            
                            setup_hints = data.get("setup_hints", [])
                            if setup_hints:
                                metadata_summary.append(f"🔧 {len(setup_hints)} setup commands identified")
                        else:
                            metadata_summary.append(f"📄 Single file: {data.get('filename', 'unknown')}")
                    else:
                        metadata_summary.append("❌ Path does not exist")
                
                elif source_name == "search_results":
                    matches = data.get("total_matches", 0)
                    if matches > 0:
                        metadata_summary.append(f"🔍 Found {matches} search matches")
                
                elif source_name == "filesystem":
                    if data.get("exists"):
                        if data.get("is_directory"):
                            project_type = data.get("project_type", "unknown")
                            if project_type != "unknown":
                                metadata_summary.append(f"📁 {project_type.replace('_', ' ').title()}")
                            
                            project_files = data.get("project_files", {})
                            key_files = [f for f in project_files.keys() if f in ['package.json', 'pyproject.toml', 'requirements.txt', 'CLAUDE.md']]
                            if key_files:
                                metadata_summary.append(f"📄 Found {', '.join(key_files)}")
                            
                            setup_hints = data.get("setup_hints", [])
                            if setup_hints:
                                metadata_summary.append(f"🔧 {len(setup_hints)} setup commands identified")
                        else:
                            metadata_summary.append(f"📄 Single file: {data.get('filename', 'unknown')}")
                    else:
                        metadata_summary.append("❌ Path does not exist")
            
            if metadata_summary:
                result_lines.extend(metadata_summary)
            else:
                result_lines.append("📝 Basic metadata collected")
            
        except Exception as e:
            result_lines.append(f"⚠️ Metadata collection partially failed: {str(e)}")
        
        # Save source with metadata
        config.add_source(source)
        config_manager.save_config(config)
        
        result_lines.append(f"✅ Added source '{source.name}' with metadata")
        
        # Show setup hints if available
        setup_hints = source.get_setup_hints()
        if setup_hints:
            result_lines.append("💡 Setup hints found:")
            for hint in setup_hints[:3]:  # Show first 3 hints
                result_lines.append(f"   • {hint}")
        
        # Suggest next steps
        if source.is_direct_mcp_server():
            result_lines.append("🚀 This appears to be a direct MCP server - try adding as HTTP server")
        else:
            result_lines.append("🔧 Use magg_add_server() to create a runnable server from this source")
        
        return "\n".join(result_lines)
    
    except Exception as e:
        return f"❌ Error adding source: {str(e)}"


def _attach_transport_docs(fn):
    fn.__doc__ += TRANSPORT_DOCS
    return fn


@_attach_transport_docs
async def magg_add_server(
    name: str,
    source_name: str,
    prefix: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    uri: str | None = None,
    env_vars: dict[str, str] | None = None,
    working_dir: str | None = None,
    transport: dict[str, Any] | None = None,
    notes: str | None = None
) -> str:
    """Add a new server configuration from a source.
    
    Args:
        name: Unique server name
        source_name: Name of the source this server uses
        prefix: Tool prefix (defaults to server name)
        command: Main command (e.g., "python", "node", "uvx", "npx")
        args: Command arguments as a list
        uri: URI for HTTP servers
        env_vars: Environment variables as a dictionary
        working_dir: Working directory for the server (required for commands, must not be project root)
        transport: Transport-specific configuration as a dictionary (see below)
        notes: Setup notes for LLM and humans
    
    Transport Configuration:
    """
    try:
        config = config_manager.load_config()

        # Check if source exists
        if source_name not in config.sources:
            return f"❌ Source '{source_name}' not found. Add it first with magg_add_source()"

        # Check if server name already exists
        if name in config.servers:
            return f"❌ Server '{name}' already exists"
        
        # Get source URI for validation
        source = config.sources[source_name]
        
        # Validate working directory for command-based servers
        if command:
            # Check if source has a URI
            if not source.uri:
                return f"❌ Source '{source_name}' has no URI configured. Please update the source with a URI."
            
            validated_dir, error = validate_working_directory(working_dir, source.uri)
            if error:
                return f"❌ {error}"
            working_dir = str(validated_dir)
        elif working_dir:
            return "❌ Working directory should only be specified for command-based servers"

        # Create server
        server = MCPServer(
            name=name,
            source_name=source_name,
            prefix=prefix or name,
            command=command,
            args=args,
            uri=uri,
            env=env_vars,
            working_dir=working_dir,
            transport=transport,
            notes=notes
        )

        # Attempt to mount the server first
        mount_success = await mount_server(server)
        if not mount_success:
            return f"❌ Failed to mount server '{name}' - server not added. Check configuration."

        # Only save if mounting succeeded
        config.add_server(server)
        config_manager.save_config(config)

        result = [f"✅ Added and mounted server '{name}'"]
        result.append(f"   Source: {source_name}")
        result.append(f"   Prefix: {server.prefix}")
        if server.command:
            cmd_display = server.command
            if server.args:
                cmd_display += " " + " ".join(server.args)
            result.append(f"   Command: {cmd_display}")
        if server.uri:
            result.append(f"   URI: {server.uri}")
        if server.transport:
            result.append(f"   Transport config: {json.dumps(server.transport)}")
        if server.notes:
            result.append(f"   Notes: {server.notes}")

        return "\n".join(result)

    except Exception as e:
        return f"❌ Error adding server: {str(e)}"


_magg_add_server = mcp.tool(magg_add_server)


@mcp.tool()
async def magg_edit_server(
    name: str,
    prefix: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    uri: str | None = None,
    env_vars: dict[str, str] | None = None,
    working_dir: str | None = None,
    transport: dict[str, Any] | None = None,
    notes: str | None = None,
    reload: bool | None = None,
) -> str:
    """Edit server configuration.
    
    Args:
        name: Server name to edit
        prefix: New tool prefix
        command: New main command (e.g., "python", "node", "uvx", "npx")
        args: New command arguments as a list of strings
        uri: New URI
        env_vars: New environment variables as dict
        working_dir: New working directory
        transport: New transport-specific configuration as dict
        notes: New notes
        reload: If true, remount the server after editing (default: true)
    """
    try:
        config = config_manager.load_config()
        
        if name not in config.servers:
            return f"❌ Server '{name}' not found"
        
        server = config.servers[name]
        changed = False

        # Update provided fields
        if prefix:
            changed = server.prefix != prefix
            server.prefix = prefix
        if command:
            changed = changed or server.command != command
            server.command = command
        if args:
            changed = changed or server.args != args
            server.args = args
        if uri:
            changed = changed or server.uri != uri
            server.uri = uri
        if env_vars:
            changed = changed or server.env != env_vars
            server.env = env_vars
        if working_dir:
            # Validate working directory if server uses commands
            if server.command or command:
                # Get source URI from config
                source = config.sources.get(server.source_name)
                if not source:
                    return f"❌ Source '{server.source_name}' not found in configuration"
                validated_dir, error = validate_working_directory(working_dir, source.uri)
                if error:
                    return f"❌ {error}"
                working_dir = str(validated_dir)
            changed = changed or server.working_dir != working_dir
            server.working_dir = working_dir
        if transport:
            changed = changed or server.transport != transport
            server.transport = transport
        if notes:
            changed = changed or server.notes != notes
            server.notes = notes

        if not changed:
            return f"ℹ️ No changes made to server '{name}'"

        config_manager.save_config(config)

        if reload is None or reload:
            # Remount the server
            if name in mounted_servers:
                del mounted_servers[name]
            mount_success = await mount_server(server)
            if not mount_success:
                return f"❌ Updated server '{name}' but failed to remount. Check configuration."

        return f"✅ Updated server '{name}' configuration"

    except Exception as e:
        return f"❌ Error editing server: {str(e)}"



@mcp.tool()
async def magg_list_sources() -> str:
    """List all registered sources."""
    try:
        config = config_manager.load_config()
        
        if not config.sources:
            return "📋 No sources registered"
        
        result = ["📋 Sources:"]
        
        for name, source in config.sources.items():
            servers = config.get_servers_for_source(name)
            server_count = len(servers)
            
            result.append(f"  📦 {name}")
            result.append(f"      URI: {source.uri}")
            result.append(f"      Servers: {server_count}")
        
        return "\n".join(result)
    
    except Exception as e:
        return f"❌ Error listing sources: {str(e)}"


@mcp.tool()
async def magg_list_servers() -> str:
    """List all registered servers with their status."""
    try:
        config = config_manager.load_config()
        
        if not config.servers:
            return "📋 No servers registered"
        
        result = ["📋 Servers:"]
        
        for name, server in config.servers.items():
            # Check if server is currently mounted
            status = "🟢 Mounted" if name in mounted_servers else "⚪ Not mounted"
            result.append(f"  {status} {name} ({server.prefix})")
            result.append(f"      Source: {server.source_name}")
            
            if server.command:
                cmd_display = server.command
                if server.args:
                    cmd_display += " " + " ".join(server.args)
                result.append(f"      Command: {cmd_display}")
            if server.uri:
                result.append(f"      URI: {server.uri}")
            if server.working_dir:
                result.append(f"      Working Dir: {server.working_dir}")
            if server.notes:
                result.append(f"      Notes: {server.notes}")
        
        return "\n".join(result)
    
    except Exception as e:
        return f"❌ Error listing servers: {str(e)}"


@mcp.tool()
async def magg_list_tools() -> str:
    """List all available tools from mounted servers."""
    try:
        tools = await mcp.get_tools()
        
        if not tools:
            return "🔧 No tools available"
        
        result = ["🔧 Available Tools:"]
        
        # Group tools by prefix
        by_prefix = {}
        for tool_name in tools.keys():
            if '_' in tool_name and not tool_name.startswith('magg_'):
                prefix = tool_name.split('_', 1)[0]
                if prefix not in by_prefix:
                    by_prefix[prefix] = []
                by_prefix[prefix].append(tool_name)
            else:
                # MAGG's own tools
                if 'magg' not in by_prefix:
                    by_prefix['magg'] = []
                by_prefix['magg'].append(tool_name)
        
        for prefix, prefix_tools in by_prefix.items():
            result.append(f"  {prefix}:")
            for tool in sorted(prefix_tools):
                result.append(f"    • {tool}")
        
        return "\n".join(result)
    
    except Exception as e:
        return f"❌ Error listing tools: {str(e)}"


@mcp.tool()
async def magg_remove_source(name: str) -> str:
    """Remove a source and all its servers.
    
    Args:
        name: Source name to remove
    """
    try:
        config = config_manager.load_config()
        
        if config.remove_source(name):
            config_manager.save_config(config)
            return f"✅ Removed source '{name}' and all its servers"
        else:
            return f"❌ Source '{name}' not found"
    
    except Exception as e:
        return f"❌ Error removing source: {str(e)}"


@mcp.tool()
async def magg_remove_server(name: str) -> str:
    """Remove a server.
    
    Args:
        name: Server name to remove
    """
    try:
        config = config_manager.load_config()
        
        if name in config.servers:
            # Remove from mounted servers if present
            if name in mounted_servers:
                del mounted_servers[name]
            
            config.remove_server(name)
            config_manager.save_config(config)
            return f"✅ Removed server '{name}'"
        else:
            return f"❌ Server '{name}' not found"
    
    except Exception as e:
        return f"❌ Error removing server: {str(e)}"


@mcp.tool()
async def magg_search_sources(query: str, limit: int = 5) -> str:
    """Search for MCP sources online without automatically adding them.
    
    Args:
        query: Search term
        limit: Maximum results per source
    """
    try:
        from .discovery.catalog import CatalogManager
        catalog_manager = CatalogManager()
        
        results = await catalog_manager.search_only(query, limit)
        
        if not any(results.values()):
            return f"🔍 No results found for '{query}'"
        
        output = [f"🔍 Search Results for '{query}':"]
        result_index = 1
        
        for source, source_results in results.items():
            if source_results:
                output.append(f"\n{source.upper()}:")
                for result in source_results:
                    output.append(f"   [{result_index}] {result.name}")
                    output.append(f"       {result.description}")
                    if result.url:
                        output.append(f"       🔗 {result.url}")
                    result_index += 1
        
        output.append(f"\n💡 To add: magg_add_source(name='<name>', uri='<uri>')")
        
        return "\n".join(output)
    
    except Exception as e:
        return f"❌ Error searching sources: {str(e)}"


# ============================================================================
# MCP Resources - Expose source metadata for LLM consumption
# ============================================================================

@mcp.resource("magg://source/{name}")
async def get_source_metadata(name: str) -> str:
    """Expose source metadata as an MCP resource."""
    try:
        config = config_manager.load_config()
        
        # URI decode the parameter
        import urllib.parse
        decoded_name = urllib.parse.unquote(name)
        
        if decoded_name not in config.sources:
            return json.dumps({"error": f"Source not found: {decoded_name}"})
        
        source = config.sources[decoded_name]
        
        # Format metadata for LLM consumption
        resource_data = {
            "uri": source.uri,
            "name": source.name,
            "metadata": source.metadata,
            "setup_hints": source.get_setup_hints(),
            "is_direct_mcp_server": source.is_direct_mcp_server(),
            "collected_metadata_sources": [entry.get("source") for entry in source.metadata]
        }
        
        return json.dumps(resource_data, indent=2)
    
    except Exception as e:
        return json.dumps({"error": f"Failed to load source metadata: {str(e)}"})


@mcp.resource("magg://sources/all")
async def get_all_sources_metadata() -> str:
    """Expose all sources metadata as an MCP resource."""
    try:
        config = config_manager.load_config()
        
        sources_data = {}
        for name, source in config.sources.items():
            sources_data[name] = {
                "uri": source.uri,
                "metadata_summary": {
                    "total_entries": len(source.metadata),
                    "sources": [entry.get("source") for entry in source.metadata],
                    "has_setup_hints": len(source.get_setup_hints()) > 0,
                    "is_direct_mcp_server": source.is_direct_mcp_server()
                }
            }
        
        return json.dumps({
            "total_sources": len(sources_data),
            "sources": sources_data
        }, indent=2)
    
    except Exception as e:
        return json.dumps({"error": f"Failed to load sources: {str(e)}"})


# ============================================================================
# MCP Prompts - Templates for LLM-assisted server configuration
# ============================================================================

@mcp.prompt("configure_server_from_source")
async def configure_server_prompt(source_name: str, server_name: str | None = None) -> list[dict[str, str]]:
    """Generate a prompt for configuring a server from source metadata."""
    try:
        config = config_manager.load_config()
        
        if source_name not in config.sources:
            return [{"role": "user", "content": f"Error: Source '{source_name}' not found"}]
        
        source = config.sources[source_name]
        
        # Build comprehensive prompt with all metadata
        prompt_parts = [
            f"I need help configuring an MCP server from this source:",
            f"",
            f"**Source Details:**",
            f"- Name: {source.name}",
            f"- URI: {source.uri}",
            f"- Server Name: {server_name or 'Please suggest one'}",
            f"",
        ]
        
        # Add metadata information
        if source.metadata:
            prompt_parts.append("**Available Metadata:**")
            for entry in source.metadata:
                source_name = entry.get("source", "unknown")
                data = entry.get("data", {})
                
                prompt_parts.append(f"")
                prompt_parts.append(f"From {source_name}:")
                
                if source_name == "github":
                    prompt_parts.append(f"- Description: {data.get('description', 'N/A')}")
                    prompt_parts.append(f"- Language: {data.get('language', 'N/A')}")
                    prompt_parts.append(f"- Stars: {data.get('stars', 0)}")
                    
                    setup_instructions = data.get("setup_instructions", [])
                    if setup_instructions:
                        prompt_parts.append(f"- Setup instructions found: {len(setup_instructions)}")
                        for i, instruction in enumerate(setup_instructions[:5]):  # First 5
                            prompt_parts.append(f"  {i+1}. {instruction}")
                
                elif source_name == "http_check":
                    prompt_parts.append(f"- Is MCP server: {data.get('is_mcp_server', False)}")
                    prompt_parts.append(f"- Accessible: {data.get('accessible', False)}")
                    indicators = data.get("mcp_indicators", [])
                    if indicators:
                        prompt_parts.append(f"- MCP indicators: {', '.join(indicators)}")
                
                elif source_name == "search_results":
                    matches = data.get("matches", [])
                    if matches:
                        prompt_parts.append(f"- Search matches: {len(matches)}")
                        for match in matches[:3]:  # First 3 matches
                            prompt_parts.append(f"  - {match.get('name')}: {match.get('description')}")
                            if match.get('install_command'):
                                prompt_parts.append(f"    Install: {match.get('install_command')}")
        
        # Add setup hints
        setup_hints = source.get_setup_hints()
        if setup_hints:
            prompt_parts.append("")
            prompt_parts.append("**Setup Hints:**")
            for hint in setup_hints:
                prompt_parts.append(f"- {hint}")
        
        # Add configuration request
        prompt_parts.extend([
            "",
            "**Please help me configure this as an MCP server by providing:**",
            "",
            "1. **Server Configuration** - What should I use for:",
            "   - Command to run (if it's a command-based server)",
            "   - URI (if it's an HTTP server)", 
            "   - Environment variables needed",
            "   - Working directory",
            "   - Tool prefix to use",
            "",
            "2. **Setup Steps** - What do I need to do to get this running?",
            "   - Installation commands",
            "   - Configuration files needed",
            "   - Dependencies to install",
            "",
            "3. **Connection Details** - How should MAGG connect to this server?",
            "",
            "Based on the metadata above, provide specific, actionable configuration details I can use with the `magg_add_server` tool.",
        ])
        
        return [{"role": "user", "content": "\n".join(prompt_parts)}]
    
    except Exception as e:
        return [{"role": "user", "content": f"Error generating configuration prompt: {str(e)}"}]


@mcp.prompt("analyze_source_setup")
async def analyze_source_setup_prompt(source_name: str) -> list[dict[str, str]]:
    """Generate a prompt for analyzing source setup requirements."""
    try:
        config = config_manager.load_config()
        
        if source_name not in config.sources:
            return [{"role": "user", "content": f"Error: Source '{source_name}' not found"}]
        
        source = config.sources[source_name]
        
        prompt_parts = [
            f"Please analyze this MCP source and extract setup information:",
            f"",
            f"**Source:** {source.name} ({source.uri})",
            f"",
            f"**Metadata Available:**",
        ]
        
        # Include all raw metadata for analysis
        for entry in source.metadata:
            prompt_parts.append(f"")
            prompt_parts.append(f"**{entry.get('source', 'Unknown').upper()} Data:**")
            prompt_parts.append(f"```json")
            prompt_parts.append(json.dumps(entry.get('data', {}), indent=2))
            prompt_parts.append(f"```")
        
        prompt_parts.extend([
            "",
            "**Please extract and provide:**",
            "",
            "1. **Installation Requirements**",
            "   - What needs to be installed? (Node.js, Python, etc.)",
            "   - Package manager commands (npm install, pip install, etc.)",
            "",
            "2. **Server Startup**", 
            "   - How to start the MCP server?",
            "   - What command should be used?",
            "   - Any required arguments or flags?",
            "",
            "3. **Configuration Needs**",
            "   - Environment variables required?",
            "   - Configuration files needed?",
            "   - API keys or credentials?",
            "",
            "4. **Connection Details**",
            "   - Does it run as a process (stdio) or HTTP server?",
            "   - Default port if HTTP?",
            "   - Any special connection requirements?",
            "",
            "Format your response with clear sections and actionable steps."
        ])
        
        return [{"role": "user", "content": "\n".join(prompt_parts)}]
    
    except Exception as e:
        return [{"role": "user", "content": f"Error generating analysis prompt: {str(e)}"}]


# ============================================================================
# MCP Sampling - LLM-assisted server configuration
# ============================================================================

async def magg_generate_server_config(
    source_name: str, 
    server_name: str | None = None,
    ctx: Context = None
) -> str:
    """Generate server configuration using LLM sampling with source metadata.
    
    Args:
        source_name: Name of the source to configure as a server
        server_name: Optional name for the server
        ctx: MCP context for sampling
    """
    try:
        config = config_manager.load_config()
        
        if source_name not in config.sources:
            return f"❌ Source '{source_name}' not found. Add it first with magg_add_source()"
        
        source = config.sources[source_name]
        
        if not ctx:
            return "❌ MCP context not available for LLM sampling"
        
        # Build comprehensive prompt with all available metadata
        prompt_parts = [
            "Based on the following source metadata, generate a complete MCP server configuration:",
            "",
            f"**Source Details:**",
            f"- Name: {source.name}",
            f"- URI: {source.uri}",
            f"- Requested server name: {server_name or 'auto-suggest'}",
            "",
        ]
        
        # Include all metadata
        if source.metadata:
            prompt_parts.append("**Available Metadata:**")
            for entry in source.metadata:
                source_name = entry.get("source", "unknown")
                data = entry.get("data", {})
                
                prompt_parts.append(f"")
                prompt_parts.append(f"**{source_name.upper()} Metadata:**")
                prompt_parts.append(json.dumps(data, indent=2))
        
        # Add setup hints
        setup_hints = source.get_setup_hints()
        if setup_hints:
            prompt_parts.append("")
            prompt_parts.append("**Extracted Setup Hints:**")
            for hint in setup_hints:
                prompt_parts.append(f"- {hint}")
        
        # Add configuration instructions
        prompt_parts.extend([
            "",
            "**Required Output:**",
            "Generate a JSON configuration with these exact fields for use with magg_add_server:",
            "",
            "```json",
            "{",
            '  "name": "suggested_server_name",',
            '  "source_name": "' + source_name + '",', 
            '  "prefix": "suggested_prefix",',
            '  "command": "exact command to run the server",',
            '  "uri": "http://localhost:port (if HTTP server, otherwise null)",',
            '  "env_vars": {"ENV_VAR": "value"} (as JSON object if needed),',
            '  "working_dir": "/path/to/working/directory (if needed)",',
            '  "notes": "Brief setup notes for humans"',
            "}",
            "```",
            "",
            "**Guidelines:**",
            "1. Choose appropriate server name and prefix",
            "2. Determine if it's a command-based or HTTP server",
            "3. Extract exact command from setup instructions", 
            "4. Include necessary environment variables",
            "5. Set working directory if required",
            "6. Add helpful notes for manual setup",
            "",
            "**Important:** Return ONLY the JSON configuration, no additional text."
        ])
        
        # Request LLM completion via sampling
        await ctx.info(f"🧠 Generating server configuration for {source.name}...")
        
        system_prompt = (
            "You are an expert at configuring MCP servers. "
            "Analyze the provided metadata and generate precise, actionable server configurations. "
            "Focus on extracting exact commands, correct ports, and necessary environment variables. "
            "Return only valid JSON as specified."
        )
        
        try:
            response = await ctx.sample(
                "\n".join(prompt_parts),
                system_prompt=system_prompt,
                temperature=0.1,  # Low temperature for precise configuration
                max_tokens=1000
            )
            
            # Try to parse the JSON response
            import re
            
            # Extract JSON from response (handle cases where LLM adds extra text)
            json_match = re.search(r'```json\s*(.*?)\s*```', response.text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{.*}', response.text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                else:
                    json_text = response.text.strip()
            
            # Parse and validate the JSON
            try:
                config_data = json.loads(json_text)
                
                # Validate required fields
                required_fields = ["name", "source_name", "prefix"]
                missing_fields = [field for field in required_fields if field not in config_data]
                
                if missing_fields:
                    return f"❌ Generated configuration missing required fields: {missing_fields}\n\nRaw response:\n{response.text}"
                
                # Format the response
                result_lines = [
                    "🧠 Generated server configuration:",
                    "",
                    "**Configuration:**",
                    json.dumps(config_data, indent=2),
                    "",
                    "**Next Steps:**",
                    f"Use this configuration with: magg_add_server(",
                    f"  name='{config_data['name']}',",
                    f"  source_name='{config_data['source_name']}',",
                    f"  prefix='{config_data['prefix']}',",
                ]
                
                if config_data.get("command"):
                    result_lines.append(f"  command='{config_data['command']}',")
                if config_data.get("uri"):
                    result_lines.append(f"  uri='{config_data['uri']}',")
                if config_data.get("env_vars"):
                    result_lines.append(f"  env_vars={config_data['env_vars']},")
                if config_data.get("working_dir"):
                    result_lines.append(f"  working_dir='{config_data['working_dir']}',")
                if config_data.get("notes"):
                    result_lines.append(f"  notes='{config_data['notes']}'")
                
                result_lines.append(")")
                
                return "\n".join(result_lines)
            
            except json.JSONDecodeError as e:
                return f"❌ Failed to parse generated JSON: {str(e)}\n\nRaw response:\n{response.text}"
        
        except Exception as e:
            return f"❌ LLM sampling failed: {str(e)}"
    
    except Exception as e:
        return f"❌ Error generating server configuration: {str(e)}"

_magg_generate_server_config = mcp.tool(magg_generate_server_config)


@mcp.tool
async def magg_smart_configure(
    source_name: str,
    auto_add: bool = False,
    ctx: Context = None
) -> str:
    """Smart configuration: Generate and optionally add server configuration.
    
    Args:
        source_name: Name of the source to configure
        auto_add: If True, automatically add the generated server configuration
        ctx: MCP context for sampling
    """
    try:
        # First generate the configuration
        config_result = await magg_generate_server_config(source_name, None, ctx)
        
        if config_result.startswith("❌"):
            return config_result
        
        if not auto_add:
            return config_result + "\n\n💡 Set auto_add=True to automatically add this server configuration"
        
        # Extract the JSON configuration from the result
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', config_result, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*}', config_result, re.DOTALL)
        
        if not json_match:
            return f"❌ Could not extract configuration for auto-add\n\n{config_result}"
        
        try:
            config_data = json.loads(json_match.group(1) if json_match.groups() else json_match.group(0))
            
            # Use the generated configuration to add the server
            add_result = await magg_add_server(
                name=config_data["name"],
                source_name=config_data["source_name"],
                prefix=config_data.get("prefix"),
                command=config_data.get("command"),
                uri=config_data.get("uri"),
                env_vars=config_data.get("env_vars"),
                working_dir=config_data.get("working_dir"),
                notes=config_data.get("notes")
            )
            
            return f"{config_result}\n\n**Auto-Add Result:**\n{add_result}"
        
        except (json.JSONDecodeError, KeyError) as e:
            return f"❌ Failed to parse generated configuration for auto-add: {str(e)}\n\n{config_result}"
    
    except Exception as e:
        return f"❌ Error in smart configuration: {str(e)}"


async def mount_server(server: MCPServer) -> bool:
    """Mount a server using FastMCP with proper transport selection."""
    try:
        if server.command:
            # Command-based server - use specific transport
            transport = get_transport_for_command(
                command=server.command,
                args=server.args or [],
                env=server.env,
                working_dir=server.working_dir,
                transport_config=server.transport
            )
            
            # Create client with the transport
            client = Client(transport)
            
        elif server.uri:
            # URI-based server - use appropriate HTTP transport
            transport = get_transport_for_uri(
                uri=server.uri,
                transport_config=server.transport
            )
            
            # Create client with the transport
            client = Client(transport)
            
        else:
            logging.getLogger(__name__).error(f"No command or URI specified for {server.name}")
            return False
        
        # Create a proxy server from the client and mount it
        proxy_server = FastMCP.as_proxy(client)
        mcp.mount(server.prefix, proxy_server)
        mounted_servers[server.name] = proxy_server
        
        logging.getLogger(__name__).info(f"Mounted server {server.name} with prefix {server.prefix}")
        return True
    
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to mount server {server.name}: {e}")
        return False


async def setup_magg(config_path: str | None = None):
    """Initialize MAGG components and mount existing servers."""
    global config_manager
    
    # Initialize components
    config_manager = ConfigManager(config_path)
    
    # Load existing configuration and mount all servers
    config = config_manager.load_config()
    
    if config.servers:
        logging.getLogger(__name__).info(f"Mounting {len(config.servers)} existing servers...")
        
        mount_results = []
        for name, server in config.servers.items():
            try:
                success = await mount_server(server)
                if success:
                    mount_results.append(f"✅ {name}")
                    logging.getLogger(__name__).info(f"Successfully mounted server: {name}")
                else:
                    mount_results.append(f"❌ {name}")
                    logging.getLogger(__name__).warning(f"Failed to mount server: {name}")
            except Exception as e:
                mount_results.append(f"❌ {name} ({str(e)})")
                logging.getLogger(__name__).error(f"Error mounting server {name}: {e}")
        
        logging.getLogger(__name__).info(f"Mount results: {', '.join(mount_results)}")
    else:
        logging.getLogger(__name__).info("No existing servers to mount")
