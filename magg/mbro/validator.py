"""Input validator for mbro multiline support."""

import codeop
from prompt_toolkit.validation import Validator, ValidationError


class InputValidator(Validator):
    """Validator that detects incomplete input for multiline support."""
    
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
        # Empty input or whitespace-only should not continue
        if not text.strip():
            return False

        # Backslash continuation
        if text.endswith('\\'):
            return True

        # Unclosed quotes
        if self._has_unclosed_quotes(text):
            return True

        # Unclosed brackets/braces
        if self._has_unclosed_brackets(text):
            return True

        # For mbro commands, we're done if quotes/brackets are balanced
        # Don't use _is_complete_mbro_command check here since it doesn't
        # consider quotes/brackets properly

        # Try Python compilation check for complex cases
        # This is mainly for Python-style dict/list arguments
        try:
            # First check if it's an mbro command
            words = text.strip().split(maxsplit=1)
            if words and words[0] in {
                'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
                'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
                'prompt', 'status', 'search', 'info'
            }:
                # For mbro commands, if quotes/brackets are balanced, we're done
                return False

            # For other input, use Python compilation check
            result = codeop.compile_command(text, '<input>', 'exec')
            return result is None  # None means incomplete
        except SyntaxError:
            return False  # Syntax error, don't continue

        return False

    @staticmethod
    def _is_complete_mbro_command(text: str) -> bool:
        """Check if text is a complete mbro command."""
        text = text.strip()
        if not text:
            return False

        # All known mbro commands
        mbro_commands = {
            'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
            'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
            'prompt', 'status', 'search', 'info'
        }

        # Commands that are complete with just the command word
        standalone_commands = {
            'help', 'quit', 'exit', 'connections', 'conns', 'disconnect',
            'tools', 'resources', 'prompts', 'status'
        }

        # Split and check first word
        words = text.split()
        if not words or words[0] not in mbro_commands:
            return False  # Not a recognized mbro command

        command = words[0]

        # Check standalone commands
        if command in standalone_commands:
            return True

        # For commands that need arguments, check if they look complete
        if command == 'call':
            # call command needs tool name, args are optional
            # call tool_name {...} or call tool_name key=value
            return len(words) >= 2
        elif command in ['connect', 'switch', 'resource', 'prompt', 'search', 'info']:
            # These commands need at least one argument
            return len(words) >= 2

        return True  # Default to complete for other commands

    @staticmethod
    def _has_unclosed_quotes(text: str) -> bool:
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

    @staticmethod
    def _has_unclosed_brackets(text: str) -> bool:
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

    @staticmethod
    def _is_valid_pair(pair: str) -> bool:
        """Check if key=value pair is valid."""
        if '=' not in pair:
            return False
        key, value = pair.split('=', 1)
        return bool(key.strip()) and bool(value.strip())