"""Output formatters for mbro."""

import json
import sys
import traceback
from typing import Any

from rich.console import Console
from rich.json import JSON
from rich.table import Table


class OutputFormatter:
    """Handle formatted output for mbro."""
    
    def __init__(self, console: Console, json_only: bool = False, use_rich: bool | None = True, indent: int = 2):
        self.console = console
        self.json_only = json_only
        self.use_rich = use_rich if use_rich is not None else True
        self.indent = indent if indent > 0 else None

    def print(self, *objects, **kwds) -> None:
        """Print a message using the console or standard output."""
        if self.use_rich:
            self.console.print(*objects, **kwds)
        else:
            print(*objects, **kwds)

    def format_json(self, data: Any) -> None:
        """Format and print JSON data."""
        if self.use_rich:
            output = JSON.from_data(data, indent=self.indent, default=str)
            self.console.print(output)
        else:
            output = json.dumps(data, indent=self.indent, default=str)
            print(output)
    
    def format_error(self, message: str, exception: Exception | None = None) -> None:
        """Format and print an error message."""
        if self.json_only:
            error_data = {"error": message}
            if exception:
                error_data["exception"] = {
                    "type": type(exception).__name__,
                    "message": str(exception),
                    "traceback": traceback.format_exc().splitlines()
                }

            self.format_json(error_data)
        else:
            if self.use_rich:
                self.console.print(f"[red]Error: {message}[/red]")
                if exception:
                    self.console.print_exception(show_locals=False)
            else:
                print(f"Error: {message}", file=sys.stderr)
                if exception:
                    traceback.print_exc()
    
    def format_success(self, message: str) -> None:
        """Format and print a success message."""
        if self.json_only:
            self.format_json({"success": message})
        elif self.use_rich:
            self.console.print(f"[green]{message}[/green]")
        else:
            print(message)
    
    def format_info(self, message: str) -> None:
        """Format and print an info message."""
        if self.json_only:
            self.format_json({"info": message})
        elif self.use_rich:
            self.console.print(message)
        else:
            print(message)
    
    def format_connections_table(self, connections: list[dict[str, Any]]) -> None:
        """Format connections as a table."""
        if not connections:
            self.format_info("No connections configured.")
            return
        
        if self.json_only:
            self.format_json({"connections": connections})
        elif self.use_rich:
            table = Table(title="Connections")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Status")
            table.add_column("Tools", justify="right")
            table.add_column("Resources", justify="right")
            table.add_column("Prompts", justify="right")
            
            for conn in connections:
                status = "[green]Connected[/green]" if conn["connected"] else "[red]Disconnected[/red]"
                if conn["current"]:
                    status += " [bold](current)[/bold]"
                table.add_row(
                    conn['name'],
                    conn['type'],
                    status,
                    str(conn['tools']),
                    str(conn['resources']),
                    str(conn['prompts'])
                )
            
            self.console.print(table)
        else:
            # Plain text table
            print("Connections:")
            for conn in connections:
                status = "Connected" if conn["connected"] else "Disconnected"
                if conn["current"]:
                    status += " (current)"
                print(f"  {conn['name']} ({conn['type']}) - {status}")
                print(f"    Tools: {conn['tools']}, Resources: {conn['resources']}, Prompts: {conn['prompts']}")
    
    def format_tool_info(self, tool: dict[str, Any]) -> None:
        """Format detailed tool information."""
        tool_data = {
            "type": "tool",
            "name": tool['name'],
            "description": tool['description']
        }
        if tool.get('inputSchema'):
            tool_data["inputSchema"] = tool['inputSchema']
        
        self.format_json(tool_data)
    
    def format_resource_info(self, resource: dict[str, Any]) -> None:
        """Format detailed resource information."""
        self.format_json({
            "type": "resource",
            "name": resource['name'],
            "uri": resource['uri'],
            "mimeType": resource['mimeType'],
            "description": resource['description']
        })
    
    def format_prompt_info(self, prompt: dict[str, Any]) -> None:
        """Format detailed prompt information."""
        prompt_data = {
            "type": "prompt",
            "name": prompt['name'],
            "description": prompt['description']
        }
        if prompt.get('arguments'):
            prompt_data["arguments"] = prompt['arguments']
        
        self.format_json(prompt_data)
    
    def format_search_results(self, term: str, tools: list, resources: list, prompts: list) -> None:
        """Format search results."""
        total_matches = len(tools) + len(resources) + len(prompts)
        
        if total_matches == 0:
            self.console.print(f"No results found for '{term}'")
            return
        
        results = {
            "query": term,
            "total_matches": total_matches,
            "tools": [{"name": t['name'], "description": t['description']} for t in tools],
            "resources": [{"name": r['name'], "uri": r['uri'], "description": r['description']} for r in resources],
            "prompts": [{"name": p['name'], "description": p['description']} for p in prompts]
        }
        
        self.format_json(results)
    
    def format_help(self) -> None:
        """Format help text."""
        if self.json_only:
            help_data = {
                "help": {
                    "connection_management": [
                        {"command": "connect <name> <connection_string>", "description": "Connect to an MCP server"},
                        {"command": "connections, conns", "description": "List all connections"},
                        {"command": "switch <name>", "description": "Switch to a different connection"},
                        {"command": "disconnect <name>", "description": "Disconnect from a server"},
                        {"command": "refresh", "description": "Refresh capabilities for current connection"}
                    ],
                    "server_exploration": [
                        {"command": "tools [filter]", "description": "List available tools"},
                        {"command": "resources [filter]", "description": "List available resources"},
                        {"command": "prompts [filter]", "description": "List available prompts"},
                        {"command": "search <term>", "description": "Search tools, resources, and prompts"},
                        {"command": "info <tool|resource|prompt> <name>", "description": "Show detailed info"}
                    ],
                    "tool_interaction": [
                        {"command": "call <tool_name> [json_args]", "description": "Call a tool"},
                        {"command": "resource <uri>", "description": "Get a resource"},
                        {"command": "prompt <name> [json_args]", "description": "Get a prompt"}
                    ]
                }
            }
            self.format_json(help_data)
            return
        
        help_text = """
Available commands:

Connection Management:
  connect <name> <connection_string>  - Connect to an MCP server
  connections, conns                  - List all connections  
  switch <name>                       - Switch to a different connection
  disconnect <name>                   - Disconnect from a server
  refresh                             - Refresh capabilities for current connection

Server Exploration:
  tools [filter]                      - List available tools
  resources [filter]                  - List available resources  
  prompts [filter]                    - List available prompts
  search <term>                       - Search tools, resources, and prompts
  info <tool|resource|prompt> <name>  - Show detailed info

Tool Interaction:
  call <tool_name> [json_args]        - Call a tool
  resource <uri>                      - Get a resource
  prompt <name> [json_args]           - Get a prompt

Examples:
  connect magg "http://localhost:8080"
  connect calc "npx @wrtnlabs/calculator-mcp"
  tools
  call magg_status
  call magg_search_tools {"query": "calculator", "limit": 3}
  call add {"a": 5, "b": 3}
  search calculator
  info tool magg_status

JSON Tips (REPL):
  - Use double quotes for JSON strings: {"key": "value"}
  - No quotes for numbers: {"count": 42}
  - Boolean values: {"enabled": true}
  - Arrays: {"items": [1, 2, 3]}
        """
        self.console.print(help_text)