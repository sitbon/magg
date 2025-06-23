"""MAGG - MCP Aggregator Server - Clean Class-Based Implementation"""

import json
import logging
import os
import re
from functools import wraps
from pathlib import Path
from typing import Any, Annotated

from fastmcp import Context
from mcp.types import PromptMessage, TextContent
from pydantic import Field, AnyUrl

from .defaults import MAGG_ADD_SERVER_DOC, PROXY_TOOL_DOC
from .manager import ServerManager, ManagedServer
from .response import MAGGResponse
from ..discovery.metadata import CatalogManager, SourceMetadataCollector
from ..settings import ConfigManager, ServerConfig
from ..util.transport import TRANSPORT_DOCS
from ..util.uri import validate_working_directory

logger = logging.getLogger(__name__)


class MAGGServer(ManagedServer):
    """Main MAGG server with tools for managing other MCP servers."""
    _is_setup = False

    def __init__(self, config_path: Path | str | None = None):
        super().__init__(ServerManager(ConfigManager(config_path)))
        self._register_tools()

    @property
    def is_setup(self) -> bool:
        """Check if the server is fully set up with tools and resources."""
        return self._is_setup

    def _register_tools(self):
        """Register all MAGG management tools programmatically."""
        self_prefix_ = self.self_prefix_

        tools = [
            (self.add_server, f"{self_prefix_}add_server", None),
            (self.remove_server, f"{self_prefix_}remove_server", None),
            (self.list_servers, f"{self_prefix_}list_servers", None),
            (self.enable_server, f"{self_prefix_}enable_server", None),
            (self.disable_server, f"{self_prefix_}disable_server", None),
            (self.search_servers, f"{self_prefix_}search_servers", None),
            (self.smart_configure, f"{self_prefix_}smart_configure", None),
            (self.analyze_servers, f"{self_prefix_}analyze_servers", None),
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
            self.mcp.tool(name=tool_name, **(options or {}))(call_tool_wrapper(method))

        self._register_resources()
        self._register_prompts()

    def _register_resources(self):
        """Register MCP resources for server metadata.
        """
        resources = [
            (self.get_server_metadata, f"{self.self_prefix}://server/{{name}}"),
            (self.get_all_servers_metadata, f"{self.self_prefix}://servers/all"),
        ]

        for method, uri_pattern in resources:
            self.mcp.resource(
                uri=uri_pattern,
                mime_type="application/json",
            )(method)

    def _register_prompts(self):
        """Register MCP prompts for intelligent configuration.
        """
        prompts = [
            (self.configure_server_prompt, f"{self.self_prefix_}configure_server"),
        ]

        for method, name in prompts:
            self.mcp.prompt(name)(method)

    # ============================================================================
    # region MCP Resource Methods - Expose server metadata for LLM consumption
    # ============================================================================

    async def get_server_metadata(self, name: str) -> dict:
        """Expose server metadata as an MCP resource."""
        config = self.config

        if name in config.servers:
            server = config.servers[name]
            return server.model_dump(mode="json", exclude_none=True, exclude_defaults=True, exclude_unset=True, by_alias=True)

        raise ValueError(f"Server '{name}' not found in configuration")

    async def get_all_servers_metadata(self) -> dict[str, dict]:
        """Expose all servers metadata as an MCP resource."""
        config = self.config

        return {
            name: server.model_dump(
                mode="json",
                exclude_none=True,
                exclude_defaults=True,
                exclude_unset=True,
                by_alias=True
            )
            for name, server in config.servers.items()
        }

    # ============================================================================
    # endregion
    # region MCP Prompt Methods - Templates for LLM-assisted configuration
    # ============================================================================

    @classmethod
    def _format_metadata_for_prompt(cls, metadata_entries: list[dict]) -> str:
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
    ) -> list[PromptMessage]:
        """Generate an enriched prompt template for configuring a server from a URL.

        This prompt can be used with any LLM to generate server configuration.
        For automatic configuration with LLM sampling, use the smart_configure tool instead.
        """
        collector = SourceMetadataCollector()

        try:
            metadata_entries = await collector.collect_metadata(source, server_name)
            metadata_info = self._format_metadata_for_prompt(metadata_entries)
        except Exception as e:
            metadata_info = f"Unable to collect metadata: {str(e)}"

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

Return the configuration as a JSON object.

Documentation for {self.self_prefix_}add_server tool:
{MAGG_ADD_SERVER_DOC}

