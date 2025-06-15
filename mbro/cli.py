#!/usr/bin/env python3
"""Interactive CLI for MBRO - MCP Browser."""

import asyncio
import json
import sys
import argparse
import readline
import atexit
from pathlib import Path

from .client import MCPBrowser


class MCPBrowserCLI:
    """Interactive CLI for browsing MCP servers."""
    
    def __init__(self):
        self.browser = MCPBrowser()
        self.running = True
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
        print("🔍 MBRO - MCP Browser")
        print("Interactive MCP server browser and client")
        print("Type 'help' for available commands or 'quit' to exit.\n")
        
        while self.running:
            try:
                # Show current connection in prompt
                current = self.browser.current_connection
                prompt = f"mbro{f':{current}' if current else ''}> "
                
                command = input(prompt).strip()
                if not command:
                    continue
                
                await self.handle_command(command)
                
            except KeyboardInterrupt:
                print("\nUse 'quit' to exit.")
            except EOFError:
                break
        
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
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    def show_help(self):
        """Show help text."""
        print("""
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
  call magg_search_tools '{"query": "calculator", "limit": 3}'
  call add '{"a": 5, "b": 3}'
  search calculator
  info tool magg_status

JSON Tips:
  - Use single quotes around JSON: '{"key": "value"}'
  - Double quotes for strings inside: {"name": "value"}
  - No quotes for numbers: {"count": 42}
        """)
    
    async def cmd_connect(self, args: list[str]):
        """Connect to an MCP server."""
        if len(args) < 2:
            print("Usage: connect <name> <connection_string>")
            print("Examples:")
            print("  connect magg \"uv run magg\"")
            print("  connect calc \"npx @wrtnlabs/calculator-mcp\"")
            print("  connect server \"http://localhost:8080\"")
            return
        
        name = args[0]
        connection_string = " ".join(args[1:])
        
        # Remove quotes if present
        if connection_string.startswith('"') and connection_string.endswith('"'):
            connection_string = connection_string[1:-1]
        
        print(f"Connecting to '{name}' with: {connection_string}")
        success = await self.browser.add_connection(name, connection_string)
        
        if success:
            print(f"Connection '{name}' added successfully.")
    
    def cmd_connections(self):
        """List all connections."""
        connections = self.browser.list_connections()
        
        if not connections:
            print("No connections configured.")
            return
        
        print("\n📡 Connections:")
        for conn in connections:
            status = "🟢" if conn["connected"] else "🔴"
            current = " (current)" if conn["current"] else ""
            print(f"  {status} {conn['name']} ({conn['type']}){current}")
            print(f"      Tools: {conn['tools']}, Resources: {conn['resources']}, Prompts: {conn['prompts']}")
    
    async def cmd_switch(self, args: list[str]):
        """Switch to a different connection."""
        if not args:
            print("Usage: switch <connection_name>")
            return
        
        name = args[0]
        success = await self.browser.switch_connection(name)
        if success:
            print(f"Switched to connection '{name}'")
    
    async def cmd_disconnect(self, args: list[str]):
        """Disconnect from a server."""
        if not args:
            print("Usage: disconnect <connection_name>")
            return
        
        name = args[0]
        success = await self.browser.remove_connection(name)
        if success:
            print(f"Disconnected from '{name}'")
    
    def cmd_tools(self, args: list[str]):
        """List available tools."""
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        tools = conn.tools
        if filter_term:
            tools = [t for t in tools if filter_term in t["name"].lower() or filter_term in t["description"].lower()]
        
        if not tools:
            print("No tools available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return
        
        print(f"\n🔧 Tools ({len(tools)}):")
        for tool in tools:
            print(f"  • {tool['name']}")
            
            # Clean up description - remove extra whitespace and format nicely
            desc = tool.get('description', '').strip()
            
            # Split on common separators and clean up
            lines = []
            if '\n\n' in desc:
                # Split on double newlines (paragraph breaks)
                parts = desc.split('\n\n')
                main_desc = parts[0].replace('\n', ' ').strip()
                lines.append(f"    {main_desc}")
                
                # Handle additional sections like Args:, Returns:, etc.
                for part in parts[1:]:
                    part = part.strip()
                    if part.startswith('Args:') or part.startswith('Arguments:'):
                        lines.append(f"    Arguments:")
                        # Parse arguments section
                        arg_lines = part.split('\n')[1:]  # Skip the "Args:" line
                        for arg_line in arg_lines:
                            arg_line = arg_line.strip()
                            if arg_line:
                                lines.append(f"      {arg_line}")
                    elif part.startswith('Returns:'):
                        lines.append(f"    Returns:")
                        return_lines = part.split('\n')[1:]
                        for return_line in return_lines:
                            return_line = return_line.strip()
                            if return_line:
                                lines.append(f"      {return_line}")
                    else:
                        # Other sections
                        clean_part = part.replace('\n', ' ').strip()
                        if clean_part:
                            lines.append(f"    {clean_part}")
            else:
                # Single line or simple description
                clean_desc = desc.replace('\n', ' ').strip()
                lines.append(f"    {clean_desc}")
            
            # Print all lines
            for line in lines:
                print(line)
            
            print()  # Add spacing between tools
    
    def cmd_resources(self, args: list[str]):
        """List available resources."""
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        resources = conn.resources
        if filter_term:
            resources = [r for r in resources if filter_term in r["name"].lower() or filter_term in r["uri"].lower()]
        
        if not resources:
            print("No resources available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return
        
        print(f"\n📄 Resources ({len(resources)}):")
        for resource in resources:
            print(f"  • {resource['name']} ({resource['mimeType']})")
            print(f"    URI: {resource['uri']}")
            print(f"    {resource['description']}")
    
    def cmd_prompts(self, args: list[str]):
        """List available prompts."""
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        filter_term = args[0].lower() if args else None
        
        prompts = conn.prompts
        if filter_term:
            prompts = [p for p in prompts if filter_term in p["name"].lower() or filter_term in p["description"].lower()]
        
        if not prompts:
            print("No prompts available." + (f" (filtered by '{filter_term}')" if filter_term else ""))
            return
        
        print(f"\n💬 Prompts ({len(prompts)}):")
        for prompt in prompts:
            print(f"  • {prompt['name']}")
            print(f"    {prompt['description']}")
            if prompt['arguments']:
                args_str = ", ".join([f"{arg['name']}{'*' if arg['required'] else ''}" for arg in prompt['arguments']])
                print(f"    Arguments: {args_str}")
    
    async def cmd_call(self, args: list[str]):
        """Call a tool."""
        if not args:
            print("Usage: call <tool_name> [json_arguments]")
            print("Examples:")
            print("  call magg_status")
            print("  call magg_search_tools '{\"query\": \"calculator\", \"limit\": 3}'")
            print("  call add '{\"a\": 5, \"b\": 3}'")
            print("\nNote: Use single quotes around JSON to avoid shell parsing issues.")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        tool_name = args[0]
        arguments = {}
        
        if len(args) > 1:
            json_str = " ".join(args[1:])
            try:
                arguments = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON arguments: {e}")
                print(f"Input was: {json_str}")
                print("\nJSON formatting tips:")
                print("  - Use double quotes for strings: {\"key\": \"value\"}")
                print("  - Use single quotes around the whole JSON: '{\"key\": \"value\"}'")
                print("  - Numbers don't need quotes: {\"count\": 42}")
                print("  - Booleans: {\"enabled\": true}")
                return
        
        try:
            print(f"🔧 Calling tool '{tool_name}' with arguments: {json.dumps(arguments, indent=2) if arguments else '{}'}")
            result = await conn.call_tool(tool_name, arguments)
            
            print("\n📤 Result:")
            for content in result:
                if hasattr(content, 'text'):
                    print(content.text)
                else:
                    print(str(content))
                    
        except Exception as e:
            print(f"❌ Error calling tool: {e}")
            print("\nTroubleshooting:")
            print("  - Check tool name with: tools")
            print("  - Get tool info with: info tool <tool_name>")
            print("  - Verify JSON format with an online validator")
    
    async def cmd_resource(self, args: list[str]):
        """Get a resource."""
        if not args:
            print("Usage: resource <uri>")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        uri = args[0]
        
        try:
            print(f"Getting resource: {uri}")
            result = await conn.get_resource(uri)
            
            print("\n📄 Resource Content:")
            # Handle different possible return formats from FastMCP
            if hasattr(result, 'contents'):
                # Standard MCP format with .contents attribute
                for content in result.contents:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(str(content))
            elif isinstance(result, list):
                # If result is already a list of contents
                for content in result:
                    if hasattr(content, 'text'):
                        print(content.text)
                    elif isinstance(content, dict) and 'text' in content:
                        print(content['text'])
                    else:
                        print(str(content))
            elif hasattr(result, 'text'):
                # Single content item
                print(result.text)
            else:
                # Fallback for other formats
                print(str(result))
                    
        except Exception as e:
            print(f"❌ Error getting resource: {e}")
    
    async def cmd_prompt(self, args: list[str]):
        """Get a prompt."""
        if not args:
            print("Usage: prompt <name> [json_arguments]")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        name = args[0]
        arguments = {}
        
        if len(args) > 1:
            try:
                arguments = json.loads(" ".join(args[1:]))
            except json.JSONDecodeError as e:
                print(f"Invalid JSON arguments: {e}")
                return
        
        try:
            print(f"Getting prompt '{name}' with arguments: {arguments}")
            result = await conn.get_prompt(name, arguments)
            
            print("\n💬 Prompt:")
            print(f"Description: {result.description}")
            for message in result.messages:
                print(f"\n{message.role}: {message.content.text}")
                    
        except Exception as e:
            print(f"❌ Error getting prompt: {e}")
    
    async def cmd_refresh(self):
        """Refresh capabilities for current connection."""
        success = await self.browser.refresh_current()
        if success:
            conn = self.browser.get_current_connection()
            print(f"Refreshed capabilities: {len(conn.tools)} tools, {len(conn.resources)} resources, {len(conn.prompts)} prompts")
    
    def cmd_search(self, args: list[str]):
        """Search tools, resources, and prompts."""
        if not args:
            print("Usage: search <term>")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        term = " ".join(args).lower()
        
        # Search tools
        matching_tools = [t for t in conn.tools if term in t["name"].lower() or term in t["description"].lower()]
        
        # Search resources
        matching_resources = [r for r in conn.resources if term in r["name"].lower() or term in r["uri"].lower() or term in r["description"].lower()]
        
        # Search prompts
        matching_prompts = [p for p in conn.prompts if term in p["name"].lower() or term in p["description"].lower()]
        
        total_matches = len(matching_tools) + len(matching_resources) + len(matching_prompts)
        
        if total_matches == 0:
            print(f"No results found for '{term}'")
            return
        
        print(f"\n🔍 Search results for '{term}' ({total_matches} matches):")
        
        if matching_tools:
            print(f"\n🔧 Tools ({len(matching_tools)}):")
            for tool in matching_tools:
                print(f"  • {tool['name']} - {tool['description']}")
        
        if matching_resources:
            print(f"\n📄 Resources ({len(matching_resources)}):")
            for resource in matching_resources:
                print(f"  • {resource['name']} - {resource['uri']}")
        
        if matching_prompts:
            print(f"\n💬 Prompts ({len(matching_prompts)}):")
            for prompt in matching_prompts:
                print(f"  • {prompt['name']} - {prompt['description']}")
    
    def cmd_info(self, args: list[str]):
        """Show detailed info about a tool, resource, or prompt."""
        if len(args) < 2:
            print("Usage: info <tool|resource|prompt> <name>")
            return
        
        conn = self.browser.get_current_connection()
        if not conn:
            print("No active connection.")
            return
        
        item_type = args[0].lower()
        name = args[1]
        
        if item_type == "tool":
            tool = next((t for t in conn.tools if t["name"] == name), None)
            if not tool:
                print(f"Tool '{name}' not found.")
                return
            
            print(f"\n🔧 Tool: {tool['name']}")
            print(f"Description: {tool['description']}")
            if tool['inputSchema']:
                print("Input Schema:")
                print(json.dumps(tool['inputSchema'], indent=2))
        
        elif item_type == "resource":
            resource = next((r for r in conn.resources if r["name"] == name), None)
            if not resource:
                print(f"Resource '{name}' not found.")
                return
            
            print(f"\n📄 Resource: {resource['name']}")
            print(f"URI: {resource['uri']}")
            print(f"Type: {resource['mimeType']}")
            print(f"Description: {resource['description']}")
        
        elif item_type == "prompt":
            prompt = next((p for p in conn.prompts if p["name"] == name), None)
            if not prompt:
                print(f"Prompt '{name}' not found.")
                return
            
            print(f"\n💬 Prompt: {prompt['name']}")
            print(f"Description: {prompt['description']}")
            if prompt['arguments']:
                print("Arguments:")
                for arg in prompt['arguments']:
                    required = " (required)" if arg['required'] else ""
                    print(f"  • {arg['name']}{required} - {arg['description']}")
        
        else:
            print("Item type must be 'tool', 'resource', or 'prompt'")


async def main_async():
    """Async main entry point."""
    parser = argparse.ArgumentParser(description="MBRO - MCP Browser")
    parser.add_argument(
        "--connect", 
        nargs=2, 
        metavar=("NAME", "CONNECTION"),
        help="Connect to a server on startup"
    )
    
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
    
    cli = MCPBrowserCLI()
    
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


def main():
    """Sync entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()