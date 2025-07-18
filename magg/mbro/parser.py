"""Command line and argument parsing for mbro."""

import json
import re
import shlex
from typing import Any


class JsonArgParser:
    """Parse and validate JSON and shell-style arguments."""

    @staticmethod
    def parse_command(text: str) -> tuple[str, list[str]]:
        """Parse a command string into command and arguments."""
        parts = []
        current = []
        in_json = False
        brace_count = 0

        for char in text:
            if char == '{' and not in_json:
                if current:
                    parts.extend(''.join(current).split())
                    current = []
                in_json = True
                brace_count = 1
                current.append(char)
            elif in_json:
                current.append(char)
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        parts.append(''.join(current))
                        current = []
                        in_json = False
            else:
                current.append(char)

        if current:
            if in_json:
                parts.append(''.join(current))
            else:
                parts.extend(''.join(current).split())

        if not parts:
            return '', []

        command = parts[0].lower()
        args = parts[1:]

        args = JsonArgParser._process_arguments(command, args)

        return command, args

    @staticmethod
    def _process_arguments(command: str, args: list[str]) -> list[str]:
        """Process and enhance arguments based on command context."""
        if not args:
            return args

        if command == 'call' and len(args) > 1:
            tool_name = args[0]
            remaining = ' '.join(args[1:])

            if not remaining.strip().startswith('{'):
                converted = JsonArgParser._convert_to_json(remaining)
                if converted:
                    return [tool_name, converted]

        return args

    @staticmethod
    def _convert_to_json(arg_string: str) -> str | None:
        """Try to convert various argument formats to JSON."""
        if arg_string.strip().startswith('{'):
            return arg_string

        if '=' in arg_string:
            args_dict = {}
            pairs = re.split(r'\s+', arg_string)

            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    args_dict[key] = JsonArgParser._infer_type(value)

            if args_dict:
                return json.dumps(args_dict)

        return None

    @staticmethod
    def _infer_type(value: str) -> Any:
        """Infer the type of a string value."""
        value = value.strip()

        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return int(value)

        try:
            if '.' in value:
                return float(value)
        except ValueError:
            pass

        if ',' in value:
            items = [JsonArgParser._infer_type(item.strip()) for item in value.split(',')]
            return items

        return value


class CommandParser:
    """Parse and prepare commands for execution."""

    @staticmethod
    def parse_command_line(line: str) -> list[str]:
        """Parse a single command line, handling comments and continuations."""
        cleaned = CommandParser._remove_comments(line)

        if not cleaned.strip():
            return []

        # Strip trailing backslash from single-line continuation
        cleaned = cleaned.rstrip()
        if cleaned.endswith('\\'):
            cleaned = cleaned[:-1].rstrip()

        if not cleaned:
            return []

        try:
            return shlex.split(cleaned)
        except ValueError:
            return cleaned.split()

    @staticmethod
    def _remove_comments(line: str) -> str:
        """Remove comments from a line, preserving quoted strings."""
        result = []
        in_single_quote = False
        in_double_quote = False
        escaped = False

        for char in line:
            if escaped:
                result.append(char)
                escaped = False
                continue

            if char == '\\':
                escaped = True
                result.append(char)
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                result.append(char)
            elif char == '#' and not in_single_quote and not in_double_quote:
                break
            else:
                result.append(char)

        return ''.join(result).rstrip()

    @staticmethod
    def split_commands(text: str) -> list[str]:
        """Split text into individual commands by semicolon or newline."""
        lines = text.split('\n')
        merged_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]
            while line.rstrip().endswith('\\') and i + 1 < len(lines):
                stripped = line.rstrip()[:-1]
                next_line = lines[i + 1].lstrip()
                if stripped and not stripped.endswith(' ') and next_line:
                    line = stripped + ' ' + next_line
                else:
                    line = stripped + next_line
                i += 1
            merged_lines.append(line)
            i += 1

        commands = []
        for line in merged_lines:
            line = CommandParser._remove_comments(line)
            if not line.strip():
                continue

            parts = CommandParser._split_by_semicolon(line)
            commands.extend(parts)

        return [cmd.strip() for cmd in commands if cmd.strip()]

    @staticmethod
    def _split_by_semicolon(text: str) -> list[str]:
        """Split text by semicolons that aren't in quotes."""
        parts = []
        current = []
        in_single_quote = False
        in_double_quote = False
        escaped = False

        for char in text:
            if escaped:
                current.append(char)
                escaped = False
                continue

            if char == '\\':
                escaped = True
                current.append(char)
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current.append(char)
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current.append(char)
            elif char == ';' and not in_single_quote and not in_double_quote:
                parts.append(''.join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append(''.join(current))

        return parts

    @staticmethod
    def parse_connect_args(args: list[str]) -> tuple[str, str]:
        """Parse connect command arguments: name and connection string."""
        if len(args) < 2:
            raise ValueError("Usage: connect <name> <connection_string>")

        name = args[0]
        connection = ' '.join(args[1:])

        return name, connection
