#!/usr/bin/env python3
"""Interactive CLI for MBRO - MCP Browser."""

import argparse
import asyncio
import codeop
import json
import sys
from asyncio import CancelledError
from functools import cached_property
from pathlib import Path

from mcp import GetPromptResult
from mcp.types import TextContent, ImageContent, EmbeddedResource
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import Validator, ValidationError

try:
    from . import arepl
except ImportError:
    arepl = None

from .client import MCPBrowser, MCPConnection
from .formatter import OutputFormatter
from .. import process
from ..proxy import ProxyMCP

from .completers import create_improved_completer
from .parser import ArgumentParser
from .multiline import MultilineInputHandler


class MCPBrowserCLI:
    """Interactive CLI for browsing MCP servers."""
    browser: MCPBrowser
    running: bool
    formatter: OutputFormatter
    verbose: bool

    def __init__(self, json_only: bool = False, use_rich: bool = True, indent: int = 2, verbose: bool = False):
        self.browser = MCPBrowser()
        self.running = True
        self.formatter = OutputFormatter(json_only=json_only, use_rich=use_rich, indent=indent)
        self.verbose = verbose
        
        # Enhanced features
        self.use_enhanced = not json_only
        if self.use_enhanced:
            self.argument_parser = ArgumentParser()
            self.multiline_handler = MultilineInputHandler(self.formatter)
            # Multiline state
            self._multiline_buffer = []

    @cached_property
    def _completer(self):
        if self.use_enhanced:
            return create_improved_completer(self)
        else:
            return WordCompleter(
                [
                    'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
                    'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
                    'prompt', 'status', 'search', 'info'
                ],
                meta_dict={
                    'help': "Show this help message",
                    'quit': "Exit the CLI",
                    'exit': "Exit the CLI",
                    'connect': "Connect to an MCP server",
                    'status': "Show status of the current connection",
                    'connections': "List all connections",
                    'conns': "List all connections (alias)",
                    'switch': "Switch to a different connection",
                    'disconnect': "Disconnect from a server",
                    'tools': "List available tools",
                    'resources': "List available resources",
                    'prompts': "List available prompts",
                    'call': "Call a tool with JSON arguments",
                    'resource': "Get a resource by URI",
                    'prompt': "Get a prompt by name with optional arguments",
                    'search': "Search tools, resources, and prompts by term",
                    'info': "Show detailed info about a tool/resource/prompt"
                }
            )

    def create_prompt_session(self):
        """Create a prompt session with history."""
        history_file = Path.home() / ".mbro_history"
        
        kwargs = {
            'history': FileHistory(str(history_file)),
            'completer': self._completer,
            'complete_while_typing': False,  # Only show on TAB
            'reserve_space_for_menu': 8,  # Ensure space for completion popup
        }
        
        if self.use_enhanced:
            # Add enhanced features
            kwargs['auto_suggest'] = AutoSuggestFromHistory()
            kwargs['enable_history_search'] = True
            kwargs['key_bindings'] = self._create_key_bindings()
            kwargs['complete_style'] = CompleteStyle.COLUMN  # Try single column for popup
            kwargs['complete_in_thread'] = False  # Keep in main thread for better popup display
            kwargs['style'] = self._create_completion_style()
            kwargs['bottom_toolbar'] = self._create_bottom_toolbar
            kwargs['multiline'] = True  # Enable multiline support
            kwargs['prompt_continuation'] = self._create_continuation_prompt
            kwargs['validator'] = self._create_input_validator()
        
        return PromptSession(**kwargs)
    
    def _create_completion_style(self):
        """Create enhanced styling for completions."""
        return Style.from_dict({
            # Completion menu styling
            'completion-menu': 'bg:#2d2d2d fg:#ffffff',
            'completion-menu.completion': 'bg:#2d2d2d fg:#ffffff',
            'completion-menu.completion.current': 'bg:#4a90e2 fg:#ffffff bold',
            'completion-menu.meta': 'bg:#404040 fg:#cccccc italic',
            'completion-menu.meta.current': 'bg:#5ca0f2 fg:#ffffff italic',
            
            # Command prompt styling
            'prompt': 'fg:#4a90e2 bold',
            'continuation': 'fg:#888888',
            
            # Bottom toolbar
            'bottom-toolbar': 'bg:#222222 fg:#cccccc',
        })
    
    def _create_key_bindings(self):
        """Create key bindings for enhanced mode."""
        kb = KeyBindings()
        # Removed multiline JSON mode - overcomplicated
        return kb
    
    def _create_bottom_toolbar(self):
        """Create bottom toolbar for enhanced mode."""
        if self.use_enhanced:
            conn = self.browser.current_connection
            if conn:
                return f" Connected: {conn} | TAB: complete | Ctrl+C: cancel "
            else:
                return " No connection | TAB: complete | Type 'connect <name> <connection>' to start "
        return ""
    
    def _create_continuation_prompt(self, width, line_number, wrap_count):
        """Create Python REPL-style continuation prompt."""
        if wrap_count > 0:
            return " " * (width - 3) + "-> "  # Line wrapping
        else:
            if self.formatter.use_rich:
                return HTML('<ansiyellow>... </ansiyellow>')  # PS2 style
            else:
                return "... "
    
    def _create_input_validator(self):
        """Create validator that detects incomplete input for multiline support."""
        class InputValidator(Validator):
            def __init__(self, cli_instance):
                self.cli = cli_instance
            
            def validate(self, document):
                text = document.text.strip()
                if not text:
                    return
                
                # Check for incomplete input patterns
                if self._needs_continuation(text):
                    # Don't raise error - allow multiline continuation
                    return
                
                # Check for obvious syntax errors in Python-style arguments
                if self._has_syntax_errors(text):
                    raise ValidationError(
                        message="Incomplete input - press Enter to continue or fix syntax",
                        cursor_position=len(text)
                    )
            
            def _needs_continuation(self, text: str) -> bool:
                """Check if input needs continuation like Python REPL."""
                # Backslash continuation
                if text.endswith('\\'):
                    return True
                
                # Unclosed quotes
                if self._has_unclosed_quotes(text):
                    return True
                
                # Unclosed brackets/braces
                if self._has_unclosed_brackets(text):
                    return True
                
                # Try Python compilation check for complex cases
                try:
                    result = codeop.compile_command(text, '<input>', 'exec')
                    return result is None  # None means incomplete
                except SyntaxError:
                    return False  # Syntax error, don't continue
                
                return False
            
            def _has_unclosed_quotes(self, text: str) -> bool:
                """Check for unclosed string literals."""
                in_single = False
                in_double = False
                escaped = False
                
                for char in text:
                    if escaped:
                        escaped = False
                        continue
                    
                    if char == '\\' and (in_single or in_double):
                        escaped = True
                    elif char == '"' and not in_single:
                        in_double = not in_double
                    elif char == "'" and not in_double:
                        in_single = not in_single
                
                return in_single or in_double
            
            def _has_unclosed_brackets(self, text: str) -> bool:
                """Check for unclosed brackets or braces."""
                stack = []
                pairs = {'(': ')', '[': ']', '{': '}'}
                in_string = False
                string_char = None
                escaped = False
                
                for char in text:
                    if escaped:
                        escaped = False
                        continue
                    
                    if char == '\\' and in_string:
                        escaped = True
                        continue
                    
                    if not in_string:
                        if char in ['"', "'"]:
                            in_string = True
                            string_char = char
                        elif char in pairs:
                            stack.append(char)
                        elif char in pairs.values():
                            if not stack:
                                return False  # Closing without opening
                            if pairs[stack[-1]] == char:
                                stack.pop()
                            else:
                                return False  # Mismatched
                    else:
                        if char == string_char:
                            in_string = False
                            string_char = None
                
                return len(stack) > 0 or in_string
            
            def _has_syntax_errors(self, text: str) -> bool:
                """Check for obvious syntax errors."""
                # Very basic syntax error detection
                # This is mainly to catch malformed key=value pairs
                if 'call ' in text and '=' in text:
                    # Check for malformed key=value syntax
                    parts = text.split()
                    if len(parts) >= 3:  # call tool_name params...
                        params = ' '.join(parts[2:])
                        if not params.startswith('{') and '=' in params:
                            # Check each key=value pair
                            pairs = params.split()
                            for pair in pairs:
                                if '=' in pair and not self._is_valid_pair(pair):
                                    return True
                
                return False
            
            def _is_valid_pair(self, pair: str) -> bool:
                """Check if key=value pair is valid."""
                if '=' not in pair:
                    return False
                key, value = pair.split('=', 1)
                return bool(key.strip()) and bool(value.strip())
        
        return InputValidator(self)
    
    async def _refresh_completer_cache(self):
        """Refresh the completer cache after connection changes."""
        if self.use_enhanced and hasattr(self, '_completer'):
            completer = self._completer
            
            # Handle merged completer (no more ThreadedCompleter)
            if hasattr(completer, 'completers'):
                for c in completer.completers:
                    if hasattr(c, 'refresh_cache'):
                        await c.refresh_cache()
            elif hasattr(completer, 'refresh_cache'):
                await completer.refresh_cache()

    async def _handle_multiline_input(self, command: str) -> str:
        """Handle multiline input processing."""
        # For now, just return the command as-is
        # The validator handles multiline detection automatically
        # Future enhancement: could add special processing here
        return command

    async def start(self, repl: bool = False):
        """Start the interactive CLI."""
        if repl:
            if arepl is None:
                self.formatter.print("REPL mode is only available with Python 3.13+")

            self.formatter.print("Entering REPL mode. `await self.handle_command(command)` to execute commands.", file=sys.stderr)

            local = dict(
                current_connection=self.browser.get_current_connection(),
                self=self,
            )

            await arepl.interact(
                banner="Welcome to MBRO - MCP Browser REPL",
                locals=local,
            )

            return

        if not self.formatter.json_only:
            self.formatter.print("MBRO - MCP Browser", file=sys.stderr)
            if self.use_enhanced:
                self.formatter.print("Type 'help' for available commands or 'quit' to exit.", file=sys.stderr)
                self.formatter.print("Enhanced mode: Ctrl+M for multiline JSON, natural language supported\n", file=sys.stderr)
            else:
                self.formatter.print("Type 'help' for available commands or 'quit' to exit.\n", file=sys.stderr)

        session = self.create_prompt_session()

        while self.running:
            try:
                # Show current connection in prompt
                if not self.formatter.json_only:
                    current = self.browser.current_connection
                    prompt = f"mbro{f':{current}' if current else ''}> "

                    if self.formatter.use_rich:
                        prompt = HTML(
                            '<ansiyellow>mbro</ansiyellow>'
                            + ('<ansigreen>:</ansigreen><ansicyan>{}</ansicyan>'.format(current) if current else '')
                            + '<ansiwhite>> </ansiwhite>'
                        )

                else:
                    prompt = ""

                command = await session.prompt_async(prompt)

                if not command:
                    continue
                
                # Handle multiline commands
                full_command = await self._handle_multiline_input(command)
                await self.handle_command(full_command)

            except KeyboardInterrupt:
                if not self.formatter.json_only:
                    self.formatter.print("\nUse 'quit' to exit.")
            except CancelledError:
                pass
            except EOFError:
                break
            except Exception as e:
                self.formatter.format_error("Unexpected error in command handling", e)

        # Cleanup connections
        for conn in self.browser.connections.values():
            await conn.disconnect()

    async def handle_command(self, command: str):
        """Handle a CLI command."""
        # Simple, direct parsing - no natural language nonsense
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
            await self.cmd_connections(args)
        elif cmd == "switch":
            await self.cmd_switch(args)
        elif cmd == "disconnect":
            await self.cmd_disconnect(args)
        elif cmd == "tools":
            await self.cmd_tools(args)
        elif cmd == "resources":
            await self.cmd_resources(args)
        elif cmd == "prompts":
            await self.cmd_prompts(args)
        elif cmd == "call":
            await self.cmd_call(args)
        elif cmd == "resource":
            await self.cmd_resource(args)
        elif cmd == "prompt":
            await self.cmd_prompt(args)
        elif cmd == "status":
            await self.cmd_status()
        elif cmd == "search":
            await self.cmd_search(args)
        elif cmd == "info":
            await self.cmd_info(args)
        else:
            self.formatter.format_error(f"Unknown command: {cmd}. Type 'help' for available commands.")

        if not self.formatter.json_only:
            self.formatter.print()
    

    async def handle_proxy_query_result(self, tool_name: str, result: list[TextContent | ImageContent | EmbeddedResource]):
        """
        Handle the ProxyMCP tool's [list, info] actions on [tool, resource, prompt].

        This allows us to present the results as if they were called directly,
        rather than as a proxy result.

        Returns True if the result was handled, False otherwise.
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
                    self.formatter.format_tools_list(MCPConnection.parse_tools_list(result))
                else:
                    self.formatter.format_tool_info(MCPConnection.parse_tool(result))

            case "resource":
                if isinstance(result, list):
                    self.formatter.format_resources_list(MCPConnection.parse_resources_list(result))
                else:
                    self.formatter.format_resource_info(MCPConnection.parse_resource(result))

            case "prompt":
                if isinstance(result, list):
                    self.formatter.format_prompts_list(MCPConnection.parse_prompts_list(result))
                else:
                    self.formatter.format_prompt_info(MCPConnection.parse_prompt(result))

            case _:
                self.formatter.format_error(f"Unknown proxy type '{result.annotations.proxyType}' in result")

        return True


    def show_help(self):
        """Show help text."""
        self.formatter.format_help()
        
        if self.use_enhanced and not self.formatter.json_only:
            self.formatter.print("\n[bold]Enhanced Features:[/bold]" if self.formatter.use_rich else "\nEnhanced Features:")
            self.formatter.print("  • TAB completion: Press TAB to see available tools, resources, and commands")
            self.formatter.print("  • Parameter completion: Shows tool parameters with documentation")
            self.formatter.print("  • Python-style arguments: Use param=value syntax or JSON")
            self.formatter.print("  • Multiline support: Python REPL-style with '...' continuation")
            self.formatter.print("  • Auto-suggestions from command history")
            self.formatter.print("\n[bold]Quick Start:[/bold]" if self.formatter.use_rich else "\nQuick Start:")
            self.formatter.print("  1. connect local stdio://magg  (REQUIRED for tab completion)")
            self.formatter.print("  2. call magg_<TAB>  (shows available tools)")
            self.formatter.print("  3. call <tool_name> <TAB>  (shows parameters with docs)")
            self.formatter.print("  4. Use: call tool param1=value1 param2=value2")
            self.formatter.print("  5. Or JSON: call tool {\"param1\": \"value1\"}")
            self.formatter.print("\n[dim]Note: Tab completion shows rich parameter info after connecting[/dim]" if self.formatter.use_rich else "\nNote: Tab completion shows rich parameter info after connecting")

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
            # Get counts for display
            tools = await conn.get_tools()
            resources = await conn.get_resources()
            prompts = await conn.get_prompts()
            self.formatter.format_success(f"Connected to '{name}' (Tools: {len(tools)}, Resources: {len(resources)}, Prompts: {len(prompts)})")
            
            # Refresh completer cache if using enhanced mode
            await self._refresh_completer_cache()
        else:
            self.formatter.format_error(f"Failed to connect to '{name}'")

    async def cmd_connections(self, args: list[str]):
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

    async def cmd_switch(self, args: list[str]):
        """Switch to a different connection."""
        if not args:
            self.formatter.format_error("Usage: switch <connection_name>")
            return

        name = args[0]
        success = await self.browser.switch_connection(name)
        if success:
            self.formatter.format_success(f"Switched to connection '{name}'")
            # Refresh completer cache for new connection
            await self._refresh_completer_cache()
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

    async def cmd_tools(self, args: list[str]):
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

    async def cmd_resources(self, args: list[str]):
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

    async def cmd_prompts(self, args: list[str]):
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

    async def cmd_call(self, args: list[str]):
        """Call a tool."""
        if not args:
            self.formatter.format_error("Usage: call <tool_name> [json_arguments]")
            if not self.formatter.json_only:
                self.formatter.format_info("\nExamples:\n"
                                           "  call magg_status\n"
                                           "  call magg_search_tools {\"query\": \"calculator\", \"limit\": 3}\n"
                                           "  call add {\"a\": 5, \"b\": 3}\n"
                                           )
                if self.use_enhanced:
                    self.formatter.format_info("\nEnhanced features:\n"
                                             "  - Natural language: 'call add with a=5 and b=3'\n" 
                                             "  - Press Ctrl+M for multiline JSON editor\n")
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
                if not self.formatter.json_only:
                    self.formatter.format_info(
                        "\nJSON formatting tips:\n"
                        "  - Use double quotes for strings: {\"key\": \"value\"}\n"
                        "  - Numbers don't need quotes: {\"count\": 42}\n"
                        "  - Booleans: {\"enabled\": true}"
                    )
                return
        # If no arguments and the tool needs them, show helpful message
        elif len(args) == 1:
            tools = await conn.get_tools()
            tool = next((t for t in tools if t['name'] == tool_name), None)
            if tool:
                schema = tool.get('inputSchema', {})
                if schema.get('required'):
                    required = schema['required']
                    self.formatter.format_error(f"Tool '{tool_name}' requires arguments: {required}")
                    self.formatter.format_info("Usage: call <tool_name> <json_arguments>")
                    return

        try:
            result = await conn.call_tool(tool_name, arguments)

            if result:
                # Proxy queries are always done through tool calls,
                # but proxied tool calls will still get passed through
                # to the normal formatting below.
                if await self.handle_proxy_query_result(tool_name, result):
                    return

                self.formatter.format_content_list(result)

        except Exception as e:
            error_args = (e,) if self.verbose else ()
            self.formatter.format_error(str(e), *error_args)
            

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

            if result:
                if len(result) > 1:
                    self.formatter.format_resource_list(result)
                else:
                    self.formatter.format_resource(result[0])

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
            result: GetPromptResult = await conn.get_prompt(name, arguments)

            self.formatter.format_prompt_result(result)

        except Exception as e:
            self.formatter.format_error(f"Error getting prompt: {e}", e)

    async def cmd_status(self):
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

    async def cmd_search(self, args: list[str]):
        """Search tools, resources, and prompts."""
        if not args:
            self.formatter.format_error("Usage: search <term>")
            return

        conn = self.browser.get_current_connection()
        if not conn:
            self.formatter.format_error("No active connection.")
            return

        term = " ".join(args).lower()

        # Get all capabilities
        tools = await conn.get_tools()
        resources = await conn.get_resources()
        prompts = await conn.get_prompts()

        # Enhanced matching function
        def matches_enhanced(item, search_term):
            """Enhanced matching with word splitting."""
            name = item.get("name", "").lower()
            desc = item.get("description", "").lower()
            
            # Direct substring match
            if search_term in name or search_term in desc:
                return True
            
            # For resources, also check URI
            if "uri" in item and search_term in item["uri"].lower():
                return True
            if "uriTemplate" in item and search_term in item["uriTemplate"].lower():
                return True
            
            # Word-based matching for enhanced mode
            if self.use_enhanced:
                words = search_term.split()
                combined = f"{name} {desc}"
                # All words must be present
                return all(word in combined for word in words)
            
            return False

        # Search with enhanced matching
        matching_tools = [t for t in tools if matches_enhanced(t, term)]
        matching_resources = [r for r in resources if matches_enhanced(r, term)]
        matching_prompts = [p for p in prompts if matches_enhanced(p, term)]

        self.formatter.format_search_results(term, matching_tools, matching_resources, matching_prompts)

    async def cmd_info(self, args: list[str]):
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
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (can be used multiple times)")

    # Behavior options
    parser.add_argument("--repl", action="store_true", default=None, help="Drop into REPL mode on startup")
    parser.add_argument("--no-enhanced", action="store_true", help="Disable enhanced features (natural language, multiline, etc.)")

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
        indent=args.indent,
        verbose=args.verbose,
    )
    
    # Disable enhanced features if requested
    if args.no_enhanced:
        cli.use_enhanced = False

    try:

        # Auto-connect if specified
        if args.connect:
            name, connection = args.connect
            success = await cli.browser.add_connection(name, connection)
            if not success:
                sys.exit(1)
            # Refresh completer cache after auto-connect
            await cli._refresh_completer_cache()

        # Handle non-interactive commands
        if args.list_connections:
            await cli.cmd_connections(['-x'])
            return
        elif args.list_tools:
            await cli.cmd_tools([])
            return
        elif args.list_resources:
            await cli.cmd_resources([])
            return
        elif args.list_prompts:
            await cli.cmd_prompts([])
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
            await cli.cmd_search([args.search])
            return
        elif args.info:
            await cli.cmd_info(args.info)
            return

        # If no non-interactive commands, start interactive mode
        await cli.start(repl=args.repl)

    except KeyboardInterrupt:
        pass

    except CancelledError:
        if not args.json:
            cli.formatter.print(f"\nOperation cancelled: exiting.", file=sys.stderr)
            exit(1)

    except Exception as e:
        cli.formatter.format_error("An unexpected error occurred", e)
        exit(1)


def main():
    """Sync entry point."""
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
