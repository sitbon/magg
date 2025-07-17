"""Command handlers for mbro CLI."""

import json
from typing import TYPE_CHECKING

from mcp.types import TextContent, ImageContent, EmbeddedResource
from ..proxy import ProxyMCP
from .client import BrowserConnection
from .parser import CommandParser
from .scripts import ScriptManager

if TYPE_CHECKING:
    from .cli import MCPBrowserCLI


class Command:
    """Command handlers for mbro CLI."""
    
    def __init__(self, cli: 'MCPBrowserCLI'):
        self.cli = cli
        self.browser = cli.browser
        self.formatter = cli.formatter
        self.script_manager = ScriptManager(cli=cli)
    
    async def connections(self, args: list):
        """List all connections."""
        extended = False

        if args:
            if args[0] == '-x':
                extended = True
            else:
                self.formatter.format_error("Usage: connections [-x]")
                return

            if len(args) > 1:
                self.formatter.format_error("Usage: connections [-x]")
                return

        connections = await self.browser.list_connections(extended=extended)
        self.formatter.format_connections_table(connections, extended=extended)
    
    async def connect(self, args: list):
        """Connect to an MCP server with optional name."""
        if not args:
            self.formatter.format_error("Usage: connect <name> <connection_string>")
            self.formatter.format_info(
                "Examples:\n"
                "  connect myserver python server.py\n"
                "  connect calc python calculator.py\n"
                "  connect webserver http://localhost:8000/mcp"
            )
            return

        try:
            name, connection_string = CommandParser.parse_connect_args(args)
        except ValueError as e:
            self.formatter.format_error(str(e))
            return

        if connection_string.startswith('"') and connection_string.endswith('"'):
            connection_string = connection_string[1:-1]

        success = await self.browser.add_connection(name, connection_string)
        if success:
            conn = self.browser.connections[name]
            tools = await conn.get_tools()
            resources = await conn.get_resources()
            prompts = await conn.get_prompts()
            self.formatter.format_success(f"Connected to '{name}' (Tools: {len(tools)}, Resources: {len(resources)}, Prompts: {len(prompts)})")

            await self.cli.refresh_completer_cache()
        else:
            self.formatter.format_error(f"Failed to connect to '{name}'")
    
    async def switch(self, args: list):
        """Switch to a different connection."""
        if not args:
            self.formatter.format_error("Usage: switch <connection_name>")
            return

        name = args[0]
        success = await self.browser.switch_connection(name)
        if success:
            await self.cli.refresh_completer_cache()
        else:
            self.formatter.format_error(f"Failed to switch to '{name}'")
    
    async def disconnect(self, args: list):
        """Disconnect from a server."""
        if not args:
            self.formatter.format_error("Usage: disconnect <connection_name>")
            return

        name = args[0]
        success = await self.browser.remove_connection(name)
        if not success:
            self.formatter.format_error(f"Connection '{name}' not found")
    
    async def status(self):
        """Get status of the current connection.
        This includes counts of tools, resources, and prompts.
        """
        conn = self.browser.get_current_connection()
        tools = await conn.get_tools()
        resources = await conn.get_resources()
        prompts = await conn.get_prompts()
        self.formatter.format_json({
            "tools": len(tools),
            "resources": len(resources),
            "prompts": len(prompts)
        })
    
    async def tools(self, args: list):
        """List available tools."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        filter_term = args[0].lower() if args else None

        tools = await conn.get_tools()
        if filter_term:
            tools = [t for t in tools if filter_term in t["name"].lower() or filter_term in t["description"].lower()]

        if not tools:
            self.formatter.format_info("No tools available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return

        self.formatter.format_tools_list(tools)
    
    async def resources(self, args: list):
        """List available resources."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        filter_term = args[0].lower() if args else None

        resources = await conn.get_resources()
        if filter_term:
            resources = [r for r in resources if filter_term in r["name"].lower() or filter_term in r.get("uri", r.get("uriTemplate")).lower()]

        if not resources:
            self.formatter.format_info("No resources available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return

        self.formatter.format_resources_list(resources)
    
    async def prompts(self, args: list):
        """List available prompts."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        filter_term = args[0].lower() if args else None

        prompts = await conn.get_prompts()
        if filter_term:
            prompts = [p for p in prompts if filter_term in p["name"].lower() or filter_term in p["description"].lower()]

        if not prompts:
            self.formatter.format_info("No prompts available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return

        self.formatter.format_prompts_list(prompts)
    
    async def call(self, args: list):
        """Call a tool."""
        if not args:
            self.formatter.format_error("Usage: call <tool_name> [arguments]")
            if not self.formatter.json_only:
                self.formatter.format_info(
                    "\nExamples:\n"
                    "  call magg_status\n"
                    "  call calc_add a=5 b=3\n"
                    "  call magg_search_servers query=\"calculator\" limit=3\n"
                    "  call test_echo {\"message\": \"hello\", \"count\": 42}\n"
                    "\nNote: JSON arguments don't need quotes around the entire object, but some tools do accept JSON strings.\n"
                )
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        tool_name = args[0]
        arguments = {}

        if len(args) > 1:
            args_str = " ".join(args[1:])

            if args_str.strip().startswith('{'):
                try:
                    arguments = json.loads(args_str)
                except json.JSONDecodeError as e:
                    self.formatter.format_error(f"Invalid JSON arguments: {e}")
                    if not self.formatter.json_only:
                        self.formatter.format_info(
                            "\nJSON formatting tips:\n"
                            "  - Use double quotes for strings: {\"key\": \"value\"}\n"
                            "  - Numbers don't need quotes: {\"count\": 42}\n"
                            "  - Booleans: {\"enabled\": true}\n"
                            "  - Don't quote the entire JSON object\n"
                            "  - Example: call tool {\"param\": \"value\"}"
                        )
                    return
            else:
                has_positional = False
                for arg in args[1:]:
                    if '=' not in arg and not arg.startswith('{'):
                        has_positional = True
                        break

                if has_positional:
                    self.formatter.format_error("Positional arguments are not supported. Use key=value syntax.")
                    self.formatter.format_info(f"Example: call {tool_name} a=1 b=2")
                    return

                arguments = self.cli.parse_shell_args(args[1:])

        tools = await conn.get_tools()
        tool = next((t for t in tools if t['name'] == tool_name), None)
        if tool:
            schema = tool.get('inputSchema', {})
            required = schema.get('required', [])
            if required:
                missing = [param for param in required if param not in arguments]
                if missing:
                    self.formatter.format_error(f"Tool '{tool_name}' missing required parameters: {missing}")

                    properties = schema.get('properties', {})
                    if properties and not self.formatter.json_only:
                        self.formatter.format_info("\nRequired parameters:")
                        for param in required:
                            if param in properties:
                                prop = properties[param]
                                param_type = prop.get('type', 'string')
                                desc = prop.get('description', 'No description')
                                self.formatter.format_info(f"  {param}: {param_type} - {desc}")

                    example_args = " ".join([f"{p}=<value>" for p in required])
                    self.formatter.format_info(f"\nExample: call {tool_name} {example_args}")
                    return

        try:
            result = await conn.call_tool(tool_name, arguments)

            if result:
                if await self._handle_proxy_query_result(tool_name, result):
                    return

                self.formatter.format_content_list(result)

        except Exception as e:
            error_args = (e,) if self.cli.verbose else ()
            self.formatter.format_error(str(e), *error_args)
    
    async def resource(self, args: list):
        """Get a resource."""
        if not args:
            self.formatter.format_error("Usage: resource <uri>")
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        uri = args[0]

        try:
            result = await conn.get_resource(uri)

            if result:
                if len(result) > 1:
                    self.formatter.format_resource_list(result)
                else:
                    self.formatter.format_resource(result[0])

        except Exception as e:
            self.formatter.format_error(f"Error getting resource: {e}", e)
    
    async def prompt(self, args: list):
        """Get a prompt."""
        if not args:
            self.formatter.format_error("Usage: prompt <name> [json_arguments]")
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        name = args[0]
        arguments = {}

        if len(args) > 1:
            try:
                arguments = json.loads(" ".join(args[1:]))
            except json.JSONDecodeError as e:
                self.formatter.format_error(f"Invalid JSON arguments: {e}")
                return

        try:
            result = await conn.get_prompt(name, arguments)

            self.formatter.format_prompt_result(result)

        except Exception as e:
            self.formatter.format_error(f"Error getting prompt: {e}", e)
    
    async def search(self, args: list):
        """Search tools, resources, and prompts."""
        if not args:
            self.formatter.format_error("Usage: search <term>")
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        term = " ".join(args).lower()

        tools = await conn.get_tools()
        resources = await conn.get_resources()
        prompts = await conn.get_prompts()

        def matches_enhanced(item, search_term):
            """Enhanced matching with word splitting."""
            name = item.get("name", "").lower()
            desc = item.get("description", "").lower()

            if search_term in name or search_term in desc:
                return True

            if "uri" in item and search_term in item["uri"].lower():
                return True
            if "uriTemplate" in item and search_term in item["uriTemplate"].lower():
                return True

            if self.cli.use_enhanced:
                words = search_term.split()
                combined = f"{name} {desc}"
                return all(word in combined for word in words)

            return False

        matching_tools = [t for t in tools if matches_enhanced(t, term)]
        matching_resources = [r for r in resources if matches_enhanced(r, term)]
        matching_prompts = [p for p in prompts if matches_enhanced(p, term)]

        self.formatter.format_search_results(term, matching_tools, matching_resources, matching_prompts)
    
    async def info(self, args: list):
        """Show detailed info about a tool, resource, or prompt."""
        if len(args) < 2:
            self.formatter.format_error("Usage: info <tool|resource|prompt> <name>")
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        item_type = args[0].lower()
        name = args[1]

        if item_type == "tool":
            tools = await conn.get_tools()
            tool = next((t for t in tools if t["name"] == name), None)
            if not tool:
                self.formatter.format_error(f"Tool '{name}' not found.")
                return

            self.formatter.format_tool_info(tool)

        elif item_type == "resource":
            resources = await conn.get_resources()
            resource = next((r for r in resources if r["name"] == name), None)
            if not resource:
                self.formatter.format_error(f"Resource '{name}' not found.")
                return

            self.formatter.format_resource_info(resource)

        elif item_type == "prompt":
            prompts = await conn.get_prompts()
            prompt = next((p for p in prompts if p["name"] == name), None)
            if not prompt:
                self.formatter.format_error(f"Prompt '{name}' not found.")
                return

            self.formatter.format_prompt_info(prompt)

        else:
            self.formatter.format_error("Item type must be 'tool', 'resource', or 'prompt'")
    
    async def script(self, args: list):
        """Handle script commands."""
        await self.script_manager.handle_script_command(args)
    
    async def _handle_proxy_query_result(self, tool_name: str, result: list) -> bool:
        """
        Handle the ProxyMCP tool's [list, info] actions on [tool, resource, prompt].

        This allows us to present the results as if they were called directly,
        rather than as a proxy result.

        Returns True if the result was handled, False otherwise.

        TODO: Consider relocating this. To ProxyMCP or just somewhere not in this module?
        """
        if tool_name != ProxyMCP.PROXY_TOOL_NAME or not result or len(result) != 1:
            return False

        result = result[0]

        if not isinstance(result, EmbeddedResource):
            return False

        if not result.annotations or getattr(result.annotations, "proxyAction", None) not in {"list", "info"}:
            return False

        proxy_type = getattr(result.annotations, "proxyType", None)

        if (result := ProxyMCP.get_proxy_query_result(result)) is None:
            self.formatter.format_error(f"Failed to handle apparent proxy query result for tool '{tool_name}'")
            return True

        match proxy_type:
            case "tool":
                if isinstance(result, list):
                    self.formatter.format_tools_list(BrowserConnection.parse_tools_list(result))
                else:
                    self.formatter.format_tool_info(BrowserConnection.parse_tool(result))

            case "resource":
                if isinstance(result, list):
                    self.formatter.format_resources_list(BrowserConnection.parse_resources_list(result))
                else:
                    self.formatter.format_resource_info(BrowserConnection.parse_resource(result))

            case "prompt":
                if isinstance(result, list):
                    self.formatter.format_prompts_list(BrowserConnection.parse_prompts_list(result))
                else:
                    self.formatter.format_prompt_info(BrowserConnection.parse_prompt(result))

            case _:
                self.formatter.format_error(f"Unknown proxy type '{result.annotations.proxyType}' in result")

        return True
