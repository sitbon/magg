"""MAGG - MCP Aggregator Server - Clean Class-Based Implementation"""

import json
import logging
from typing import Any
from pathlib import Path

from fastmcp import FastMCP, Client, Context

from .settings import ConfigManager, ServerConfig
from .response import MAGGResponse
from .utils import (
    get_transport_for_command, 
    get_transport_for_uri,
    validate_working_directory
)

# Instructions for the MAGG server
MAGG_INSTRUCTIONS = """
MAGG (MCP Aggregator) manages and aggregates other MCP servers.

Key capabilities:
- Add and manage MCP servers with intelligent configuration
- Aggregate tools from multiple servers with prefixes to avoid conflicts
- Search for new MCP servers online
- Export/import configurations
- Smart configuration assistance using LLM sampling
- Expose server metadata as resources for LLM consumption

Use magg_add_server to register new MCP servers, then they will be automatically mounted.
Tools from mounted servers are available with their configured prefixes.
"""


class ServerManager:
    """Manages MCP servers - mounting, unmounting, and tracking."""
    
    def __init__(self, mcp: FastMCP, config_manager: ConfigManager):
        self.mcp = mcp
        self.config_manager = config_manager
        self.mounted_servers = {}  # name -> proxy server
        self.logger = logging.getLogger(__name__)
    
    async def mount_server(self, server: ServerConfig) -> bool:
        """Mount a server using FastMCP."""
        if not server.enabled:
            self.logger.info("Server %s is disabled, skipping mount", server.name)
            return False
            
        try:
            if server.command:
                # Command-based server
                transport = get_transport_for_command(
                    command=server.command,
                    args=server.args or [],
                    env=server.env,
                    working_dir=server.working_dir,
                    transport_config=server.transport
                )
                client = Client(transport)
                
            elif server.uri:
                # URI-based server
                transport = get_transport_for_uri(
                    uri=server.uri,
                    transport_config=server.transport
                )
                client = Client(transport)
                
            else:
                self.logger.error("No command or URI specified for %s", server.name)
                return False
            
            # Create proxy and mount
            proxy_server = FastMCP.as_proxy(client)
            self.mcp.mount(server.prefix, proxy_server)
            self.mounted_servers[server.name] = proxy_server
            
            self.logger.info("Mounted server %s with prefix %s", server.name, server.prefix)
            return True
        
        except Exception as e:
            self.logger.error("Failed to mount server %s: %s", server.name, e)
            return False
    
    async def unmount_server(self, name: str) -> bool:
        """Unmount a server."""
        if name in self.mounted_servers:
            # Note: FastMCP doesn't have unmount, so we just track it as unmounted
            del self.mounted_servers[name]
            self.logger.info("Unmounted server %s", name)
            return True
        return False
    
    async def mount_all_enabled(self):
        """Mount all enabled servers from config."""
        config = self.config_manager.load_config()
        enabled_servers = config.get_enabled_servers()
        
        if not enabled_servers:
            self.logger.info("No enabled servers to mount")
            return
        
        self.logger.info("Mounting %d enabled servers...", len(enabled_servers))
        
        results = []
        for name, server in enabled_servers.items():
            try:
                success = await self.mount_server(server)
                results.append((name, success))
            except Exception as e:
                self.logger.error("Error mounting %s: %s", name, e)
                results.append((name, False))
        
        # Log results
        successful = [name for name, success in results if success]
        failed = [name for name, success in results if not success]
        
        if successful:
            self.logger.info("Successfully mounted: %s", ', '.join(successful))
        if failed:
            self.logger.warning("Failed to mount: %s", ', '.join(failed))


