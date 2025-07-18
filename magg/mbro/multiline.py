"""Multiline input handling for mbro."""

import json
from typing import Optional, Dict, Any, Callable
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.filters import Condition

try:
    from pygments.lexers import JsonLexer
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


class PropertyTypeValidator(Validator):
    """Validator for property types in multiline input."""

    def __init__(self, prop_type: str, prop_info: Dict[str, Any]):
        self.prop_type = prop_type
        self.prop_info = prop_info

    def validate(self, document):
        text = document.text.strip()

        if not text:
            return

        if self.prop_type == 'integer':
            try:
                int(text)
            except ValueError:
                raise ValidationError(message="Must be an integer")

        elif self.prop_type == 'number':
            try:
                float(text)
            except ValueError:
                raise ValidationError(message="Must be a number")

        elif self.prop_type == 'boolean':
            if text.lower() not in ('true', 'false', 'yes', 'no', '1', '0', 'y', 'n'):
                raise ValidationError(message="Must be true/false")

        if 'enum' in self.prop_info and text not in map(str, self.prop_info['enum']):
            valid = ', '.join(str(v) for v in self.prop_info['enum'])
            raise ValidationError(message=f"Must be one of: {valid}")


class JSONValidator(Validator):
    """Validate JSON input."""

    def validate(self, document):
        """Validate the JSON document."""
        text = document.text
        if not text.strip():
            return

        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            raise ValidationError(
                message=f"Invalid JSON: {str(e)}",
                cursor_position=len(text)
            )