Documentation for proxy tool:
{PROXY_TOOL_DOC}
"""

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
    # endregion
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
        uri: Annotated[AnyUrl | None, Field(description="URI for HTTP servers")] = None,
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

            if working_dir:
                validated_dir, error = validate_working_directory(working_dir, source)
                if error:
                    return MAGGResponse.error(error)
                working_dir = validated_dir

            try:
                server = ServerConfig(
                    name=name,
                    source=source,
                    prefix=prefix or "",
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

            mount_success = None

            if server.enabled:
                mount_success = await self.server_manager.mount_server(server)

                if not mount_success:
                    return MAGGResponse.error(f"Failed to mount server '{name}'")

            # Save to config
            config.add_server(server)
            self.save_config(config)

            return MAGGResponse.success({
                "action": "server_added",
                "server": {
                    "name": server.name,
                    "source": server.source,
                    "prefix": server.prefix,
                    "command": (
                        f"{server.command} {' '.join(server.args) if server.args else ''}".strip()
                        if server.command else None
                    ),
                    "uri": server.uri,
                    "working_dir": server.working_dir,
                    "notes": server.notes,
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
        """List all configured servers.

        Unlike the /servers/all resource, this tool also provides the runtime
        status of each server (mounted or not).
        """
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

                if server.command:
                    server_data["command"] = f"{server.command} {' '.join(server.args) if server.args else ''}".strip()
                if server.uri:
                    server_data["uri"] = server.uri
                if server.working_dir:
                    server_data["working_dir"] = str(server.working_dir)
                if server.notes:
                    server_data["notes"] = server.notes

                servers.append(server_data)

            return MAGGResponse.success(servers)

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
            # TODO: Consider calling unmount regardless of suggested state
            await self.server_manager.unmount_server(name)

            self.save_config(config)
            return MAGGResponse.success({
                "action": "server_disabled",
                "server": {"name": name}
            })

        except Exception as e:
            return MAGGResponse.error(f"Failed to disable server: {str(e)}")

    async def smart_configure(
        self,
        source: Annotated[str, Field(description="URL of the server package/repository")],
        server_name: Annotated[str | None, Field(
            description="Optional server name (auto-generated if not provided)"
        )] = None,
        allow_add: Annotated[bool, Field(
            description="Whether to automatically add the server after configuration (default: False)"
        )] = False,
        context: Context | None = None,
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
            collector = SourceMetadataCollector()
            metadata_entries = await collector.collect_metadata(source, server_name)
            metadata_summary = []

            for entry in metadata_entries:
                entry_source = entry.get("source", "unknown")
                data = entry.get("data", {})

                if entry_source == "github" and data:
                    metadata_summary.append(f"GitHub: {data.get('description', 'No description')}")
                    metadata_summary.append(f"Language: {data.get('language', 'Unknown')}")
                    metadata_summary.append(f"Stars: {data.get('stars', 0)}")
                    if data.get("setup_instructions"):
                        metadata_summary.append("Setup hints found in README")

                elif entry_source == "filesystem" and data.get("exists"):
                    if data.get("is_directory"):
                        metadata_summary.append(f"Project type: {data.get('project_type', 'unknown')}")
                        if data.get("setup_hints"):
                            metadata_summary.append(f"Setup commands: {', '.join(data['setup_hints'])}")

                elif entry_source == "http_check" and data.get("is_mcp_server"):
                    metadata_summary.append("Direct MCP server detected via HTTP")


            if not context:
                config_suggestion = {
                    "name": server_name or Path(source).stem.replace('-', '').replace('_', ''),
                    "source": source
                }

                for entry in metadata_entries:
                    data = entry.get("data", {})
                    if entry.get("source") == "filesystem" and data.get("project_type"):
                        project_type = data["project_type"]
                        if project_type == "nodejs_project":
                            config_suggestion["command"] = "npx"
                            # noinspection PyTypeChecker
                            config_suggestion["args"] = [server_name or Path(source).stem]
                        elif project_type == "python_project":
                            config_suggestion["command"] = "python"
                            # noinspection PyTypeChecker
                            config_suggestion["args"] = ["-m", server_name or Path(source).stem]

                return MAGGResponse.success({
                    "action": "metadata_based_config",
                    "metadata": metadata_summary,
                    "suggested_config": config_suggestion
                })

            prompt = f"""You are being asked by the MAGG smart_configure tool to analyze metadata and generate an optimal MCP server configuration.

Configure an MCP server for: {source}

