"""Natural language and advanced argument parsing for mbro."""

import re
import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    """Represents a parsed command with its components."""
    command: str
    args: List[str]
    raw_text: str
    confidence: float = 1.0
    
    def to_command_string(self) -> str:
        """Convert back to command string format."""
        if self.args:
            return f"{self.command} {' '.join(self.args)}"
        return self.command


class NaturalLanguageParser:
    """Parse natural language commands into structured commands."""
    
    # Pattern definitions with handlers
    PATTERNS = [
        # Direct tool calls
        (r'call (\w+)$', lambda m: ParsedCommand('call', [m.group(1)], m.group(0))),
        (r'call (\w+) with no args?$', lambda m: ParsedCommand('call', [m.group(1)], m.group(0))),
        (r'run (\w+)$', lambda m: ParsedCommand('call', [m.group(1)], m.group(0))),
        (r'execute (\w+)$', lambda m: ParsedCommand('call', [m.group(1)], m.group(0))),
        
        # Tool calls with arguments
        (r'call (\w+) with (.+)$', 'parse_call_with_args'),
        (r'run (\w+) with (.+)$', 'parse_call_with_args'),
        
        # Search commands
        (r'search for (.+)$', lambda m: ParsedCommand('search', [m.group(1)], m.group(0))),
        (r'find (.+)$', lambda m: ParsedCommand('search', [m.group(1)], m.group(0))),
        (r'look for (.+)$', lambda m: ParsedCommand('search', [m.group(1)], m.group(0))),
        
        # Listing commands
        (r'show (?:me )?(?:all )?tools?$', lambda m: ParsedCommand('tools', [], m.group(0))),
        (r'list (?:all )?tools?$', lambda m: ParsedCommand('tools', [], m.group(0))),
        (r'what tools (?:are )?available\??$', lambda m: ParsedCommand('tools', [], m.group(0))),
        
        (r'show (?:me )?(?:all )?resources?$', lambda m: ParsedCommand('resources', [], m.group(0))),
        (r'list (?:all )?resources?$', lambda m: ParsedCommand('resources', [], m.group(0))),
        (r'what resources (?:are )?available\??$', lambda m: ParsedCommand('resources', [], m.group(0))),
        
        (r'show (?:me )?(?:all )?prompts?$', lambda m: ParsedCommand('prompts', [], m.group(0))),
        (r'list (?:all )?prompts?$', lambda m: ParsedCommand('prompts', [], m.group(0))),
        
        # Connection commands
        (r'connect to (\w+) (?:at|on) (.+)$', lambda m: ParsedCommand('connect', [m.group(1), m.group(2)], m.group(0))),
        (r'connect (\w+) to (.+)$', lambda m: ParsedCommand('connect', [m.group(1), m.group(2)], m.group(0))),
        
        # Info commands
        (r'(?:show|get) (?:me )?info (?:about|on|for) (\w+) (\w+)$', 
         lambda m: ParsedCommand('info', [m.group(1), m.group(2)], m.group(0))),
        (r'describe (\w+) (\w+)$', lambda m: ParsedCommand('info', [m.group(1), m.group(2)], m.group(0))),
        
        # Status commands
        (r'(?:show )?status$', lambda m: ParsedCommand('status', [], m.group(0))),
        (r'where am i\??$', lambda m: ParsedCommand('status', [], m.group(0))),
        (r'what(?:\'s| is) (?:my )?(?:current )?connection\??$', lambda m: ParsedCommand('status', [], m.group(0))),
        
        # Exit commands
        (r'(?:quit|exit|bye|goodbye)$', lambda m: ParsedCommand('quit', [], m.group(0))),
    ]
    
    def parse(self, text: str) -> Optional[ParsedCommand]:
        """Parse natural language text into a command."""
        text = text.strip()
        text_lower = text.lower()
        
        # Try each pattern
        for pattern, handler in self.PATTERNS:
            match = re.match(pattern, text_lower)
            if match:
                if isinstance(handler, str):
                    # Call method by name
                    handler = getattr(self, handler)
                result = handler(match)
                if result:
                    result.raw_text = text  # Preserve original text
                    return result
        
        return None
    
    def parse_call_with_args(self, match: re.Match) -> ParsedCommand:
        """Parse 'call tool with key=value' style arguments."""
        tool_name = match.group(1)
        args_str = match.group(2)
        
        # Try different argument formats
        
        # 1. Check if it's already JSON
        if args_str.strip().startswith('{'):
            return ParsedCommand('call', [tool_name, args_str], match.group(0))
        
        # 2. Try key=value format
        args_dict = self._parse_key_value_args(args_str)
        if args_dict:
            return ParsedCommand('call', [tool_name, json.dumps(args_dict)], match.group(0))
        
        # 3. Try natural language patterns
        nl_args = self._parse_natural_args(args_str)
        if nl_args:
            return ParsedCommand('call', [tool_name, json.dumps(nl_args)], match.group(0))
        
        # 4. Fall back to passing as-is
        return ParsedCommand('call', [tool_name, args_str], match.group(0), confidence=0.5)
    
    def _parse_key_value_args(self, args_str: str) -> Optional[Dict[str, Any]]:
        """Parse key=value style arguments."""
        # Split by common separators
        pairs = re.split(r'\s*(?:,|and|&)\s*', args_str)
        
        args_dict = {}
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Type inference
                args_dict[key] = self._infer_type(value)
            else:
                # Not a key=value format
                return None
        
        return args_dict if args_dict else None
    
    def _parse_natural_args(self, args_str: str) -> Optional[Dict[str, Any]]:
        """Parse natural language argument patterns."""
        args_dict = {}
        
        # Pattern: "5 as a and 3 as b"
        pattern = r'(\w+)\s+as\s+(\w+)'
        for match in re.finditer(pattern, args_str):
            value, key = match.groups()
            args_dict[key] = self._infer_type(value)
        
        # Pattern: "a of 5 and b of 3"
        pattern = r'(\w+)\s+of\s+(\w+)'
        for match in re.finditer(pattern, args_str):
            key, value = match.groups()
            args_dict[key] = self._infer_type(value)
        
        return args_dict if args_dict else None
    
    def _infer_type(self, value: str) -> Any:
        """Infer the type of a string value."""
        value = value.strip()
        
        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # Boolean
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer
        if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return int(value)
        
        # Float
        try:
            if '.' in value:
                return float(value)
        except ValueError:
            pass
        
        # List (simple comma-separated)
        if ',' in value:
            items = [self._infer_type(item.strip()) for item in value.split(',')]
            return items
        
        # Default to string
        return value


