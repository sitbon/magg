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

        if self._needs_continuation(text):
            return

        if self._has_syntax_errors(text):
            raise ValidationError(
                message="Incomplete input - press Enter to continue or fix syntax",
                cursor_position=len(text)
            )

    def _needs_continuation(self, text: str) -> bool:
        """Check if input needs continuation like Python REPL."""
        if not text.strip():
            return False

        if text.endswith('\\'):
            return True

        if self._has_unclosed_quotes(text):
            return True

        if self._has_unclosed_brackets(text):
            return True

        try:
            words = text.strip().split(maxsplit=1)
            if words and words[0] in {
                'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
                'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
                'prompt', 'status', 'search', 'info'
            }:
                return False

            result = codeop.compile_command(text, '<input>', 'exec')
            return result is None
        except SyntaxError:
            return False

        return False

    @staticmethod
    def _is_complete_mbro_command(text: str) -> bool:
        """Check if text is a complete mbro command."""
        text = text.strip()
        if not text:
            return False

        mbro_commands = {
            'help', 'quit', 'exit', 'connect', 'connections', 'conns', 'switch',
            'disconnect', 'tools', 'resources', 'prompts', 'call', 'resource',
            'prompt', 'status', 'search', 'info'
        }

        standalone_commands = {
            'help', 'quit', 'exit', 'connections', 'conns', 'disconnect',
            'tools', 'resources', 'prompts', 'status'
        }

        words = text.split()
        if not words or words[0] not in mbro_commands:
            return False

        command = words[0]

        if command in standalone_commands:
            return True

        if command == 'call':
            return len(words) >= 2
        elif command in ['connect', 'switch', 'resource', 'prompt', 'search', 'info']:
            return len(words) >= 2

        return True

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
                        return False
                    if pairs[stack[-1]] == char:
                        stack.pop()
                    else:
                        return False
            else:
                if char == string_char:
                    in_string = False
                    string_char = None

        return len(stack) > 0 or in_string

    def _has_syntax_errors(self, text: str) -> bool:
        """Check for obvious syntax errors."""
        if 'call ' in text and '=' in text:
            parts = text.split()
            if len(parts) >= 3:
                params = ' '.join(parts[2:])
                if not params.startswith('{') and '=' in params:
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
