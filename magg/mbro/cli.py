#!/usr/bin/env python3
"""Interactive CLI for MBRO - MCP Browser."""

import argparse
import asyncio
import codeop
import shlex
import sys
from asyncio import CancelledError
from functools import cached_property
from pathlib import Path

from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.filters import completion_is_selected, has_completions
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style

try:
    from . import arepl
except ImportError:
    arepl = None

from .client import BrowserClient
from .formatter import OutputFormatter
from .. import process

from .completers import create_improved_completer
from .parser import JsonArgParser
from .multiline import MultilineInputHandler
from .command import Command
from .validator import InputValidator
from .parser import CommandParser


class MCPBrowserCLI:
    """Interactive CLI for browsing MCP servers."""
    browser: BrowserClient
    running: bool
    formatter: OutputFormatter
    verbose: bool
    
    COMMANDS = frozenset({
        "help", "quit", "connect", "connections", "switch", "disconnect",
        "tools", "resources", "prompts", "call", "resource", "prompt",
        "status", "search", "info", "script"
    })
    
    ALIASES = {
        "exit": "quit",
        "conns": "connections"
    }

    def __init__(self, json_only: bool = False, use_rich: bool = True, indent: int = 2, verbose: bool = False):
        self.browser = BrowserClient()
        self.running = True
        self.formatter = OutputFormatter(json_only=json_only, use_rich=use_rich, indent=indent)
        self.verbose = verbose
        self.command = Command(self)

        self.use_enhanced = not json_only
        if self.use_enhanced:
            self.json_parser = JsonArgParser()
            self.multiline_handler = MultilineInputHandler(self.formatter)
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

        kwds: dict = dict(
            history=FileHistory(str(history_file)),
            completer=self._completer,
            complete_while_typing=False,
            reserve_space_for_menu=8,
        )

        if self.use_enhanced:
            kwds.update(
                auto_suggest=self._create_smart_auto_suggest(),
                enable_history_search=True,
                key_bindings=self._create_key_bindings(),
                complete_style=CompleteStyle.COLUMN,
                complete_in_thread=False,
                style=self._create_completion_style(),
                bottom_toolbar=self._create_bottom_toolbar,
                multiline=True,
                prompt_continuation=self._create_continuation_prompt,
            )

        return PromptSession(**kwds)

    @classmethod
    def _create_completion_style(cls):
        """Create enhanced styling for completions."""
        return Style.from_dict({
            'completion-menu': 'bg:#2d2d2d fg:#ffffff',
            'completion-menu.completion': 'bg:#2d2d2d fg:#ffffff',
            'completion-menu.completion.current': 'bg:#4a90e2 fg:#ffffff bold',
            'completion-menu.meta': 'bg:#404040 fg:#cccccc italic',
            'completion-menu.meta.current': 'bg:#5ca0f2 fg:#ffffff italic',
            'prompt': 'fg:#4a90e2 bold',
            'continuation': 'fg:#888888',
            'bottom-toolbar': 'bg:#222222 fg:#cccccc',
        })

    def _create_key_bindings(self):
        """Create key bindings for enhanced mode."""
        kb = KeyBindings()

        @kb.add('c-c')
        def _(event):
            """Handle Ctrl+C - cancel completion or multiline input or interrupt."""
            buffer = event.app.current_buffer
            if buffer.complete_state:
                buffer.cancel_completion()
            elif buffer.text.strip():
                buffer.reset()
            else:
                raise KeyboardInterrupt()

        @kb.add('enter')
        def _(event):
            """Handle Enter key - submit complete commands immediately."""
            buffer = event.app.current_buffer
            document = buffer.document
            text = document.text.strip()

            validator_instance = self._create_input_validator()

            if text and not validator_instance._needs_continuation(text):
                if '\n' not in document.text:
                    buffer.validate_and_handle()
                    return

            if not buffer.document.current_line.strip() and buffer.text.strip():
                buffer.validate_and_handle()
            else:
                buffer.insert_text('\n')

        @kb.add('escape', 'enter')
        def _(event):
            """Alt+Enter to force submit even with incomplete input."""
            buffer = event.app.current_buffer
            buffer.validate_and_handle()

        @kb.add('tab')
        def _(event):
            """Custom TAB handling for completion control."""
            buffer = event.app.current_buffer

            if buffer.complete_state:
                buffer.complete_next()
            else:
                buffer.start_completion(select_first=False)

        @kb.add('s-tab')  # Shift+Tab
        def _(event):
            """Navigate backward through completions."""
            buffer = event.app.current_buffer
            if buffer.complete_state:
                buffer.complete_previous()

        @kb.add('enter', filter=completion_is_selected)
        def _(event):
            """Apply selected completion and close menu."""
            buffer = event.app.current_buffer
            if buffer.complete_state and buffer.complete_state.current_completion:
                buffer.apply_completion(buffer.complete_state.current_completion)
                buffer.cancel_completion()

        @kb.add('escape', filter=has_completions, eager=True)
        def _(event):
            """Cancel completion menu without applying (ESC when menu is open)."""
            buffer = event.app.current_buffer
            buffer.cancel_completion()

        return kb

    @classmethod
    def _create_smart_auto_suggest(cls):
        """Create auto-suggestion from history."""
        return AutoSuggestFromHistory()

    def _create_bottom_toolbar(self):
        """Create bottom toolbar for enhanced mode."""
        if self.use_enhanced:
            conn = self.browser.current_connection
            if conn:
                return f" Connected: {conn} | TAB: complete | Shift+TAB: navigate | Enter: apply | ESC/Ctrl+C: cancel "
            else:
                return " No connection | TAB: complete | Type 'connect <name> <connection>' to start "
        return ""

    def _create_continuation_prompt(self, width, line_number, wrap_count):
        """Create Python REPL-style continuation prompt aligned with main prompt."""
        if wrap_count > 0:
            return " " * (width - 3) + "-> "
        else:
            current = self.browser.current_connection if self.browser.current_connection else None
            if current:
                padding = len(f"mbro:{current}> ") - 4
            else:
                padding = len("mbro> ") - 4

            spaces = " " * padding
            if self.formatter.use_rich:
                return HTML(f'{spaces}<ansiyellow>... </ansiyellow>')
            else:
                return f"{spaces}... "

    def _create_input_validator(self):
        """Create validator that detects incomplete input for multiline support."""
        return InputValidator(self)

    @classmethod
    def parse_shell_args(cls, args: list[str]) -> dict:
        """Parse shell-style key=value arguments.

        Examples:
            name="test" -> {"name": "test"}
            count=42 -> {"count": 42}
            enabled=true -> {"enabled": true}
            name="my server" count=5 -> {"name": "my server", "count": 5}
        """
        result = {}

        for arg in args:
            if '=' not in arg:
                continue

            key, value = arg.split('=', 1)
            key = key.strip()

            if not key:
                continue

            if value.lower() == 'true':
                result[key] = True
            elif value.lower() == 'false':
                result[key] = False
            elif value.replace('.', '', 1).replace('-', '', 1).isdigit():
                if '.' in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)
            else:
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    result[key] = value[1:-1]
                else:
                    result[key] = value

        return result

    async def refresh_completer_cache(self):
        """Refresh the completer cache after connection changes."""
        if self.use_enhanced and hasattr(self, '_completer'):
            completer = self._completer

            if hasattr(completer, 'completers'):
                for c in completer.completers:
                    if hasattr(c, 'refresh_cache'):
                        await c.refresh_cache()
            elif hasattr(completer, 'refresh_cache'):
                await completer.refresh_cache()


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
            self.formatter.print("Type 'help' for available commands or 'quit' to exit.\n", file=sys.stderr)

        session = self.create_prompt_session()

        while self.running:
            try:
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

                await self.handle_command(command)

            except KeyboardInterrupt:
                if not self.formatter.json_only:
                    self.formatter.print("\nUse 'quit' to exit.")
            except CancelledError:
                pass
            except EOFError:
                break
            except Exception as e:
                self.formatter.format_error("Unexpected error in command handling", e)

        for conn in self.browser.connections.values():
            await conn.disconnect()

    async def handle_command(self, command: str):
        """Handle a CLI command."""
        parts = CommandParser.parse_command_line(command)
        
        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        if args and any('{' in arg for arg in args):
            json_start_idx = None
            for i, arg in enumerate(args):
                if '{' in arg:
                    json_start_idx = i
                    break
            
            if json_start_idx is not None:
                json_part = ' '.join(args[json_start_idx:])
                
                if json_part.count('{') == json_part.count('}'):
                    if cmd in ['call', 'prompt', 'get-prompt']:
                        args = args[:json_start_idx] + [json_part]

        cmd = self.ALIASES.get(cmd, cmd)
        
        if cmd not in self.COMMANDS:
            self.formatter.format_error(f"Unknown command: {cmd}")
            self.formatter.format_info("Type 'help' for available commands")
            return
        
        match cmd:
            case "help":
                self.show_help()
            case "quit":
                self.running = False
            case _:
                await getattr(self.command, cmd)(args)

        if not self.formatter.json_only:
            self.formatter.print()


    def show_help(self):
        """Show help text."""
        self.formatter.format_help(enhanced=self.use_enhanced and not self.formatter.json_only)