class ArgumentParser:
    """Parse and validate command arguments."""
    
    def __init__(self):
        self.nl_parser = NaturalLanguageParser()
    
    def parse_command(self, text: str) -> Tuple[str, List[str]]:
        """Parse a command string into command and arguments."""
        # First try natural language parsing
        parsed = self.nl_parser.parse(text)
        if parsed and parsed.confidence > 0.7:
            return parsed.command, parsed.args
        
        # Fall back to traditional parsing
        # Handle potential JSON in arguments
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
        
        # Handle remaining content
        if current:
            if in_json:
                parts.append(''.join(current))
            else:
                parts.extend(''.join(current).split())
        
        if not parts:
            return '', []
        
        command = parts[0].lower()
        args = parts[1:]
        
        # Post-process arguments
        args = self._process_arguments(command, args)
        
        return command, args
    
    def _process_arguments(self, command: str, args: List[str]) -> List[str]:
        """Process and enhance arguments based on command context."""
        if not args:
            return args
        
        if command == 'call' and len(args) > 1:
            # Try to intelligently parse non-JSON arguments
            tool_name = args[0]
            remaining = ' '.join(args[1:])
            
            # If it's not already JSON, try to convert it
            if not remaining.strip().startswith('{'):
                converted = self._convert_to_json(remaining)
                if converted:
                    return [tool_name, converted]
        
        return args
    
    def _convert_to_json(self, arg_string: str) -> Optional[str]:
        """Try to convert various argument formats to JSON."""
        # Already JSON?
        if arg_string.strip().startswith('{'):
            return arg_string
        
        # Try key=value format
        if '=' in arg_string:
            args_dict = {}
            pairs = re.split(r'\s+', arg_string)
            
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    args_dict[key] = self.nl_parser._infer_type(value)
            
            if args_dict:
                return json.dumps(args_dict)
        
        return None


class SmartSuggestions:
    """Provide intelligent suggestions based on context and errors."""
    
    def __init__(self, cli_instance):
        self.cli = cli_instance
    
    def suggest_for_error(self, error: str, context: Dict[str, Any]) -> List[str]:
        """Suggest fixes based on error and context."""
        suggestions = []
        
        if "json" in error.lower():
            suggestions.append("Use Ctrl+M to open multiline JSON editor")
            suggestions.append("Ensure proper JSON formatting with double quotes")
            
            # Try to fix common JSON errors
            if context.get('json_string'):
                fixed = self._attempt_json_fix(context['json_string'])
                if fixed:
                    suggestions.append(f"Try: {fixed}")
        
        elif "not found" in error.lower():
            item = context.get('item_name', '')
            item_type = context.get('item_type', 'item')
            
            # Get similar items
            similar = self._find_similar_items(item, item_type)
            if similar:
                suggestions.append(f"Did you mean: {', '.join(similar[:3])}")
        
        elif "connection" in error.lower():
            suggestions.append("Use 'connections' to see available connections")
            suggestions.append("Use 'connect <name> <url>' to create a new connection")
        
        return suggestions
    
    def _attempt_json_fix(self, json_string: str) -> Optional[str]:
        """Attempt to fix common JSON errors."""
        # Replace single quotes with double quotes
        fixed = json_string.replace("'", '"')
        
        # Try to parse
        try:
            json.loads(fixed)
            return fixed
        except:
            pass
        
        # Add missing quotes around keys
        fixed = re.sub(r'(\w+):', r'"\1":', fixed)
        
        try:
            json.loads(fixed)
            return fixed
        except:
            pass
        
        return None
    
    def _find_similar_items(self, item: str, item_type: str) -> List[str]:
        """Find similar items of the given type."""
        from difflib import get_close_matches
        
        conn = self.cli.browser.get_current_connection()
        if not conn:
            return []
        
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if item_type == 'tool':
                items = loop.run_until_complete(conn.get_tools())
            elif item_type == 'resource':
                items = loop.run_until_complete(conn.get_resources())
            elif item_type == 'prompt':
                items = loop.run_until_complete(conn.get_prompts())
            else:
                loop.close()
                return []
            
            loop.close()
            
            names = [i['name'] for i in items]
            return get_close_matches(item, names, n=3, cutoff=0.6)
            
        except:
            return []