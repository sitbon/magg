"""MAGG - MCP Aggregator Server - Clean Class-Based Implementation"""

import json
import logging
import os
from functools import cached_property, wraps
from typing import Any, Annotated, TypeAlias
from pathlib import Path

from fastmcp import FastMCP, Client, Context
from mcp.types import PromptMessage, TextContent, EmbeddedResource, Resource, TextResourceContents, Annotations
from pydantic import Field, AnyUrl

from ..settings import ConfigManager, ServerConfig, MAGGConfig
from ..response import MAGGResponse
from ..util import (
    get_transport_for_command, 
    get_transport_for_uri,
    validate_working_directory,
    TRANSPORT_DOCS,
)

from .defaults import MAGG_INSTRUCTIONS

JSONToolResponse: TypeAlias = TextContent | EmbeddedResource


class ServerManager:
    """Manages MCP servers - mounting, unmounting, and tracking."""
    config_manager: ConfigManager
    mcp: FastMCP
    mounted_servers: dict
    logger: logging.Logger
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.mcp = FastMCP(
            name=self.self_prefix,
            instructions=MAGG_INSTRUCTIONS.format(self_prefix=self.self_prefix),
        )
        self.mounted_servers = {}
        self.logger = logging.getLogger(__name__)
    
    @property
    def config(self) -> MAGGConfig:
        """Get the current MAGG configuration."""
        return self.config_manager.load_config()

    def save_config(self, config: MAGGConfig):
        """Save the current configuration to disk."""
        return self.config_manager.save_config(config)

    @cached_property
    def self_prefix(self) -> str:
        """Get the self prefix for this MAGG server - cannot be changed during process lifetime."""
        return self.config.self_prefix
    
    async def mount_server(self, server: ServerConfig) -> bool:
        """Mount a server using FastMCP."""
        if not server.enabled:
            self.logger.info("Server %s is disabled, skipping mount", server.name)
            return False

        if server.name in self.mounted_servers:
            self.logger.warning("Server %s is already mounted, skipping", server.name)
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
            self.mcp.mount(server.prefix, proxy_server, as_proxy=True)
            # Store both proxy and client for resource/prompt access
            self.mounted_servers[server.name] = {
                'proxy': proxy_server,
                'client': client
            }
            
            self.logger.debug("Mounted server %s with prefix %s", server.name, server.prefix)
            return True
        
        except Exception as e:
            self.logger.error("Failed to mount server %s: %s", server.name, e)
            return False
    
    async def unmount_server(self, name: str) -> bool:
        """Unmount a server."""
        if name in self.mounted_servers:
            # Get the server config to find the prefix
            config = self.config
            server = config.servers.get(name)
            if server and server.prefix in self.mcp._mounted_servers:
                # Properly unmount from FastMCP
                self.mcp.unmount(server.prefix)
                self.logger.debug("Called unmount for prefix %s", server.prefix)
            
            # Remove from our tracking
            del self.mounted_servers[name]
            self.logger.info("Unmounted server %s", name)
            return True

        else:
            self.logger.warning("Server %s is not mounted, cannot unmount", name)
            return False
    
    async def mount_all_enabled(self):
        """Mount all enabled servers from config."""
        config = self.config
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
    _is_setup = False
    server_manager: ServerManager
    logger: logging.Logger
    
    def __init__(self, config_path: str | None = None):
        self.server_manager = ServerManager(ConfigManager(config_path))
        self.logger = logging.getLogger(__name__)
        self._register_tools()

    @property
    def is_setup(self) -> bool:
        """Check if the server is fully set up with tools and resources."""
        return self._is_setup
    
    @property
    def mcp(self) -> FastMCP:
        return self.server_manager.mcp

    @property
    def config(self) -> MAGGConfig:
        """Get the current MAGG configuration."""
        return self.server_manager.config

    @property
    def self_prefix(self) -> str:
        """Get the self prefix for this MAGG server."""
        return self.server_manager.self_prefix

    def save_config(self, config: MAGGConfig):
        """Save the current configuration to disk."""
        return self.server_manager.save_config(config)

    def _register_tools(self):
        """Register all MAGG management tools programmatically."""
        self_prefix = self.self_prefix
        
        tools = [
            (self.add_server, f"{self_prefix}_add_server", None),
            (self.remove_server, f"{self_prefix}_remove_server", None),
            (self.list_servers, f"{self_prefix}_list_servers", None),
            (self.enable_server, f"{self_prefix}_enable_server", None),
            (self.disable_server, f"{self_prefix}_disable_server", None),
            (self.list_tools, f"{self_prefix}_list_tools", None),
            (self.list_resources, f"{self_prefix}_list_resources", None),
            (self.get_resource, f"{self_prefix}_get_resource", None),
            (self.list_prompts, f"{self_prefix}_list_prompts", None),
            (self.search_servers, f"{self_prefix}_search_servers", None),
            (self.smart_configure, f"{self_prefix}_smart_configure", None),
            (self.analyze_servers, f"{self_prefix}_analyze_servers", None),
        ]

        def call_tool_wrapper(func):
            @wraps(func)
            async def wrapper(*args, **kwds):
                result = await func(*args, **kwds)

                if isinstance(result, MAGGResponse):
                    return result.as_json_text_content

                return result

            return wrapper

        for method, tool_name, options in tools:
            # FastMCP's @tool decorator can be applied programmatically
            self.mcp.tool(name=tool_name, **(options or {}))(call_tool_wrapper(method))
            
        # Register resources
        self._register_resources(self_prefix)
        
        # Register prompts
        self._register_prompts(self_prefix)
    
    def _register_resources(self, self_prefix: str):
        """Register MCP resources for server metadata."""
        # Define resource mappings: (method, uri_pattern)
        resources = [
            (self.get_server_metadata, f"{self_prefix}://server/{{name}}"),
            (self.get_all_servers_metadata, f"{self_prefix}://servers/all"),
        ]
        
        # Register each resource with the MCP server
        for method, uri_pattern in resources:
            self.mcp.resource(
                uri=uri_pattern,
                mime_type="application/json",
            )(method)
    
    def _register_prompts(self, self_prefix: str):
        """Register MCP prompts for intelligent configuration."""
        # Define prompt mappings: (method, name)
        prompts = [
            (self.configure_server_prompt, f"{self_prefix}_configure_server"),
        ]
        
        # Register each prompt with the MCP server
        for method, name in prompts:
            self.mcp.prompt(name)(method)

    # ============================================================================
    # MCP Resource Methods - Expose server metadata for LLM consumption
    # ============================================================================
    
    async def get_server_metadata(self, name: str) -> dict:
        """Expose server metadata as an MCP resource."""
        config = self.config

        if name in config.servers:
            server = config.servers[name]
            return server.model_dump(exclude_none=True, exclude_defaults=True, exclude_unset=True, by_alias=True)

        raise ValueError(f"Server '{name}' not found in configuration")

    async def get_all_servers_metadata(self) -> dict[str, dict]:
        """Expose all servers metadata as an MCP resource."""
        config = self.config

        return {
            name: server.model_dump(
                exclude_none=True,
                exclude_defaults=True,
                exclude_unset=True,
                by_alias=True
            )
            for name, server in config.servers.items()
        }
    
    # ============================================================================
    # region MCP Prompt Methods - Templates for LLM-assisted configuration
    # ============================================================================
    
    def _format_metadata_for_prompt(self, metadata_entries: list[dict]) -> str:
        """Format metadata entries into a readable string for prompts."""
        lines = []
        for entry in metadata_entries:
            source = entry.get("source", "unknown")
            data = entry.get("data", {})
            
            if source == "github" and data:
                lines.append(f"- GitHub Repository: {data.get('description', 'No description')}")
                lines.append(f"  Language: {data.get('language', 'Unknown')}")
                lines.append(f"  Stars: {data.get('stars', 0)}")
                if data.get("setup_instructions"):
                    lines.append("  Setup instructions found in README")
                    
            elif source == "filesystem" and data.get("exists"):
                if data.get("is_directory"):
                    lines.append(f"- Local Project: {data.get('project_type', 'unknown')} project")
                    if data.get("setup_hints"):
                        lines.append(f"  Setup commands: {', '.join(data['setup_hints'])}")
                        
            elif source == "http_check" and data.get("is_mcp_server"):
                lines.append("- Direct MCP server endpoint detected (HTTP/SSE)")
                
            elif source == "npm" and data:
                lines.append(f"- NPM Package: {data.get('name', 'Unknown')}")
                if data.get("description"):
                    lines.append(f"  Description: {data['description']}")
                    
        return "\n".join(lines) if lines else "No metadata available"
    
    async def configure_server_prompt(
        self,
        source: Annotated[str, Field(description="URL of the server to configure")],
        server_name: Annotated[str | None, Field(description="Optional server name")] = None,
    ) -> list[dict[str, str]]:
        """Generate an enriched prompt template for configuring a server from a URL.
        
        This prompt can be used with any LLM to generate server configuration.
        For automatic configuration with LLM sampling, use the smart_configure tool instead.
        """
        # Collect metadata to enrich the prompt
        from ..discovery.metadata import SourceMetadataCollector
        collector = SourceMetadataCollector()
        
        try:
            metadata_entries = await collector.collect_metadata(source, server_name)
            metadata_info = self._format_metadata_for_prompt(metadata_entries)
        except Exception:
            metadata_info = "Unable to collect metadata"

        messages = []

        system_message = PromptMessage(
            role="assistant",
            content=TextContent(
                type="text",
                text="You are an expert at configuring MCP servers. Analyze the provided URL and metadata to generate optimal server configuration."
            ),
        )

        messages.append(system_message)

        user_prompt = f"""Configure an MCP server for: {source}
                
Server name: {server_name or 'auto-generate'}

Collected Metadata:
{metadata_info}

Please determine the following configuration:
1. name: A string, potentially user provided (can be human-readable)
2. prefix: A valid Python identifier (no underscores)
3. command: The full command to run (e.g., "python server.py", "npx @playwright/mcp@latest", or null for HTTP)
4. uri: For HTTP servers (if applicable)
5. working_dir: If needed
6. env_vars: Environment variables as an object (if needed)
7. notes: Helpful setup instructions
8. transport: Any transport-specific configuration (optional dict)

Consider the URL type and metadata:
- GitHub repos may need cloning and setup
- NPM packages use npx
- Python packages may use uvx or python -m
- HTTP/HTTPS URLs may be direct MCP servers

Return the configuration as a JSON object."""

        messages.append(
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=user_prompt,
                ),
            )
        )

        return messages

    # ============================================================================
    # region MCP Tool Methods - Core server management functionality
    # ============================================================================

    async def add_server(
        self,
        name: Annotated[str, Field(description="Unique server name")],
        source: Annotated[str, Field(description="URL of the server package/repository")],
        prefix: Annotated[str | None, Field(description="Tool prefix (defaults to conformed server name)")] = None,
        command: Annotated[str | None, Field(
            description="Full command to run (e.g., 'python server.py', 'npx @playwright/mcp@latest')"
        )] = None,
        uri: Annotated[str | None, Field(description="URI for HTTP servers")] = None,
        env_vars: Annotated[dict[str, str] | None, Field(description="Environment variables")] = None,
        working_dir: Annotated[str | None, Field(description="Working directory (for commands)")] = None,
        notes: Annotated[str | None, Field(description="Setup notes")] = None,
        enable: Annotated[bool | None, Field(description="Whether to enable the server immediately (default: True)")] = True,
        transport: Annotated[dict[str, Any] | None, Field(
            description=f"Transport-specific configuration (optional){TRANSPORT_DOCS}"
        )] = None,
    ) -> MAGGResponse:
        """Add a new MCP server."""
        try:
            config = self.config

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
            self.save_config(config)

            return MAGGResponse.success({
                "action": "server_added",
                "server": {
                    "name": name,
                    "source": source,
                    "prefix": server.prefix,
                    "command": command,
                    "uri": uri,
                    "working_dir": working_dir,
                    "notes": notes,
                    "enabled": server.enabled,
                    "mounted": mount_success
                }
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to add server: {str(e)}")

    async def remove_server(
        self,
        name: Annotated[str, Field(description="Server name to remove")],
    ) -> MAGGResponse:
        """Remove a server."""
        try:
            config = self.config
            
            if name in config.servers:
                await self.server_manager.unmount_server(name)
                config.remove_server(name)
                self.save_config(config)
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
            config = self.config
            
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
    
    async def enable_server(
        self,
        name: Annotated[str, Field(description="Server name to enable")],
    ) -> MAGGResponse:
        """Enable a server."""
        try:
            config = self.config
            
            if name not in config.servers:
                return MAGGResponse.error(f"Server '{name}' not found")

            server = config.servers[name]

            if server.enabled:
                return MAGGResponse.error(f"Server '{name}' is already enabled")

            server.enabled = True
            
            # Try to mount it
            success = await self.server_manager.mount_server(server)
            
            self.save_config(config)
            
            return MAGGResponse.success({
                "action": "server_enabled",
                "server": {"name": name},
                "mounted": success
            })
                
        except Exception as e:
            return MAGGResponse.error(f"Failed to enable server: {str(e)}")
    
    async def disable_server(
        self,
        name: Annotated[str, Field(description="Server name to disable")],
    ) -> MAGGResponse:
        """Disable a server."""
        try:
            config = self.config
            
            if name not in config.servers:
                return MAGGResponse.error(f"Server '{name}' not found")
            
            server = config.servers[name]

            if not server.enabled:
                return MAGGResponse.error(f"Server '{name}' is already disabled")

            server.enabled = False
            
            # Unmount if mounted
            await self.server_manager.unmount_server(name)
            
            self.save_config(config)
            return MAGGResponse.success({
                "action": "server_disabled",
                "server": {"name": name}
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to disable server: {str(e)}")
    
    async def list_tools(self) -> MAGGResponse:
        """List all available tools from mounted servers."""
        try:
            config = self.config
            tools_by_server = {}
            total_tools = 0
            
            # Get tools from each mounted server
            for server_name, server_info in self.server_manager.mounted_servers.items():
                client = server_info['client']
                server_config = config.servers.get(server_name)
                
                if not server_config:
                    continue
                    
                try:
                    # Get tools directly from the client
                    async with client as conn:
                        tools = await conn.list_tools()
                        tool_names = [tool.name for tool in tools]
                        
                        # Add prefix to tool names
                        prefixed_tools = [f"{server_config.prefix}_{name}" for name in tool_names]
                        
                        tools_by_server[server_name] = {
                            "prefix": server_config.prefix,
                            "tools": sorted(prefixed_tools)
                        }
                        total_tools += len(prefixed_tools)
                        
                except Exception as e:
                    self.logger.warning("Failed to get tools from server %s: %s", server_name, e)
                    tools_by_server[server_name] = {
                        "prefix": server_config.prefix,
                        "tools": [],
                        "error": str(e)
                    }
            
            # Add MAGG's own tools
            magg_tools = []
            all_tools = await self.mcp.get_tools()
            for tool_name in all_tools.keys():
                if tool_name.startswith(f'{self.self_prefix}_'):
                    magg_tools.append(tool_name)
            
            if magg_tools:
                tools_by_server[self.self_prefix] = {
                    "prefix": self.self_prefix,
                    "tools": sorted(magg_tools)
                }
                total_tools += len(magg_tools)
            
            return MAGGResponse.success({
                "servers": tools_by_server,
                "total_tools": total_tools,
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list tools: {str(e)}")
    
    async def smart_configure(
        self,
        source: Annotated[str, Field(description="URL of the server package/repository")],
        server_name: Annotated[str | None, Field(
            description="Optional server name (auto-generated if not provided)"
        )] = None,
        ctx: Context | None = None,
    ) -> MAGGResponse:
        """Use LLM sampling to intelligently configure and add a server from a URL.
        
        This tool performs the complete workflow:
        1. Collects metadata about the source URL
        2. Uses LLM sampling (if context provided) to generate optimal configuration
        3. Automatically adds the server to your configuration
        
        Note: This requires an LLM context for intelligent configuration.
        Without LLM context, it falls back to basic metadata-based heuristics.
        For generating configuration prompts without sampling, use configure_server_prompt.
        """
        try:
            # First, collect metadata about the URL
            from ..discovery.metadata import SourceMetadataCollector
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
            
            # Build enhanced prompt with metadata for LLM sampling
            prompt = f"""You are being asked by the MAGG smart_configure tool to analyze metadata and generate an optimal MCP server configuration.

Configure an MCP server for: {source}

Server name requested: {server_name or '<auto-generate based on source>'}

=== METADATA COLLECTED ===
{os.linesep.join(f"- {item}" for item in metadata_summary) if metadata_summary else "No metadata available"}

=== TASK ===
Based on the URL and metadata above, generate a complete JSON configuration that will be automatically added to the user's MAGG server configuration.

Required fields:
1. name: A human-readable string (can contain any characters)
2. prefix: A valid Python identifier for tool prefixing (no underscores)
3. command: The appropriate command (python, node, npx, uvx, or null for HTTP/SSE servers)
4. uri: For HTTP/SSE servers (if applicable)
5. working_dir: If needed
6. env_vars: Environment variables as an object (if needed)
7. notes: Helpful setup instructions for the user
8. transport: Any transport-specific configuration (optional dict)

Return ONLY valid JSON, no explanations or markdown formatting."""

            # Perform LLM sampling to generate the configuration
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
                json_match = re.search(r'{.*}', result.text, re.DOTALL)
                if not json_match:
                    return MAGGResponse.error("No valid JSON configuration found in LLM response")
                
                config_data = json.loads(json_match.group())
                
                # Add the server with the generated configuration
                add_result = await self.add_server(
                    name=config_data.get("name", server_name or "generated"),
                    source=source,
                    prefix=config_data.get("prefix"),
                    command=config_data.get("command"),
                    uri=config_data.get("uri"),
                    env_vars=config_data.get("env_vars"),
                    working_dir=config_data.get("working_dir"),
                    notes=config_data.get("notes"),
                    enable=config_data.get("enabled"),
                    transport=config_data.get("transport"),
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
    
    async def search_servers(
        self,
        query: Annotated[str, Field(description="Search query for MCP servers")],
        limit: Annotated[int, Field(description="Maximum number of results to return")] = 5,
    ) -> MAGGResponse:
        """Search for MCP servers online."""
        try:
            from ..discovery.catalog import CatalogManager
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
    
    async def list_resources(
        self,
        name: Annotated[str | None, Field(description="Optional server name to filter by")] = None,
        prefix: Annotated[str | None, Field(description="Optional prefix to filter by")] = None,
    ) -> MAGGResponse:
        """List all available resources from mounted servers."""
        try:
            resources_by_server = {}
            
            # First, add MAGG's own resources
            resources = []

            for uri_pattern, method in [
                (f"{self.self_prefix}://servers/all", self.get_all_servers_metadata),
                (f"{self.self_prefix}://server/{{name}}", self.get_server_metadata),
            ]:
                resources.append({
                    "uri": uri_pattern,
                    "name": uri_pattern.split("/")[-1],
                    "description": method.__doc__.strip() if method.__doc__ else "",
                    "mimeType": "application/json"
                })
            
            if not prefix or prefix == self.self_prefix:
                resources_by_server[self.self_prefix] = {
                    "server_name": self.self_prefix,
                    "prefix": self.self_prefix,
                    "resources": resources,
                    "resource_templates": []
                }
            
            # Then add resources from mounted servers
            config = self.config
            
            for server_name, mount_info in self.server_manager.mounted_servers.items():
                server = config.servers.get(server_name)
                if not server:
                    continue
                    
                # Apply filters
                if name and server_name != name:
                    continue
                if prefix and server.prefix != prefix:
                    continue
                
                server_resources = []
                server_templates = []
                
                # Use the proxy server to get resources
                proxy = mount_info['proxy']
                try:
                    # Get regular resources
                    resources_dict = await proxy.get_resources()
                    for resource_uri, resource in resources_dict.items():
                        resource_data = {
                            "uri": resource_uri,
                            "name": resource.name or resource_uri.split("/")[-1],
                            "mimeType": resource.mime_type or "application/json"
                        }
                        if resource.description:
                            resource_data["description"] = resource.description
                        server_resources.append(resource_data)
                    
                    # Get template resources
                    templates_dict = await proxy.get_resource_templates()
                    for template_uri, template in templates_dict.items():
                        template_data = {
                            "uriTemplate": template_uri,
                            "name": template.name or template_uri.split("/")[-1],
                            "mimeType": template.mime_type or "application/json"
                        }
                        if template.description:
                            template_data["description"] = template.description
                        server_templates.append(template_data)
                        
                except Exception as e:
                    self.server_manager.logger.warning("Failed to list resources for %s: %s", server_name, e)
                    continue
                
                if server_resources or server_templates:
                    resources_by_server[server_name] = {
                        "server_name": server_name,
                        "prefix": server.prefix,
                        "resources": server_resources,
                        "resource_templates": server_templates
                    }
            
            return MAGGResponse.success({
                "servers": resources_by_server,
                "total_servers": len(resources_by_server),
                "total_resources": sum(len(s["resources"]) + len(s["resource_templates"]) 
                                     for s in resources_by_server.values())
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list resources: {str(e)}")

    async def get_resource(
        self,
        uri: Annotated[AnyUrl, Field(description="The resource URI or URI template")],
        prefix: Annotated[str | None, Field(description="Optional server prefix to filter by")] = None,
        name: Annotated[str | None, Field(description="Optional server name to filter by")] = None,
    ) -> MAGGResponse:
        """Get a specific resource from an MCP server."""
        try:
            # Check if it's a MAGG resource
            if uri.scheme == self.self_prefix and name in {None, self.self_prefix}:
                return await self.mcp._read_resource()
                # if uri.path == "/servers/all":
                #     content = await self.get_all_servers_metadata()
                #
                # elif uri.path.startswith("/server/"):
                #     server_name = uri.path.split("/")[-1]
                #     content = await self.get_server_metadata(server_name)
                # else:
                #     return MAGGResponse.error(f"Unknown {self.self_prefix} resource: {uri}")
                #
                # return MAGGResponse.success({
                #     "uri": uri,
                #     "mimeType": "application/json",
                #     "contentType": "structured",
                #     "content": content
                # })

            # Otherwise, look for the resource in mounted servers
            config = self.config

            for server_name, mount_info in self.server_manager.mounted_servers.items():
                server = config.servers.get(server_name)
                if not server:
                    continue

                # Apply filters
                if name and server_name != name:
                    continue
                if prefix and server.prefix != prefix:
                    continue

                client: Client = mount_info['client']

                try:
                    async with client:
                        # Try to read the resource
                        try:
                            result = await client.read_resource(uri)

                            # Extract content based on result type
                            # First check if it's a list (common return type)
                            if isinstance(result, list) and len(result) > 0:
                                # Take the first item from the list
                                content_item = result[0]
                                if hasattr(content_item, 'text'):
                                    content_str = content_item.text
                                elif hasattr(content_item, 'blob'):
                                    import base64
                                    content_str = base64.b64encode(content_item.blob).decode('utf-8')
                                else:
                                    content_str = str(content_item)
                            elif hasattr(result, 'contents'):
                                # Handle ResourceResponse with contents list
                                if result.contents and len(result.contents) > 0:
                                    content = result.contents[0]
                                    if hasattr(content, 'text'):
                                        content_str = content.text
                                    elif hasattr(content, 'blob'):
                                        # For binary content, we might want to base64 encode
                                        import base64
                                        content_str = base64.b64encode(content.blob).decode('utf-8')
                                    else:
                                        content_str = str(content)
                                else:
                                    content_str = ""
                            elif hasattr(result, 'text'):
                                content_str = result.text
                            elif hasattr(result, 'blob'):
                                import base64
                                content_str = base64.b64encode(result.blob).decode('utf-8')
                            else:
                                content_str = str(result)

                            # Determine actual mime type and content type from result
                            mime_type = "application/json"
                            content_type = "text"

                            # Check if result is a list
                            if isinstance(result, list) and len(result) > 0:
                                content_item = result[0]
                                if hasattr(content_item, 'mimeType') and content_item.mimeType:
                                    mime_type = content_item.mimeType
                                elif hasattr(content_item, 'blob'):
                                    content_type = "base64"
                            elif hasattr(result, 'contents') and result.contents:
                                content = result.contents[0]
                                if hasattr(content, 'mimeType') and content.mimeType:
                                    mime_type = content.mimeType

                            # Determine content type based on mime type
                            if mime_type.startswith("text/"):
                                content_type = "text"
                            elif mime_type.startswith("image/"):
                                content_type = "base64"
                            elif mime_type in ["application/json", "application/xml"]:
                                content_type = "structured"
                            elif content_type != "base64":  # Don't override if already set to base64
                                content_type = "binary"

                            return MAGGResponse.success({
                                "server": server_name,
                                "prefix": server.prefix,
                                "uri": uri,
                                "mimeType": mime_type,
                                "contentType": content_type,
                                "content": content_str
                            })
                        except Exception:
                            # Resource not found in this server, continue to next
                            continue

                except Exception as e:
                    self.server_manager.logger.warning("Failed to access resource from %s: %s", server_name, e)
                    continue

            return MAGGResponse.error(f"Resource not found: {uri}")

        except Exception as e:
            return MAGGResponse.error(f"Failed to get resource: {str(e)}")

    async def list_prompts(
        self,
        name: Annotated[str | None, Field(description="Optional server name to filter by")] = None,
        prefix: Annotated[str | None, Field(description="Optional prefix to filter by")] = None,
    ) -> MAGGResponse:
        """List all available prompts from mounted servers."""
        try:
            return MAGGResponse.success(
                {
                    "prompts": await self.mcp.get_prompts(),
                }
            )
            # prompts_by_server = {}
            #
            # # First, add MAGG's own prompts
            # prompts = await self.mcp.get_prompts()
            #
            # if not prefix or prefix == self.self_prefix:
            #     prompts_by_server[self.self_prefix] = {
            #         "server_name": self.self_prefix,
            #         "prefix": self.self_prefix,
            #         "prompts": prompts
            #     }
            #
            # # Then add prompts from mounted servers
            # config = self.config
            #
            # for server_name, mount_info in self.server_manager.mounted_servers.items():
            #     server = config.servers.get(server_name)
            #     if not server:
            #         continue
            #
            #     # Apply filters
            #     if name and server_name != name:
            #         continue
            #     if prefix and server.prefix != prefix:
            #         continue
            #
            #     server_prompts = []
            #
            #     # Use the proxy server to get prompts
            #     proxy = mount_info['proxy']
            #     try:
            #         prompts_dict = await proxy.get_prompts()
            #         for prompt_name, prompt in prompts_dict.items():
            #             prompt_info = {
            #                 "name": prompt_name,
            #                 "description": prompt.description or "",
            #             }
            #
            #             # Extract arguments from the prompt
            #             arguments = []
            #             if hasattr(prompt, 'arguments'):
            #                 for arg in prompt.arguments:
            #                     arguments.append({
            #                         "name": arg.name,
            #                         "description": arg.description or "",
            #                         "required": arg.required
            #                     })
            #
            #             prompt_info["arguments"] = arguments
            #             server_prompts.append(prompt_info)
            #
            #     except Exception as e:
            #         self.server_manager.logger.warning("Failed to list prompts for %s: %s", server_name, e)
            #         continue
            #
            #     if server_prompts:
            #         prompts_by_server[server_name] = {
            #             "server_name": server_name,
            #             "prefix": server.prefix,
            #             "prompts": server_prompts
            #         }
            #
            # return MAGGResponse.success({
            #     "servers": prompts_by_server,
            #     "total_servers": len(prompts_by_server),
            #     "total_prompts": sum(len(s["prompts"]) for s in prompts_by_server.values())
            # })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list prompts: {str(e)}")

    async def analyze_servers(
        self,
        ctx: Context | None = None,
    ):
        """Analyze configured servers and provide insights using LLM."""
        try:
            config = self.config
            
            if not config.servers:
                return MAGGResponse.success({
                    "analysis": f"No servers configured yet. Use {self.self_prefix}_add_server to add servers."
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
        if not self._is_setup:
            self._is_setup = True
            # Mount all enabled servers
            await self.server_manager.mount_all_enabled()
    
    async def run_stdio(self):
        """Run MAGG in stdio mode."""
        # Don't call setup() here - it's already called by ServerRunner
        await self.mcp.run_stdio_async()
    
    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run MAGG in HTTP mode."""
        # Don't call setup() here - it's already called by ServerRunner
        await self.mcp.run_http_async(host=host, port=port)
