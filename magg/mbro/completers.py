"""Improved completion handlers for mbro CLI."""

import asyncio
from typing import List, Optional, Dict, Any, Iterable, Tuple
from prompt_toolkit.completion import Completer, Completion, merge_completers
from prompt_toolkit.document import Document


class ImprovedMCPCommandCompleter(Completer):
    """Improved context-aware completer for MCP commands."""

    def __init__(self, cli_instance):
        self.cli = cli_instance
        self.base_commands = {
            'help': "Show available commands",
            'quit': "Exit the CLI",
            'exit': "Exit the CLI",
            'connect': "Connect to an MCP server",
            'connections': "List all connections",
            'conns': "List all connections (alias)",
            'switch': "Switch to a different connection",
            'disconnect': "Disconnect from a server",
            'tools': "List available tools",
            'resources': "List available resources",
            'prompts': "List available prompts",
            'call': "Call a tool with arguments",
            'resource': "Get a resource by URI",
            'prompt': "Get a prompt by name",
            'status': "Show connection status",
            'search': "Search tools, resources, and prompts",
            'info': "Show detailed info about a tool/resource/prompt"
        }
        self._tools_cache = {}
        self._resources_cache = {}
        self._prompts_cache = {}

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get completions based on current context."""
        text = document.text_before_cursor

        cmd, args, partial = self._parse_command_state(text)

        if cmd is None:
            if partial is not None:
                yield from self._complete_commands(partial)
            else:
                yield from self._complete_commands("")
        else:
            yield from self._get_context_completions(cmd, args, partial)

    def _parse_command_state(self, text: str) -> Tuple[Optional[str], List[str], Optional[str]]:
        """Parse command state from text.

        Returns:
            (command, arguments, partial_word)
            - command: The command if one is complete, None otherwise
            - arguments: List of complete arguments
            - partial_word: The partial word being typed, None if at a space
        """
        if not text:
            return None, [], None

        parts = text.split()
        ends_with_space = text.endswith(' ')

        if not parts:
            return None, [], None

        if len(parts) == 1 and not ends_with_space:
            return None, [], parts[0]

        cmd = parts[0].lower()

        if len(parts) == 1 and ends_with_space:
            return cmd, [], None

        if ends_with_space:
            return cmd, parts[1:], None
        else:
            return cmd, parts[1:-1], parts[-1]

    def _complete_commands(self, prefix: str) -> Iterable[Completion]:
        """Complete command names."""
        for cmd, description in self.base_commands.items():
            if cmd.startswith(prefix.lower()):
                yield Completion(
                    cmd,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=description
                )

    def _get_context_completions(self, cmd: str, args: List[str], partial: Optional[str]) -> Iterable[Completion]:
        """Get context-specific completions."""
        if cmd == 'call':
            if len(args) == 0:
                yield from self._complete_tool_names(partial or "")
            elif len(args) == 1 and partial is None:
                tool_name = args[0]
                yield from self._complete_tool_arguments(tool_name, [], None)
            elif len(args) >= 1:
                tool_name = args[0]
                yield from self._complete_tool_arguments(tool_name, args[1:], partial)

        elif cmd in ('switch', 'disconnect'):
            if len(args) == 0:
                yield from self._complete_connection_names(partial or "")

        elif cmd == 'info':
            if len(args) == 0:
                for info_type in ['tool', 'resource', 'prompt']:
                    if partial is None or info_type.startswith(partial):
                        yield Completion(
                            info_type,
                            start_position=-len(partial) if partial else 0,
                            display_meta=f"Show {info_type} details"
                        )
            elif len(args) == 1:
                yield from self._complete_item_names(args[0], partial or "")

        elif cmd == 'resource':
            if len(args) == 0:
                yield from self._complete_resource_uris(partial or "")

        elif cmd == 'prompt':
            if len(args) == 0:
                yield from self._complete_prompt_names(partial or "")

    def _complete_tool_names(self, prefix: str) -> Iterable[Completion]:
        """Complete tool names with enhanced metadata."""
        tools = self._get_cached_tools()

        if not tools:
            return

        for tool in tools:
            name = tool.get('name', '')
            if name.startswith(prefix):
                description = tool.get('description', '')

                schema = tool.get('inputSchema', {})
                properties = schema.get('properties', {})
                required = schema.get('required', [])

                meta_parts = []
                if description:
                    if len(description) > 60:
                        description = description[:57] + '...'
                    meta_parts.append(description)

                if required and len(required) <= 3:
                    meta_parts.append(f"requires: {', '.join(required)}")
                elif properties:
                    param_count = len(properties)
                    required_count = len(required)
                    if required_count > 0:
                        meta_parts.append(f"{required_count}/{param_count} required")
                    else:
                        meta_parts.append(f"{param_count} optional")

                yield Completion(
                    name,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=' | '.join(meta_parts) if meta_parts else None
                )

    def _complete_connection_names(self, prefix: str) -> Iterable[Completion]:
        """Complete connection names."""
        for name in self.cli.browser.connections:
            if name.startswith(prefix):
                meta = "● active" if name == self.cli.browser.current_connection else "○ inactive"
                yield Completion(
                    name,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=meta
                )

    def _complete_resource_uris(self, prefix: str) -> Iterable[Completion]:
        """Complete resource URIs."""
        resources = self._get_cached_resources()
        for resource in resources:
            uri = resource.get('uri') or resource.get('uriTemplate', '')
            if uri.startswith(prefix):
                name = resource.get('name', '')
                yield Completion(
                    uri,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=name
                )

    def _complete_prompt_names(self, prefix: str) -> Iterable[Completion]:
        """Complete prompt names."""
        prompts = self._get_cached_prompts()
        for prompt in prompts:
            name = prompt.get('name', '')
            if name.startswith(prefix):
                description = prompt.get('description', '')
                if len(description) > 50:
                    description = description[:47] + '...'

                yield Completion(
                    name,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=description
                )

    def _complete_item_names(self, item_type: str, prefix: str) -> Iterable[Completion]:
        """Complete item names based on type."""
        items = []
        if item_type == 'tool':
            items = self._get_cached_tools()
        elif item_type == 'resource':
            items = self._get_cached_resources()
        elif item_type == 'prompt':
            items = self._get_cached_prompts()

        for item in items:
            name = item.get('name', '')
            if name.startswith(prefix):
                description = item.get('description', '')
                if len(description) > 50:
                    description = description[:47] + '...'
                yield Completion(
                    name,
                    start_position=-len(prefix) if prefix else 0,
                    display_meta=description
                )

    def _complete_tool_arguments(self, tool_name: str, args: List[str], partial: Optional[str]) -> Iterable[Completion]:
        """Complete tool arguments with parameter names and documentation."""
        tools = self._get_cached_tools()
        tool = next((t for t in tools if t.get('name') == tool_name), None)

        if not tool:
            yield Completion(
                '{',
                start_position=0,
                display_meta="JSON arguments"
            )
            return

        schema = tool.get('inputSchema', {})
        properties = schema.get('properties', {})
        required = schema.get('required', [])

        if not args and partial is None:
            if properties:
                for param_name, param_info in properties.items():
                    param_type = param_info.get('type', 'any')
                    description = param_info.get('description', '')
                    is_required = param_name in required

                    meta_parts = []
                    if param_type:
                        meta_parts.append(f"{param_type}")
                    if is_required:
                        meta_parts.append("required")
                    else:
                        meta_parts.append("optional")
                    if description:
                        desc = description[:50] + '...' if len(description) > 50 else description
                        meta_parts.append(desc)

                    yield Completion(
                        f"{param_name}=",
                        start_position=0,
                        display_meta=" | ".join(meta_parts),
                        style='fg:ansicyan'
                    )
            else:
                yield Completion(
                    "",
                    start_position=0,
                    display="(no parameters)",
                    display_meta="This tool requires no arguments - just press Enter",
                    style='fg:ansigreen'
                )

        elif args and not partial:
            provided_params = self._parse_existing_params(args)

            for param_name, param_info in properties.items():
                if param_name not in provided_params:
                    param_type = param_info.get('type', 'any')
                    description = param_info.get('description', '')
                    is_required = param_name in required

                    meta_parts = [param_type]
                    if is_required:
                        meta_parts.append("required")
                    if description:
                        desc = description[:40] + '...' if len(description) > 40 else description
                        meta_parts.append(desc)

                    yield Completion(
                        f"{param_name}=",
                        start_position=0,
                        display_meta=" | ".join(meta_parts),
                        style='fg:ansicyan'
                    )

        elif partial and '=' not in partial:
            for param_name, param_info in properties.items():
                if param_name.startswith(partial):
                    param_type = param_info.get('type', 'any')
                    description = param_info.get('description', '')
                    is_required = param_name in required

                    meta_parts = [param_type]
                    if is_required:
                        meta_parts.append("required")
                    if description:
                        desc = description[:40] + '...' if len(description) > 40 else description
                        meta_parts.append(desc)

                    yield Completion(
                        f"{param_name}=",
                        start_position=-len(partial),
                        display_meta=" | ".join(meta_parts),
                        style='fg:ansicyan'
                    )

        elif partial and '=' in partial:
            param_name, value_part = partial.split('=', 1)
            param_info = properties.get(param_name, {})
            yield from self._complete_parameter_value(param_name, param_info, value_part)

    def _parse_existing_params(self, args: List[str]) -> set:
        """Parse existing arguments to find which parameters are already provided."""
        provided = set()

        for arg in args:
            if '=' in arg:
                param_name = arg.split('=', 1)[0]
                provided.add(param_name)

        return provided

    def _complete_parameter_value(self, param_name: str, param_info: Dict[str, Any], value_part: str) -> Iterable[Completion]:
        """Complete parameter values based on type and constraints."""
        param_type = param_info.get('type', 'string')
        enum_values = param_info.get('enum', [])

        if enum_values:
            for enum_val in enum_values:
                enum_str = str(enum_val)
                if enum_str.startswith(value_part):
                    yield Completion(
                        enum_str,
                        start_position=-len(value_part),
                        display_meta=f"Valid option for {param_name}"
                    )

        elif param_type == 'boolean':
            for bool_val in ['true', 'false']:
                if bool_val.startswith(value_part.lower()):
                    yield Completion(
                        bool_val,
                        start_position=-len(value_part),
                        display_meta=f"Boolean value for {param_name}"
                    )

        elif param_type == 'string':
            examples = param_info.get('examples', [])
            if examples:
                for example in examples[:3]:
                    example_str = str(example)
                    if example_str.startswith(value_part):
                        yield Completion(
                            example_str,
                            start_position=-len(value_part),
                            display_meta=f"Example value for {param_name}"
                        )

        if not enum_values and not value_part:
            type_hints = {
                'integer': '123',
                'number': '123.45',
                'string': '"text"',
                'array': '[item1,item2]',
                'object': '{"key":"value"}'
            }

            hint = type_hints.get(param_type)
            if hint:
                yield Completion(
                    hint,
                    start_position=0,
                    display_meta=f"Example {param_type} value",
                    style='fg:ansiyellow'
                )

    def _get_cached_tools(self) -> List[Dict[str, Any]]:
        """Get cached tools or empty list."""
        conn_name = self.cli.browser.current_connection
        if conn_name and conn_name in self._tools_cache:
            return self._tools_cache[conn_name]
        return []

    def _get_cached_resources(self) -> List[Dict[str, Any]]:
        """Get cached resources or empty list."""
        conn_name = self.cli.browser.current_connection
        if conn_name and conn_name in self._resources_cache:
            return self._resources_cache[conn_name]
        return []

    def _get_cached_prompts(self) -> List[Dict[str, Any]]:
        """Get cached prompts or empty list."""
        conn_name = self.cli.browser.current_connection
        if conn_name and conn_name in self._prompts_cache:
            return self._prompts_cache[conn_name]
        return []

    async def refresh_cache(self):
        """Refresh the cache of tools, resources, and prompts."""
        conn_name = self.cli.browser.current_connection
        conn = self.cli.browser.get_current_connection()

        if conn and conn_name:
            try:
                tools, resources, prompts = await asyncio.gather(
                    conn.get_tools(),
                    conn.get_resources(),
                    conn.get_prompts(),
                    return_exceptions=True
                )

                if not isinstance(tools, Exception):
                    self._tools_cache[conn_name] = tools

                if not isinstance(resources, Exception):
                    self._resources_cache[conn_name] = resources
                if not isinstance(prompts, Exception):
                    self._prompts_cache[conn_name] = prompts
            except Exception:
                pass


class ImprovedArgumentCompleter(Completer):
    """Smart argument completer that understands different argument types."""

    def __init__(self, cli_instance):
        self.cli = cli_instance

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Get argument completions."""
        text = document.text_before_cursor

        parts = text.split()
        if len(parts) < 2:
            return

        cmd = parts[0].lower()

        if cmd == 'connect' and len(parts) == 3 and not text.endswith(' '):
            prefix = parts[2]
            for conn_type in ['stdio://', 'http://', 'https://', 'npx ', 'node ', 'python ', 'uvx ']:
                if conn_type.startswith(prefix):
                    yield Completion(
                        conn_type,
                        start_position=-len(prefix),
                        display_meta="Connection type"
                    )


def create_improved_completer(cli_instance) -> Completer:
    """Create an improved completer with popup menu support."""
    command_completer = ImprovedMCPCommandCompleter(cli_instance)
    argument_completer = ImprovedArgumentCompleter(cli_instance)

    return merge_completers([command_completer, argument_completer])
