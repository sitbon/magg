#!/usr/bin/env python3
"""Interactive CLI for MBRO - MCP Browser."""

import asyncio
import json
import sys
import argparse
import readline
import atexit
from asyncio import CancelledError
from pathlib import Path

from rich.console import Console
from rich.traceback import install as install_rich_traceback

from .client import MCPBrowser
from .formatter import OutputFormatter

# Install rich traceback handler
install_rich_traceback(show_locals=False)


class MCPBrowserCLI:
    """Interactive CLI for browsing MCP servers."""
    
    def __init__(self, json_only: bool = False, use_rich: bool = True, indent: int = 2):
        self.browser = MCPBrowser()
        self.running = True
        self.console = Console() if use_rich else None
        self.formatter = OutputFormatter(self.console, json_only=json_only, use_rich=use_rich, indent=indent)
        self.setup_readline()
    
    def setup_readline(self):
        """Setup readline for command history and completion."""
        try:
            # Set up history file
            history_file = Path.home() / ".mbro_history"
            
            # Load existing history
            if history_file.exists():
                readline.read_history_file(str(history_file))
            
            # Set history length
            readline.set_history_length(1000)
            
            # Save history on exit
            atexit.register(lambda: readline.write_history_file(str(history_file)))
            
            # Set up tab completion
            readline.set_completer(self.complete)
            readline.parse_and_bind("tab: complete")
            
            # Enable vi or emacs mode (emacs is default)
            readline.parse_and_bind("set editing-mode emacs")
            
        except ImportError:
            # readline not available (e.g., on Windows)
            pass
        except Exception as e:
            print(f"Warning: Could not setup readline: {e}")
    
    def complete(self, text, state):
        """Tab completion for commands."""
        commands = [
            'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
            'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
            'prompt', 'refresh', 'search', 'info'
        ]
        
        matches = [cmd for cmd in commands if cmd.startswith(text)]
        
        # Add tool names if we have a current connection
        current = self.browser.get_current_connection()
        if current and text:
            tool_names = [tool['name'] for tool in current.tools if tool['name'].startswith(text)]
            matches.extend(tool_names)
        
        try:
            return matches[state]
        except IndexError:
            return None
    
    async def start(self):
        """Start the interactive CLI."""
        if not self.formatter.json_only:
            self.formatter.print("MBRO - MCP Browser")
            self.formatter.print("Type 'help' for available commands or 'quit' to exit.\n")
        
        while self.running:
            try:
                # Show current connection in prompt
                if not self.formatter.json_only:
                    current = self.browser.current_connection
                    prompt = f"mbro{f':{current}' if current else ''}> "
                    command = input(prompt).strip()
                else:
                    # In JSON mode, no prompt
                    command = input().strip()
                
                if not command:
                    continue
                
                await self.handle_command(command)
                
            except KeyboardInterrupt:
                if not self.formatter.json_only:
                    self.formatter.print("\nUse 'quit' to exit.")
            except EOFError:
                break
            except Exception as e:
                self.formatter.format_error("Unexpected error in command handling", e)
        
        # Cleanup connections
        for conn in self.browser.connections.values():
            await conn.disconnect()
    
    async def handle_command(self, command: str):
        """Handle a CLI command."""
        parts = command.split()
        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            self.show_help()
        elif cmd == "quit" or cmd == "exit":
            self.running = False
        elif cmd == "connect":
            await self.cmd_connect(args)
        elif cmd == "connections" or cmd == "conns":
            self.cmd_connections()
        elif cmd == "switch":
            await self.cmd_switch(args)
        elif cmd == "disconnect":
            await self.cmd_disconnect(args)
        elif cmd == "tools":
            self.cmd_tools(args)
        elif cmd == "resources":
            self.cmd_resources(args)
        elif cmd == "prompts":
            self.cmd_prompts(args)
        elif cmd == "call":
            await self.cmd_call(args)
        elif cmd == "resource":
            await self.cmd_resource(args)
        elif cmd == "prompt":
            await self.cmd_prompt(args)
        elif cmd == "refresh":
            await self.cmd_refresh()
        elif cmd == "search":
            self.cmd_search(args)
        elif cmd == "info":
            self.cmd_info(args)
        else:
            self.formatter.format_error(f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    def show_help(self):
        """Show help text."""
        self.formatter.format_help()
    
    async def cmd_connect(self, args: list[str]):
        """Connect to an MCP server."""
        if len(args) < 2:
            self.formatter.format_error("Usage: connect <name> <connection_string>")
            return
        
        name = args[0]
        connection_string = " ".join(args[1:])
        
        # Remove quotes if present
        if connection_string.startswith('"') and connection_string.endswith('"'):
            connection_string = connection_string[1:-1]
        
        success = await self.browser.add_connection(name, connection_string)
        if success:
            conn = self.browser.connections[name]
            self.formatter.format_success(f"Connected to '{name}' (Tools: {len(conn.tools)}, Resources: {len(conn.resources)}, Prompts: {len(conn.prompts)})")
        else:
            self.formatter.format_error(f"Failed to connect to '{name}'")
    
    def cmd_connections(self):
        """List all connections."""
        connections = self.browser.list_connections()
        self.formatter.format_connections_table(connections)
    
    async def cmd_switch(self, args: list[str]):
        """Switch to a different connection."""
        if not args:
            self.formatter.format_error("Usage: switch <connection_name>")
            return
        
        name = args[0]
        success = await self.browser.switch_connection(name)
        if success:
            self.formatter.format_success(f"Switched to connection '{name}'")
        else:
            self.formatter.format_error(f"Failed to switch to '{name}'")
    
    async def cmd_disconnect(self, args: list[str]):
        """Disconnect from a server."""
        if not args:
            self.formatter.format_error("Usage: disconnect <connection_name>")
            return
        
        name = args[0]
        success = await self.browser.remove_connection(name)
        if success:
            self.formatter.format_success(f"Disconnected from '{name}'")
        else:
            self.formatter.format_error(f"Connection '{name}' not found")
    
    def cmd_tools(self, args: list[str]):
        """List available tools."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        tools = conn.tools
        if filter_term:
            tools = [t for t in tools if filter_term in t["name"].lower() or filter_term in t["description"].lower()]
        
        if not tools:
            self.formatter.format_info("No tools available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return
        
        # # Output as JSON array
        # tool_list = []
        # for tool in tools:
        #     tool_list.append({
        #         "name": tool['name'],
        #         "description": tool.get('description', '').strip()
        #     })
        
        self.formatter.format_json(tools)
    
    def cmd_resources(self, args: list[str]):
        """List available resources."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        resources = conn.resources
        if filter_term:
            resources = [r for r in resources if filter_term in r["name"].lower() or filter_term in r.get("uri", r.get("uriTemplate")).lower()]
        
        if not resources:
            self.formatter.format_info("No resources available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return

        
        self.formatter.format_json(resources)
    
    def cmd_prompts(self, args: list[str]):
        """List available prompts."""
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        prompts = conn.prompts
        if filter_term:
            prompts = [p for p in prompts if filter_term in p["name"].lower() or filter_term in p["description"].lower()]
        
        if not prompts:
            self.formatter.format_info("No prompts available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return

        self.formatter.format_json(prompts)
    
    async def cmd_call(self, args: list[str]):
        """Call a tool."""
        if not args:
            self.formatter.format_error("Usage: call <tool_name> [json_arguments]")
            self.formatter.format_info("Examples:")
            self.formatter.format_info("  call magg_status")
            self.formatter.format_info("  call magg_search_tools {\"query\": \"calculator\", \"limit\": 3}")
            self.formatter.format_info("  call add {\"a\": 5, \"b\": 3}")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return
        
        tool_name = args[0]
        arguments = {}
        
        if len(args) > 1:
            json_str = " ".join(args[1:])
            try:
                arguments = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.formatter.format_error(f"Invalid JSON arguments: {e}")
                self.formatter.format_info("\nJSON formatting tips:")
                self.formatter.format_info("  - Use double quotes for strings: {\"key\": \"value\"}")
                self.formatter.format_info("  - Numbers don't need quotes: {\"count\": 42}")
                self.formatter.format_info("  - Booleans: {\"enabled\": true}")
                return
        
        try:
            result = await conn.call_tool(tool_name, arguments)
            
            # Extract content from result
            output = []
            for content in result:
                if hasattr(content, 'text'):
                    output.append(content.text)
                else:
                    output.append(str(content))
            
            # Try to parse as JSON for better display
            combined = "\n".join(output)
            try:
                parsed = json.loads(combined)
                self.formatter.format_json(parsed)
            except:
                # Not JSON, just print as text
                self.formatter.format_info(combined)
                    
        except Exception as e:
            self.formatter.format_error(f"Error calling tool: {e}", e)
    
    async def cmd_resource(self, args: list[str]):
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
            
            # Handle different possible return formats from FastMCP
            output = []
            if hasattr(result, 'contents'):
                # Standard MCP format with .contents attribute
                for content in result.contents:
                    if hasattr(content, 'text'):
                        output.append(content.text)
                    else:
                        output.append(str(content))
            elif isinstance(result, list):
                # If result is already a list of contents
                for content in result:
                    if hasattr(content, 'text'):
                        output.append(content.text)
                    elif isinstance(content, dict) and 'text' in content:
                        output.append(content['text'])
                    else:
                        output.append(str(content))
            elif hasattr(result, 'text'):
                # Single content item
                output.append(result.text)
            else:
                # Fallback for other formats
                output.append(str(result))
            
            # Try to parse as JSON for better display
            combined = "\n".join(output)
            try:
                parsed = json.loads(combined)
                self.formatter.format_json(parsed)
            except:
                # Not JSON, just print as text
                self.formatter.format_info(combined)
                    
        except Exception as e:
            self.formatter.format_error(f"Error getting resource: {e}", e)
    
    async def cmd_prompt(self, args: list[str]):
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
            
            # Format prompt result as JSON
            prompt_data = {
                "description": result.description,
                "messages": []
            }
            
            for message in result.messages:
                prompt_data["messages"].append({
                    "role": message.role,
                    "content": message.content.text
                })
            
            self.formatter.format_json(prompt_data)
                    
        except Exception as e:
            self.formatter.format_error(f"Error getting prompt: {e}", e)
    
    async def cmd_refresh(self):
        """Refresh capabilities for current connection."""
        success = await self.browser.refresh_current()
        if success:
            conn = self.browser.get_current_connection()
            self.formatter.format_json({
                "tools": len(conn.tools),
                "resources": len(conn.resources),
                "prompts": len(conn.prompts)
            })
    
    def cmd_search(self, args: list[str]):
        """Search tools, resources, and prompts."""
        if not args:
            self.formatter.format_error("Usage: search <term>")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return
        
        term = " ".join(args).lower()
        
        # Search tools
        matching_tools = [t for t in conn.tools if term in t["name"].lower() or term in t["description"].lower()]
        
        # Search resources
        matching_resources = [r for r in conn.resources if term in r["name"].lower() or term in r["uri"].lower() or term in r["description"].lower()]
        
        # Search prompts
        matching_prompts = [p for p in conn.prompts if term in p["name"].lower() or term in p["description"].lower()]
        
        total_matches = len(matching_tools) + len(matching_resources) + len(matching_prompts)
        
        self.formatter.format_search_results(term, matching_tools, matching_resources, matching_prompts)
    
    def cmd_info(self, args: list[str]):
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
            tool = next((t for t in conn.tools if t["name"] == name), None)
            if not tool:
                self.formatter.format_error(f"Tool '{name}' not found.")
                return
            
            self.formatter.format_tool_info(tool)
        
        elif item_type == "resource":
            resource = next((r for r in conn.resources if r["name"] == name), None)
            if not resource:
                self.formatter.format_error(f"Resource '{name}' not found.")
                return
            
            self.formatter.format_resource_info(resource)
        
        elif item_type == "prompt":
            prompt = next((p for p in conn.prompts if p["name"] == name), None)
            if not prompt:
                self.formatter.format_error(f"Prompt '{name}' not found.")
                return
            
            self.formatter.format_prompt_info(prompt)
        
        else:
            self.formatter.format_error("Item type must be 'tool', 'resource', or 'prompt'")


async def main_async():
    """Async main entry point."""
    parser = argparse.ArgumentParser(description="MBRO - MCP Browser")
    parser.add_argument(
        "--connect",
        nargs=2,
        metavar=("NAME", "CONNECTION"),
        help="Connect to a server on startup"
    )

    # Output formatting options
    parser.add_argument("--json", action="store_true", help="Output only JSON (machine-readable)")
    parser.add_argument("--no-rich", action="store_true", default=None, help="Disable Rich formatting")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent level (0 for compact)")

    # Non-interactive commands
    parser.add_argument("--list-connections", action="store_true", help="List all connections")
    parser.add_argument("--list-tools", action="store_true", help="List available tools")
    parser.add_argument("--list-resources", action="store_true", help="List available resources")
    parser.add_argument("--list-prompts", action="store_true", help="List available prompts")
    parser.add_argument("--call-tool", nargs="+", metavar=("TOOL", "ARGS"), help="Call a tool with JSON args")
    parser.add_argument("--get-resource", metavar="URI", help="Get a resource")
    parser.add_argument("--get-prompt", nargs="+", metavar=("NAME", "ARGS"), help="Get a prompt with JSON args")
    parser.add_argument("--search", metavar="TERM", help="Search tools, resources, and prompts")
    parser.add_argument("--info", nargs=2, metavar=("TYPE", "NAME"), help="Show info about tool/resource/prompt")

    args = parser.parse_args()

    if args.no_rich is None and args.json:
        args.no_rich = not sys.stdout.isatty()  # Disable rich if output is not a TTY

    cli = MCPBrowserCLI(
        json_only=args.json,
        use_rich=not args.no_rich,
        indent=args.indent
    )

    try:

        # Auto-connect if specified
        if args.connect:
            name, connection = args.connect
            success = await cli.browser.add_connection(name, connection)
            if not success:
                sys.exit(1)

        # Handle non-interactive commands
        if args.list_connections:
            cli.cmd_connections()
            return
        elif args.list_tools:
            cli.cmd_tools([])
            return
        elif args.list_resources:
            cli.cmd_resources([])
            return
        elif args.list_prompts:
            cli.cmd_prompts([])
            return
        elif args.call_tool:
            tool_name = args.call_tool[0]
            tool_args = args.call_tool[1:] if len(args.call_tool) > 1 else []
            await cli.cmd_call([tool_name] + tool_args)
            return
        elif args.get_resource:
            await cli.cmd_resource([args.get_resource])
            return
        elif args.get_prompt:
            prompt_name = args.get_prompt[0]
            prompt_args = args.get_prompt[1:] if len(args.get_prompt) > 1 else []
            await cli.cmd_prompt([prompt_name] + prompt_args)
            return
        elif args.search:
            cli.cmd_search([args.search])
            return
        elif args.info:
            cli.cmd_info(args.info)
            return

        # If no non-interactive commands, start interactive mode
        await cli.start()

    except KeyboardInterrupt:
        pass

    except CancelledError:
        # Handle cancellation gracefully
        if not args.json:
            cli.formatter.print("\nOperation cancelled.")

    except Exception as e:
        cli.formatter.format_error("An unexpected error occurred", e)
        exit(1)


def main():
    """Sync entry point."""
    # Setup logging first
    from .. import process
    process.setup()

    try:
        asyncio.run(main_async())

    except KeyboardInterrupt:
        pass

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