Server name requested: {server_name or '<auto-generate based on source>'}

=== METADATA COLLECTED ===
{os.linesep.join(f"- {item}" for item in metadata_summary) if metadata_summary else "No metadata available"}

=== TASK ===
Based on the URL and metadata above, generate a complete JSON configuration that will be automatically added to the user's MAGG server configuration.
* Search for existing tools in the MCP catalog if needed
* Search the web for additional setup instructions if needed
* Examine and use the MAGG MCP server tools directly as needed.
  - The (un-prefixed) `proxy` tool can be used to call any MCP capability and interact with MAGG's dynamic state.

Required fields:
1. name: A human-readable string (can contain any characters)
2. prefix: A valid Python identifier for tool prefixing (no underscores)
3. command: The appropriate command and args (python, node, npx, uvx, or null for HTTP/SSE servers)
4. uri: For HTTP/SSE servers (if applicable)
5. working_dir: If needed
6. env_vars: Environment variables as an object (if needed)
7. notes: Helpful setup instructions for the user
8. transport: Any transport-specific configuration (optional dict)

Return ONLY valid JSON, no explanations or markdown formatting.

Documentation for {self.self_prefix_}add_server tool:
{MAGG_ADD_SERVER_DOC}

Documentation for proxy tool:
{PROXY_TOOL_DOC}
"""

            result = await context.sample(
                messages=prompt,
                max_tokens=1000,
                temperature=0.7,
            )

            if allow_add:
                if not result or not result.text:
                    return MAGGResponse.error("Failed to get configuration from LLM")

                try:
                    json_match = re.search(r'{.*}', result.text, re.DOTALL)
                    if not json_match:
                        return MAGGResponse.error("No valid JSON configuration found in LLM response")

                    config_data = json.loads(json_match.group())

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

            else:
                if result and hasattr(result, 'text'):
                    output = result.text

                    try:
                        output = json.loads(output)
                    except json.JSONDecodeError:
                        pass
                else:
                    output = "No valid configuration generated by LLM"

                return MAGGResponse.success({
                    "action": "smart_configure_prompt",
                    "source": source,
                    "metadata": metadata_summary,
                    "response": output,
                })

        except Exception as e:
            return MAGGResponse.error(f"Smart configuration failed: {str(e)}")

    # noinspection PyMethodMayBeStatic
    async def search_servers(
        self,
        query: Annotated[str, Field(description="Search query for MCP servers")],
        limit: Annotated[int, Field(description="Maximum number of results to return per search source")] = 5,
    ) -> MAGGResponse:
        """Search for MCP servers online."""
        try:
            catalog = CatalogManager()
            results = await catalog.search_only(query, limit)

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

    async def analyze_servers(
        self,
        ctx: Context | None = None,
    ):
        """Analyze configured servers and provide insights using LLM."""
        try:
            config = self.config

            if not config.servers:
                return MAGGResponse.success({
                    "analysis": f"No servers configured yet. Use {self.self_prefix_}add_server to add servers."
                })

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

            if ctx:
                prompt = f"""Analyze this MAGG server configuration and provide insights:

{json.dumps(analysis_data, indent=2)}

Please provide:
1. Overview of the current setup
2. Any potential issues or conflicts
3. Suggestions for optimization
4. Missing capabilities that could be added"""

                result = await ctx.sample(
                    messages=prompt,
                    max_tokens=1000
                )

                if result and result.text:
                    # noinspection PyTypeChecker
                    analysis_data["insights"] = result.text

            return MAGGResponse.success(analysis_data)

        except Exception as e:
            return MAGGResponse.error(f"Failed to analyze servers: {str(e)}")

    # ============================================================================
    # endregion
    # region MCP Server Management - Setup and Run Methods
    # ============================================================================

    async def setup(self):
        """Initialize MAGG and mount existing servers.

        This is called automatically by run_stdio() and run_http().
        For in-memory usage via FastMCPTransport, call this manually:

            server = MAGGServer()
            await server.setup()
            client = Client(FastMCPTransport(server.mcp))
        """
        if not self._is_setup:
            self._is_setup = True
            await self.server_manager.mount_all_enabled()

    async def run_stdio(self):
        """Run MAGG in stdio mode."""
        await self.setup()
        await self.mcp.run_stdio_async()

    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run MAGG in HTTP mode."""
        await self.setup()
        await self.mcp.run_http_async(host=host, port=port, log_level="WARNING")

    # ============================================================================
    # endregion
    # ============================================================================
