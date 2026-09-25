"""Command line and argument parsing for mbro."""

import re
import shlex

# call/prompt followed by a JSON object: the object is kept as raw text rather than shell-split
JSON_ARGS_PATTERN = re.compile(r"(call|prompt)\s+(\S+)\s+(\{.*)", re.DOTALL | re.IGNORECASE)


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
        if cleaned.endswith("\\"):
            cleaned = cleaned[:-1].rstrip()

        if not cleaned:
            return []

        # shlex would strip the double quotes inside a JSON object
        if match := JSON_ARGS_PATTERN.fullmatch(cleaned.strip()):
            return list(match.groups())

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

            if char == "\\":
                escaped = True
                result.append(char)
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                result.append(char)
            elif char == "#" and not in_single_quote and not in_double_quote:
                break
            else:
                result.append(char)

        return "".join(result).rstrip()

    @staticmethod
    def split_commands(text: str) -> list[str]:
        """Split text into individual commands by semicolon or newline."""
        lines = text.split("\n")
        merged_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]
            while line.rstrip().endswith("\\") and i + 1 < len(lines):
                stripped = line.rstrip()[:-1]
                next_line = lines[i + 1].lstrip()
                if stripped and not stripped.endswith(" ") and next_line:
                    line = stripped + " " + next_line
                else:
                    line = stripped + next_line
                i += 1
            merged_lines.append(line)
            i += 1

        commands = []
        pending = ""
        for line in merged_lines:
            line = CommandParser._remove_comments(line)
            if pending:
                line = pending + "\n" + line
                pending = ""

            if not line.strip():
                continue

            # A JSON object spanning lines: keep reading until its braces balance
            if CommandParser._brace_depth(line) > 0:
                pending = line
                continue

            parts = CommandParser._split_by_semicolon(line)
            commands.extend(parts)

        if pending:
            commands.extend(CommandParser._split_by_semicolon(pending))

        return [cmd.strip() for cmd in commands if cmd.strip()]

    @staticmethod
    def _brace_depth(text: str) -> int:
        """Count braces opened but not closed, ignoring those in quotes."""
        depth = 0
        in_single_quote = False
        in_double_quote = False
        escaped = False

        for char in text:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif not in_single_quote and not in_double_quote:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1

        return depth

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

            if char == "\\":
                escaped = True
                current.append(char)
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current.append(char)
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current.append(char)
            elif char == ";" and not in_single_quote and not in_double_quote:
                parts.append("".join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append("".join(current))

        return parts

    @staticmethod
    def parse_connect_args(args: list[str]) -> tuple[str, str]:
        """Parse connect command arguments: name and connection string."""
        if len(args) < 2:
            raise ValueError("Usage: connect <name> <connection_string>")

        name = args[0]
        connection = " ".join(args[1:])

        return name, connection
