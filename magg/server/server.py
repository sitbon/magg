"""MAGG - MCP Aggregator Server - Clean Class-Based Implementation"""

import json
import logging
from typing import Any, Annotated
from pathlib import Path

from fastmcp import FastMCP, Client, Context
from pydantic import Field

from ..settings import ConfigManager, ServerConfig
from ..response import MAGGResponse
from ..util import (
    get_transport_for_command, 
    get_transport_for_uri,
    validate_working_directory,
    TRANSPORT_DOCS,
)

from .defaults import MAGG_INSTRUCTIONS


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
            self.mcp.mount(server.prefix, proxy_server, as_proxy=True)
            # Store both proxy and client for resource/prompt access
            self.mounted_servers[server.name] = {
                'proxy': proxy_server,
                'client': client
            }
            
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
            (self.list_resources, "magg_list_resources"),
            (self.get_resource, "magg_get_resource"),
            (self.list_prompts, "magg_list_prompts"),
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
    
    async def get_server_metadata(self, name: str) -> ServerConfig:
        """Expose server metadata as an MCP resource."""
        config = self.config_manager.load_config()

        if name in config.servers:
            server = config.servers[name]
            return server

        raise ValueError(f"Server '{name}' not found in configuration")

    async def get_all_servers_metadata(self) -> dict[str, ServerConfig]:
        """Expose all servers metadata as an MCP resource."""
        config = self.config_manager.load_config()
        return config.servers
    
    # ============================================================================
    # region MCP Prompt Methods - Templates for LLM-assisted configuration
    # ============================================================================
    
    async def configure_server_prompt(
        self,
        source: Annotated[str, Field(description="URL of the server to configure")],
        server_name: Annotated[str | None, Field(description="Optional server name")] = None,
    ) -> list[dict[str, str]]:
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
        transport: Annotated[dict[str, Any] | None, Field(description="Transport-specific configuration (optional)")] = None,
    ) -> MAGGResponse:
        """Add a new MCP server."""
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

    add_server.__doc__ += f"\n\nTransport documentation:\n{TRANSPORT_DOCS}\n"

    async def remove_server(
        self,
        name: Annotated[str, Field(description="Server name to remove")],
    ) -> MAGGResponse:
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
    
    async def enable_server(
        self,
        name: Annotated[str, Field(description="Server name to enable")],
    ) -> MAGGResponse:
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
    
    async def disable_server(
        self,
        name: Annotated[str, Field(description="Server name to disable")],
    ) -> MAGGResponse:
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
        source: Annotated[str, Field(description="URL of the server package/repository")],
        server_name: Annotated[str | None, Field(
            description="Optional server name (auto-generated if not provided)"
        )] = None,
        ctx: Context | None = None,
    ) -> MAGGResponse:
        """Use LLM sampling to intelligently configure a server from a URL."""
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
7. env_vars: Environment variables as an object (if needed)
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
            magg_resources = []
            for uri_pattern, method in [
                ("magg://servers/all", self.get_all_servers_metadata),
                ("magg://server/{name}", self.get_server_metadata),
            ]:
                magg_resources.append({
                    "uri": uri_pattern,
                    "name": uri_pattern.split("/")[-1],
                    "description": method.__doc__.strip() if method.__doc__ else "",
                    "mimeType": "application/json"
                })
            
            if not prefix or prefix == "magg":
                resources_by_server["magg"] = {
                    "server_name": "magg",
                    "prefix": "magg",
                    "resources": magg_resources,
                    "resource_templates": []
                }
            
            # Then add resources from mounted servers
            config = self.config_manager.load_config()
            
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
                    self.server_manager.logger.warning(f"Failed to list resources for {server_name}: {e}")
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
        uri: Annotated[str, Field(description="The resource URI or URI template")],
        args: Annotated[dict[str, Any] | None, Field(
            description="Arguments for URI template (if applicable)"
        )] = None,
        prefix: Annotated[str | None, Field(description="Optional server prefix to filter by")] = None,
        name: Annotated[str | None, Field(description="Optional server name to filter by")] = None,
    ) -> MAGGResponse:
        """Get a specific resource from an MCP server."""
        try:
            # Check if it's a MAGG resource
            if uri.startswith("magg://"):
                if uri == "magg://servers/all":
                    content = await self.get_all_servers_metadata()
                elif uri.startswith("magg://server/"):
                    server_name = uri.split("/")[-1]
                    content = await self.get_server_metadata(server_name)
                else:
                    return MAGGResponse.error(f"Unknown MAGG resource: {uri}")
                
                return MAGGResponse.success({
                    "uri": uri,
                    "mimeType": "application/json",
                    "contentType": "structured",
                    "content": content
                })
            
            # Otherwise, look for the resource in mounted servers
            config = self.config_manager.load_config()
            
            for server_name, mount_info in self.server_manager.mounted_servers.items():
                server = config.servers.get(server_name)
                if not server:
                    continue
                
                # Apply filters
                if name and server_name != name:
                    continue
                if prefix and server.prefix != prefix:
                    continue
                
                client = mount_info['client']
                
                try:
                    async with client:
                        # Try to read the resource
                        try:
                            if args:
                                # Template resource with args
                                result = await client.read_resource(uri, **args)
                            else:
                                # Regular resource
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
                    self.server_manager.logger.warning(f"Failed to access resource from {server_name}: {e}")
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
            prompts_by_server = {}
            
            # First, add MAGG's own prompts
            magg_prompts = []
            for prompt_name, method in [
                ("configure_server", self.configure_server_prompt),
            ]:
                magg_prompts.append({
                    "name": prompt_name,
                    "description": method.__doc__.strip() if method.__doc__ else "",
                    "arguments": [
                        {"name": "source", "description": "URL of the server", "required": True},
                        {"name": "server_name", "description": "Optional server name", "required": False}
                    ]
                })
            
            if not prefix or prefix == "magg":
                prompts_by_server["magg"] = {
                    "server_name": "magg",
                    "prefix": "magg",
                    "prompts": magg_prompts
                }
            
            # Then add prompts from mounted servers
            config = self.config_manager.load_config()
            
            for server_name, mount_info in self.server_manager.mounted_servers.items():
                server = config.servers.get(server_name)
                if not server:
                    continue
                    
                # Apply filters
                if name and server_name != name:
                    continue
                if prefix and server.prefix != prefix:
                    continue
                
                server_prompts = []
                
                # Use the proxy server to get prompts
                proxy = mount_info['proxy']
                try:
                    prompts_dict = await proxy.get_prompts()
                    for prompt_name, prompt in prompts_dict.items():
                        prompt_info = {
                            "name": prompt_name,
                            "description": prompt.description or "",
                        }
                        
                        # Extract arguments from the prompt
                        arguments = []
                        if hasattr(prompt, 'arguments'):
                            for arg in prompt.arguments:
                                arguments.append({
                                    "name": arg.name,
                                    "description": arg.description or "",
                                    "required": arg.required
                                })
                        
                        prompt_info["arguments"] = arguments
                        server_prompts.append(prompt_info)
                        
                except Exception as e:
                    self.server_manager.logger.warning(f"Failed to list prompts for {server_name}: {e}")
                    continue
                
                if server_prompts:
                    prompts_by_server[server_name] = {
                        "server_name": server_name,
                        "prefix": server.prefix,
                        "prompts": server_prompts
                    }
            
            return MAGGResponse.success({
                "servers": prompts_by_server,
                "total_servers": len(prompts_by_server),
                "total_prompts": sum(len(s["prompts"]) for s in prompts_by_server.values())
            })
            
        except Exception as e:
            return MAGGResponse.error(f"Failed to list prompts: {str(e)}")

    async def analyze_servers(
        self,
        ctx: Context | None = None,
    ) -> MAGGResponse:
        """Analyze configured servers and provide insights using LLM."""
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