async def handle_commands(cli: MCPBrowserCLI, args) -> bool:
    """Handle command line commands from args or stdin.
    
    Returns:
        True if any commands were executed
    """
    commands_to_run = []
    
    if args.commands and args.commands[0] == '-':
        stdin_text = sys.stdin.read()
        commands_to_run = CommandParser.split_commands(stdin_text)
    elif args.commands:
        command_text = ' '.join(args.commands)
        commands_to_run = CommandParser.split_commands(command_text)
    
    if not commands_to_run:
        return False
    
    for command in commands_to_run:
        if command.strip():
            await cli.handle_command(command)
    
    return True


async def main_async():
    """Async main entry point."""
    parser = argparse.ArgumentParser(description="MBRO - MCP Browser")
    parser.add_argument("--json", "-j", action="store_true", help="Output only JSON (machine-readable)")
    parser.add_argument("--no-rich", action="store_true", default=None, help="Disable Rich formatting")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent level (0 for compact)")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (can be used multiple times)")

    parser.add_argument("--repl", action="store_true", default=None, help="Drop into REPL mode on startup")
    parser.add_argument("--no-enhanced", action="store_true", help="Disable enhanced features (natural language, multiline, etc.)")
    parser.add_argument("-n", "--no-interactive", action="store_true", help="Don't drop into interactive mode after commands")
    parser.add_argument("-x", "--execute-script", action="append", metavar="SCRIPT", help="Execute script file (can be used multiple times)")
    
    parser.add_argument("commands", nargs="*", help="Commands to execute (use ';' to separate multiple commands or '-' to read from stdin)")

    args = parser.parse_args()

    if args.no_rich is None and args.json:
        args.no_rich = not sys.stdout.isatty()

    cli = MCPBrowserCLI(
        json_only=args.json,
        use_rich=not args.no_rich,
        indent=args.indent,
        verbose=args.verbose,
    )

    if args.no_enhanced:
        cli.use_enhanced = False

    try:
        if args.execute_script:
            for script_path in args.execute_script:
                await cli.handle_command(f"script run {script_path}")

        commands_executed = False
        if args.commands:
            commands_executed = await handle_commands(cli, args)
        
        if not commands_executed and not args.no_interactive:
            await cli.start(repl=args.repl)
        elif not commands_executed and args.no_interactive:
            parser.print_help()
            sys.exit(1)

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