class MAGGServer:
    """Main MAGG server with tools for managing other MCP servers."""
    
    def __init__(self, config_path: str | None = None):
        self.mcp = FastMCP(
            name="magg", 
            instructions=MAGG_INSTRUCTIONS
        )
        self.config_manager = ConfigManager(config_path)
        self.server_manager = ServerManager(self.mcp, self.config_manager)
        
        # Register tools
        self._register_tools()
    
    def _register_tools(self):
        """Register all MAGG management tools programmatically."""
        # Define tool mappings: (method_name, tool_name)
        tools = [
            (self.add_server, "magg_add_server"),
            (self.remove_server, "magg_remove_server"),
            (self.list_servers, "magg_list_servers"),
            (self.enable_server, "magg_enable_server"),
            (self.disable_server, "magg_disable_server"),
            (self.list_tools, "magg_list_tools"),
            (self.search_servers, "magg_search_servers"),
            (self.smart_configure, "magg_smart_configure"),
        ]
        
        # Register each tool with the MCP server
        for method, tool_name in tools:
            # FastMCP's @tool decorator can be applied programmatically
            self.mcp.tool(name=tool_name)(method)
            
        # Register resources
        self._register_resources()
        
        # Register prompts
        self._register_prompts()
        
        # Register the analyze_servers tool
        self.mcp.tool(name="magg_analyze_servers")(self.analyze_servers)
    
    def _register_resources(self):
        """Register MCP resources for server metadata."""
        # Define resource mappings: (method, uri_pattern)
        resources = [
            (self.get_server_metadata, "magg://server/{name}"),
            (self.get_all_servers_metadata, "magg://servers/all"),
        ]
        
        # Register each resource with the MCP server
        for method, uri_pattern in resources:
            self.mcp.resource(uri_pattern)(method)
    
    def _register_prompts(self):
        """Register MCP prompts for intelligent configuration."""
        # Define prompt mappings: (method, name)
        prompts = [
            (self.configure_server_prompt, "configure_server"),
        ]
        
        # Register each prompt with the MCP server
        for method, name in prompts:
            self.mcp.prompt(name)(method)

    @classmethod
    def _is_name_valid(cls, name: str) -> bool:
        return name.isidentifier()
    
    # ============================================================================
    # MCP Resource Methods - Expose server metadata for LLM consumption
    # ============================================================================
    
    async def get_server_metadata(self, name: str) -> str:
        """Expose server metadata as an MCP resource."""
        try:
            config = self.config_manager.load_config()
            if name in config.servers:
                server = config.servers[name]
                return json.dumps(server.model_dump(), indent=2)
            return json.dumps({"error": f"Server '{name}' not found"})
        except Exception as e:
            return json.dumps({"error": f"Failed to load server metadata: {str(e)}"})
    
    async def get_all_servers_metadata(self) -> str:
        """Expose all servers metadata as an MCP resource."""
        try:
            config = self.config_manager.load_config()
            servers_data = {
                name: server.model_dump() 
                for name, server in config.servers.items()
            }
            return json.dumps(servers_data, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to load servers metadata: {str(e)}"})
    
    # ============================================================================
    # MCP Prompt Methods - Templates for LLM-assisted configuration
    # ============================================================================
    
    async def configure_server_prompt(self, source: str, server_name: str | None = None) -> list[dict[str, str]]:
        """Generate a prompt for configuring a server from a URL."""
        messages = [
            {
                "role": "system",
                "content": "You are an expert at configuring MCP servers. Analyze the provided URL and generate optimal server configuration."
            },
            {
                "role": "user",
                "content": f"""Configure an MCP server for: {source}
                
Server name: {server_name or 'auto-generate'}

Please determine:
1. name: A string, potentially user provided (can be human-readable)
2. prefix: A valid Python identifier (no underscores)
3. command: The full command to run (e.g., "python server.py", "npx @playwright/mcp@latest", or null for HTTP)
4. uri: For HTTP servers (if applicable)
5. working_dir: If needed
6. env: Environment variables as an object (if needed)
7. notes: Helpful setup instructions
8. transport: Any transport-specific configuration (optional dict)

Consider the URL type:
- GitHub repos may need cloning and setup
- NPM packages use npx
- Python packages may use uvx or python -m
- HTTP/HTTPS URLs may be direct MCP servers
                """
            }
        ]
        return messages
    
    # ============================================================================
    # MCP Tool Methods - Core server management functionality
    # ============================================================================

    async def add_server(
        self,
        name: str,
        source: str,
        prefix: str | None = None,
        command: str | None = None,
        uri: str | None = None,
        env_vars: dict[str, str] | None = None,
        working_dir: str | None = None,
        notes: str | None = None,
        enable: bool | None = None,
        transport: dict[str, Any] | None = None,
    ) -> MAGGResponse:
        """Add a new MCP server.
        
        Args:
            name: Unique server name
            source: URL of the server package/repository
            prefix: Tool prefix (defaults to conformed server name)
            command: Full command to run (e.g., "python server.py", "npx @playwright/mcp@latest")
            uri: URI for HTTP servers
            env_vars: Environment variables
            working_dir: Working directory (required for commands)
            notes: Setup notes
            enable: Whether to enable the server immediately (default: True)
            transport: Transport-specific configuration (optional)
        """
        try:
            config = self.config_manager.load_config()
            
            if name in config.servers:
                return MAGGResponse.error(f"Server '{name}' already exists")
            
            # Split command into command and args if needed
            actual_command = command
            actual_args = None
            if command:
                import shlex
                parts = shlex.split(command)
                if len(parts) > 1:
                    actual_command = parts[0]
                    actual_args = parts[1:]
                elif len(parts) == 1:
                    actual_command = parts[0]
                    actual_args = None
            
            # Validate working directory for command servers
            if actual_command and working_dir:
                validated_dir, error = validate_working_directory(working_dir, source)
                if error:
                    return MAGGResponse.error(error)
                working_dir = str(validated_dir)
            
            # Create server config
            try:
                server = ServerConfig(
                    name=name,
                    source=source,
                    prefix=prefix or "",  # Will be auto-generated from name
                    command=actual_command,
                    args=actual_args,
                    uri=uri,
                    env=env_vars,
                    working_dir=working_dir,
                    notes=notes,
                    enabled=enable if enable is not None else True,
                    transport=transport or {},
                )
            except ValueError as e:
                return MAGGResponse.error(str(e))
            
            # Try to mount immediately if enabled
            mount_success = True
            if server.enabled:  # Use the server's enabled flag, not the parameter
                mount_success = await self.server_manager.mount_server(server)
                if not mount_success:
                    return MAGGResponse.error(f"Failed to mount server '{name}'")
            
            # Save to config
            config.add_server(server)
            self.config_manager.save_config(config)
            
            return MAGGResponse.success({
                "action": "server_added",
                "server": {
                    "name": name,
                    "source": source,
                    "prefix": server.prefix,
                    "command": command,  # Return original command string
                    "uri": uri,
                    "working_dir": working_dir,
                    "notes": notes,
                    "enabled": server.enabled,
                    "mounted": mount_success
                }
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to add server: {str(e)}")
    
    async def remove_server(self, name: str) -> MAGGResponse:
        """Remove a server."""
        try:
            config = self.config_manager.load_config()
            
            if config.remove_server(name):
                await self.server_manager.unmount_server(name)
                self.config_manager.save_config(config)
                return MAGGResponse.success({
                    "action": "server_removed",
                    "server": {"name": name}
                })
            else:
                return MAGGResponse.error(f"Server '{name}' not found")
                
        except Exception as e:
            return MAGGResponse.error(f"Failed to remove server: {str(e)}")
    
    async def list_servers(self) -> MAGGResponse:
        """List all configured servers."""
        try:
            config = self.config_manager.load_config()
            
            servers = []
            for name, server in config.servers.items():
                server_data = {
                    "name": name,
                    "source": server.source,
                    "prefix": server.prefix,
                    "enabled": server.enabled,
                    "mounted": name in self.server_manager.mounted_servers,
                }
                
                # Add optional fields only if present
                if server.command:
                    # Reconstruct full command for display
                    if server.args:
                        server_data["command"] = f"{server.command} {' '.join(server.args)}"
                    else:
                        server_data["command"] = server.command
                if server.uri:
                    server_data["uri"] = server.uri
                if server.working_dir:
                    server_data["working_dir"] = server.working_dir
                if server.notes:
                    server_data["notes"] = server.notes
                
                servers.append(server_data)
            
            return MAGGResponse.success({
                "servers": servers,
                "total": len(servers)
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list servers: {str(e)}")
    
    async def enable_server(self, name: str) -> MAGGResponse:
        """Enable a server."""
        try:
            config = self.config_manager.load_config()
            
            if name not in config.servers:
                return MAGGResponse.error(f"Server '{name}' not found")
            
            server = config.servers[name]
            server.enabled = True
            
            # Try to mount it
            success = await self.server_manager.mount_server(server)
            
            self.config_manager.save_config(config)
            
            return MAGGResponse.success({
                "action": "server_enabled",
                "server": {"name": name},
                "mounted": success
            })
                
        except Exception as e:
            return MAGGResponse.error(f"Failed to enable server: {str(e)}")
    
    async def disable_server(self, name: str) -> MAGGResponse:
        """Disable a server."""
        try:
            config = self.config_manager.load_config()
            
            if name not in config.servers:
                return MAGGResponse.error(f"Server '{name}' not found")
            
            server = config.servers[name]
            server.enabled = False
            
            # Unmount if mounted
            await self.server_manager.unmount_server(name)
            
            self.config_manager.save_config(config)
            return MAGGResponse.success({
                "action": "server_disabled",
                "server": {"name": name}
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to disable server: {str(e)}")
    
    async def list_tools(self) -> MAGGResponse:
        """List all available tools from mounted servers."""
        try:
            tools = await self.mcp.get_tools()
            
            # Group by prefix
            by_prefix = {}
            for tool_name in tools.keys():
                if '_' in tool_name and not tool_name.startswith('magg_'):
                    prefix = tool_name.split('_', 1)[0]
                else:
                    prefix = 'magg'
                
                if prefix not in by_prefix:
                    by_prefix[prefix] = []
                by_prefix[prefix].append(tool_name)
            
            # Convert to structured format
            tool_groups = []
            for prefix, prefix_tools in sorted(by_prefix.items()):
                tool_groups.append({
                    "prefix": prefix,
                    "tools": sorted(prefix_tools),
                    "count": len(prefix_tools)
                })
            
            return MAGGResponse.success({
                "tool_groups": tool_groups,
                "total_tools": len(tools)
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list tools: {str(e)}")
    
    async def smart_configure(
        self, 
        source: str,
        server_name: str | None = None,
        ctx: Context | None = None
    ) -> MAGGResponse:
        """Use LLM sampling to intelligently configure a server from a URL.
        
        Args:
            source: URL of the server package/repository
            server_name: Optional server name (auto-generated if not provided)
            ctx: MCP context for sampling
        """
        try:
            # First, collect metadata about the URL
            from .discovery.metadata import SourceMetadataCollector
            collector = SourceMetadataCollector()
            
            metadata_entries = await collector.collect_metadata(source, server_name)
            
            # Build a comprehensive prompt with metadata
            metadata_summary = []
            for entry in metadata_entries:
                source = entry.get("source", "unknown")
                data = entry.get("data", {})
                
                if source == "github" and data:
                    metadata_summary.append(f"GitHub: {data.get('description', 'No description')}")
                    metadata_summary.append(f"Language: {data.get('language', 'Unknown')}")
                    metadata_summary.append(f"Stars: {data.get('stars', 0)}")
                    if data.get("setup_instructions"):
                        metadata_summary.append("Setup hints found in README")
                        
                elif source == "filesystem" and data.get("exists"):
                    if data.get("is_directory"):
                        metadata_summary.append(f"Project type: {data.get('project_type', 'unknown')}")
                        if data.get("setup_hints"):
                            metadata_summary.append(f"Setup commands: {', '.join(data['setup_hints'])}")
                            
                elif source == "http_check" and data.get("is_mcp_server"):
                    metadata_summary.append("Direct MCP server detected via HTTP")
            
            # If no context, return basic metadata-based configuration
            if not ctx:
                # Try to auto-configure based on metadata
                config_suggestion = {
                    "name": server_name or Path(source).stem.replace('-', '').replace('_', ''),
                    "source": source
                }
                
                # Detect command based on metadata
                for entry in metadata_entries:
                    data = entry.get("data", {})
                    if entry.get("source") == "filesystem" and data.get("project_type"):
                        project_type = data["project_type"]
                        if project_type == "nodejs_project":
                            config_suggestion["command"] = "npx"
                            config_suggestion["args"] = [server_name or Path(source).stem]
                        elif project_type == "python_project":
                            config_suggestion["command"] = "python"
                            config_suggestion["args"] = ["-m", server_name or Path(source).stem]
                
                return MAGGResponse.success({
                    "action": "metadata_based_config",
                    "metadata": metadata_summary,
                    "suggested_config": config_suggestion
                })
            
            # Build enhanced prompt with metadata
            prompt = f"""Configure an MCP server for: {source}

source: The source url or URI of this server. Can be a GitHub repo, Glama listing, website, or local filesystem path.

Server name: {server_name or '<auto-generate>'}

Collected metadata:
{chr(10).join(f"- {item}" for item in metadata_summary)}

Based on this metadata, please generate a complete JSON configuration with:
0. source: (as above)
1. name: A string (human-readable, can contain any characters)
2. prefix: A valid Python identifier (no underscores)
3. command: The appropriate command (python, node, npx, uvx, or null for HTTP)
4. args: Required arguments as an array
5. uri: For HTTP servers (if applicable)
6. working_dir: If needed
7. env: Environment variables as an object (if needed)
8. notes: Helpful setup instructions
9. transport: Any transport-specific configuration (optional dict)

Return ONLY valid JSON, no explanations."""

            # Sample from the LLM using simple string format
            result = await ctx.sample(
                messages=prompt,
                max_tokens=1000
            )
            
            if not result or not result.text:
                return MAGGResponse.error("Failed to get configuration from LLM")
            
            # Try to parse the response as JSON
            try:
                # Extract JSON from the response
                import re
                json_match = re.search(r'\{.*\}', result.text, re.DOTALL)
                if not json_match:
                    return MAGGResponse.error("No valid JSON configuration found in LLM response")
                
                config_data = json.loads(json_match.group())
                
                # Add the server with the generated configuration
                add_result = await self.add_server(
                    name=config_data.get("name", server_name or "generated"),
                    source=source,
                    prefix=config_data.get("prefix"),
                    command=config_data.get("command"),
                    args=config_data.get("args"),
                    uri=config_data.get("uri"),
                    env_vars=config_data.get("env"),
                    working_dir=config_data.get("working_dir"),
                    notes=config_data.get("notes")
                )
                
                if add_result.is_success:
                    return MAGGResponse.success({
                        "action": "smart_configured",
                        "server": add_result.output["server"],
                        "llm_config": config_data
                    })
                else:
                    return add_result
                    
            except json.JSONDecodeError as e:
                return MAGGResponse.error(f"Failed to parse LLM configuration: {str(e)}")
                
        except Exception as e:
            return MAGGResponse.error(f"Smart configuration failed: {str(e)}")
    
    async def search_servers(self, query: str, limit: int = 5) -> MAGGResponse:
        """Search for MCP servers online."""
        try:
            from .discovery.catalog import CatalogManager
            catalog = CatalogManager()
            
            results = await catalog.search_only(query, limit)
            
            # Convert search results to structured format
            search_results = []
            for source, items in results.items():
                for item in items:
                    result_data = {
                        "source": source,
                        "name": item.name,
                        "description": item.description
                    }
                    if item.url:
                        result_data["url"] = item.url
                    if hasattr(item, 'install_command') and item.install_command:
                        result_data["install_command"] = item.install_command
                    search_results.append(result_data)
            
            return MAGGResponse.success({
                "query": query,
                "results": search_results,
                "total": len(search_results)
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to search servers: {str(e)}")
    
    async def analyze_servers(self, ctx: Context | None = None) -> MAGGResponse:
        """Analyze configured servers and provide insights using LLM.
        
        Args:
            ctx: MCP context for sampling
        """
        try:
            config = self.config_manager.load_config()
            
            if not config.servers:
                return MAGGResponse.success({
                    "analysis": "No servers configured yet. Use magg_add_server to add servers."
                })
            
            # Build analysis data
            analysis_data = {
                "total_servers": len(config.servers),
                "enabled_servers": len(config.get_enabled_servers()),
                "mounted_servers": len(self.server_manager.mounted_servers),
                "servers": {}
            }
            
            for name, server in config.servers.items():
                server_info = {
                    "source": server.source,
                    "enabled": server.enabled,
                    "mounted": name in self.server_manager.mounted_servers,
                    "command": server.command,
                    "uri": server.uri,
                    "prefix": server.prefix,
                    "notes": server.notes
                }
                analysis_data["servers"][name] = server_info
            
            # If context available, use LLM for insights
            if ctx:
                prompt = f"""Analyze this MAGG server configuration and provide insights:

{json.dumps(analysis_data, indent=2)}

Please provide:
1. Overview of the current setup
2. Any potential issues or conflicts
3. Suggestions for optimization
4. Missing capabilities that could be added"""

                # Use simple string sampling
                result = await ctx.sample(
                    messages=prompt,
                    max_tokens=1000
                )
                
                if result and result.text:
                    analysis_data["insights"] = result.text
            
            return MAGGResponse.success(analysis_data)
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to analyze servers: {str(e)}")
    
    async def setup(self):
        """Initialize MAGG and mount existing servers."""
        await self.server_manager.mount_all_enabled()
    
    async def run_stdio(self):
        """Run MAGG in stdio mode."""
        # Don't call setup() here - it's already called by ServerRunner
        await self.mcp.run_stdio_async()
    
    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run MAGG in HTTP mode."""
        # Don't call setup() here - it's already called by ServerRunner
        await self.mcp.run_http_async(host=host, port=port)