class MultilineInputHandler:
    """Handle multiline input with syntax highlighting and validation."""

    def __init__(self, formatter=None):
        self.formatter = formatter
        self.style = Style.from_dict({
            'prompt': '#ansiblue bold',
            'continuation': '#ansiwhite',
            'json-key': '#ansicyan',
            'json-string': '#ansigreen',
            'json-number': '#ansiyellow',
            'json-boolean': '#ansimagenta',
        })

    def create_bindings(self) -> KeyBindings:
        """Create key bindings for multiline mode."""
        bindings = KeyBindings()

        @bindings.add('c-d')
        def submit(event):
            """Submit the current buffer."""
            event.app.exit()

        @bindings.add('c-c')
        def cancel(event):
            """Cancel input."""
            event.app.exit(exception=KeyboardInterrupt)

        @bindings.add('tab')
        def indent(event):
            """Insert 2 spaces for indentation."""
            event.current_buffer.insert_text('  ')

        return bindings

    async def get_multiline_input(
        self,
        prompt: str = "",
        initial_text: str = "",
        lexer_type: str = 'json',
        validator: Optional[Validator] = None,
        completer: Optional[Any] = None,
        bottom_toolbar: Optional[Callable] = None
    ) -> Optional[str]:
        """Get multiline input with syntax highlighting."""

        lexer = None
        if PYGMENTS_AVAILABLE and lexer_type == 'json':
            lexer = PygmentsLexer(JsonLexer)

        if validator is None and lexer_type == 'json':
            validator = JSONValidator()

        if bottom_toolbar is None:
            def bottom_toolbar():
                return " Ctrl+D: Submit | Ctrl+C: Cancel | Tab: Indent "

        session = PromptSession(
            message=prompt,
            multiline=True,
            key_bindings=self.create_bindings(),
            lexer=lexer,
            style=self.style,
            validator=validator,
            completer=completer,
            bottom_toolbar=bottom_toolbar,
            mouse_support=True,
            complete_while_typing=False,
        )

        try:
            result = await session.prompt_async(default=initial_text)
            return result
        except KeyboardInterrupt:
            return None
        except EOFError:
            return session.default_buffer.text

    async def get_json_input(
        self,
        tool_name: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        initial_value: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Get JSON input with schema awareness."""

        prompt_lines = []
        if tool_name:
            prompt_lines.append(f"Enter JSON arguments for '{tool_name}':")
        else:
            prompt_lines.append("Enter JSON:")

        if schema and 'properties' in schema:
            prompt_lines.append("\nExpected properties:")
            required = schema.get('required', [])

            for prop, info in schema['properties'].items():
                prop_type = info.get('type', 'any')
                desc = info.get('description', '')
                is_required = prop in required

                line = f"  {prop}: {prop_type}"
                if is_required:
                    line += " (required)"
                if desc:
                    line += f" - {desc}"
                prompt_lines.append(line)

        prompt_lines.append("\n")
        prompt = '\n'.join(prompt_lines)

        if initial_value:
            initial_text = json.dumps(initial_value, indent=2)
        elif schema and 'properties' in schema:
            template = {}
            for prop, info in schema['properties'].items():
                prop_type = info.get('type', 'string')
                if prop_type == 'string':
                    template[prop] = ""
                elif prop_type == 'number':
                    template[prop] = 0
                elif prop_type == 'integer':
                    template[prop] = 0
                elif prop_type == 'boolean':
                    template[prop] = False
                elif prop_type == 'array':
                    template[prop] = []
                elif prop_type == 'object':
                    template[prop] = {}
                else:
                    template[prop] = None
            initial_text = json.dumps(template, indent=2)
        else:
            initial_text = "{\n  \n}"

        result = await self.get_multiline_input(
            prompt=prompt,
            initial_text=initial_text,
            lexer_type='json',
            validator=JSONValidator() if schema else None
        )

        if result is None:
            return None

        try:
            return json.loads(result)
        except json.JSONDecodeError as e:
            if self.formatter:
                self.formatter.format_error(f"Invalid JSON: {e}")
            return None

    async def edit_json(
        self,
        current_value: Dict[str, Any],
        title: str = "Edit JSON"
    ) -> Optional[Dict[str, Any]]:
        """Edit existing JSON data."""
        current_text = json.dumps(current_value, indent=2)

        result = await self.get_multiline_input(
            prompt=f"{title}:\n",
            initial_text=current_text,
            lexer_type='json'
        )

        if result is None:
            return None

        try:
            return json.loads(result)
        except json.JSONDecodeError as e:
            if self.formatter:
                self.formatter.format_error(f"Invalid JSON: {e}")
            return None


class InteractiveArgumentBuilder:
    """Build arguments interactively based on schema."""

    def __init__(self, formatter=None):
        self.formatter = formatter

    async def build_arguments(
        self,
        tool_name: str,
        schema: Dict[str, Any],
        session: PromptSession
    ) -> Optional[Dict[str, Any]]:
        """Interactively build arguments based on schema."""

        if not schema or 'properties' not in schema:
            handler = MultilineInputHandler(self.formatter)
            return await handler.get_json_input(tool_name)

        properties = schema['properties']
        required = schema.get('required', [])
        result = {}

        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get('type', 'string')
            description = prop_info.get('description', '')
            is_required = prop_name in required
            default = prop_info.get('default')
            enum_values = prop_info.get('enum')

            prompt_parts = [prop_name]
            if description:
                prompt_parts.append(f"({description})")

            type_hint = prop_type
            if enum_values:
                type_hint = f"[{'/'.join(str(v) for v in enum_values)}]"
            elif prop_type == 'boolean':
                type_hint = "[true/false]"

            prompt_parts.append(f"<{type_hint}>")

            if not is_required:
                if default is not None:
                    prompt_parts.append(f"[default: {default}]")
                else:
                    prompt_parts.append("[optional]")

            prompt = ' '.join(prompt_parts) + ': '

            value = await self._get_property_value(
                session, prompt, prop_type, prop_info,
                is_required, default
            )

            if value is not None:
                result[prop_name] = value
            elif is_required:
                if self.formatter:
                    self.formatter.format_error(f"Required field '{prop_name}' was not provided")
                return None

        return result

    async def _get_property_value(
        self,
        session: PromptSession,
        prompt: str,
        prop_type: str,
        prop_info: Dict[str, Any],
        is_required: bool,
        default: Any
    ) -> Any:
        """Get a single property value with validation."""

        validator = self._create_type_validator(prop_type, prop_info)

        while True:
            try:
                value = await session.prompt_async(prompt, validator=validator)

                if not value and not is_required:
                    return default

                if prop_type == 'integer':
                    return int(value)
                elif prop_type == 'number':
                    return float(value)
                elif prop_type == 'boolean':
                    return value.lower() in ('true', 'yes', '1', 'y')
                elif prop_type == 'array':
                    return [v.strip() for v in value.split(',')]
                elif prop_type == 'object':
                    handler = MultilineInputHandler(self.formatter)
                    return await handler.get_json_input()
                else:
                    return value

            except KeyboardInterrupt:
                return None
            except ValueError as e:
                if self.formatter:
                    self.formatter.format_error(f"Invalid value: {e}")
                continue

    def _create_type_validator(self, prop_type: str, prop_info: Dict[str, Any]) -> Optional[Validator]:
        """Create a validator for the property type."""
        return PropertyTypeValidator(prop_type, prop_info)
