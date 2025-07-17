"""Script management and handling for mbro."""

import re
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from magg.settings import ConfigManager
from .parser import CommandParser

if TYPE_CHECKING:
    from .cli import MCPBrowserCLI
    from .formatter import OutputFormatter


class ScriptManager:
    """Manage mbro script files and handle script commands."""
    config_manager: ConfigManager
    cli: 'MCPBrowserCLI' = None
    formatter: 'OutputFormatter' = None

    def __init__(self, *, cli: 'MCPBrowserCLI', config_path: Path | str | None = None):
        self.config_manager = ConfigManager(config_path=config_path)
        self.cli = cli
        self.formatter = cli.formatter

    @property
    def scripts(self) -> list[Path]:
        """Get all available script paths."""
        magg_config = self.config_manager.load_config()
        return magg_config.get_script_paths()

    def find_script(self, script_ref: str) -> Path | None:
        """Find a script by name or path."""
        path = Path(script_ref)
        
        if not path.suffix:
            path = path.with_suffix('.mbro')
        
        if path.is_absolute() and path.exists():
            return path
        
        if path.exists():
            return path.resolve()
        
        search = script_ref.lower()
        
        if '/' in search:
            search_path = Path(search)
            search_parts = tuple(p.lower() for p in search_path.parts[:-1])
            search_name = search_path.name.lower()
            
            for script in self.scripts:
                script_parts = tuple(p.lower() for p in script.parts[:-1])
                script_name = script.stem.lower()
                
                if script_name != search_name:
                    continue
                    
                if not search_parts:
                    return script
                    
                for i in range(len(script_parts) - len(search_parts) + 1):
                    if script_parts[i:i+len(search_parts)] == search_parts:
                        return script
        
        for script in self.scripts:
            script_name = script.stem.lower()
            if script_name == search or (script.suffix and script.name.lower() == search):
                return script
        return None

    
    async def handle_script_command(self, args: List[str]):
        """Handle script subcommands."""
        if not args:
            self.formatter.format_error("Usage: script <command> [args]\nCommands: run, list, search, dump")
            return
        
        subcmd = args[0]
        subargs = args[1:]
        
        if subcmd == "run":
            await self.run_script(subargs)
        elif subcmd == "list":
            await self.list_scripts(subargs)
        elif subcmd == "search":
            await self.search_scripts(subargs)
        elif subcmd == "dump":
            await self.dump_script(subargs)
        else:
            self.formatter.format_error(f"Unknown script command: {subcmd}\nCommands: run, list, search, dump")
    
    async def run_script(self, args: List[str]):
        """Run a script file."""
        if not args:
            self.formatter.format_error("Usage: script run <script_name_or_path>")
            return
        
        script_ref = args[0]
        
        script_path = self.find_script(script_ref)
        if not script_path:
            self.formatter.format_error(f"Script not found: {script_ref}")
            exit(1)
        
        try:
            script_content = script_path.read_text()
        except Exception as e:
            self.formatter.format_error(f"Failed to read script: {e}")
            return
        
        commands = CommandParser.split_commands(script_content)
        
        for command in commands:
            if command.strip():
                if self.cli.verbose:
                    self.formatter.format_info(f"> {command}")
                await self.cli.handle_command(command)
    
    async def list_scripts(self, args: List[str]):
        """List available scripts with optional filter."""
        filter_str = args[0] if args else None
        
        scripts = self.scripts
        
        if filter_str:
            scripts = [s for s in scripts if filter_str.lower() in s.name.lower()]
        
        if not scripts:
            if filter_str:
                self.formatter.format_warning(f"No scripts found matching '{filter_str}'")
            else:
                self.formatter.format_warning("No scripts found")
            return
        
        self.formatter.format_info(f"Available scripts ({len(scripts)}):")
        
        by_dir = {}
        for script in scripts:
            dir_path = self._get_friendly_path(script.parent)
            if dir_path not in by_dir:
                by_dir[dir_path] = []
            by_dir[dir_path].append(script)
        
        for dir_path, dir_scripts in sorted(by_dir.items()):
            self.formatter.format_info(f"\n{dir_path}:")
            for script in sorted(dir_scripts):
                desc = self._get_script_description(script)
                if desc:
                    self.formatter.format_info(f"  • {script.name} - {desc}")
                else:
                    self.formatter.format_info(f"  • {script.name}")
    
    async def search_scripts(self, args: List[str]):
        """Search scripts by regex pattern."""
        if not args:
            self.formatter.format_error("Usage: script search <pattern>")
            return
        
        pattern = args[0]
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            self.formatter.format_error(f"Invalid regex pattern: {e}")
            return
        
        matches = []
        for script in self.scripts:
            if regex.search(script.name):
                matches.append((script, "filename"))
                continue
            
            try:
                content = script.read_text()
                if regex.search(content):
                    matches.append((script, "content"))
            except Exception:
                pass
        
        if not matches:
            self.formatter.format_warning(f"No scripts found matching pattern '{pattern}'")
            return
        
        self.formatter.format_info(f"Scripts matching '{pattern}' ({len(matches)}):")
        for script, match_type in matches:
            desc = self._get_script_description(script)
            match_info = f" (matched in {match_type})"
            if desc:
                self.formatter.format_info(f"  • {script.name} - {desc}{match_info}")
            else:
                self.formatter.format_info(f"  • {script.name}{match_info}")
    
    async def dump_script(self, args: List[str]):
        """Dump script content, optionally into multiline editor."""
        if not args:
            self.formatter.format_error("Usage: script dump <script_name_or_path>")
            return
        
        script_ref = args[0]
        
        script_path = self.find_script(script_ref)
        if not script_path:
            self.formatter.format_error(f"Script not found: {script_ref}")
            exit(1)
        
        try:
            script_content = script_path.read_text()
        except Exception as e:
            self.formatter.format_error(f"Failed to read script: {e}")
            return
        
        if not self.formatter.json_only and self.cli.use_enhanced and hasattr(self.cli, 'multiline_handler'):
            self.formatter.format_info(f"Script: {script_path.name}\nPress Ctrl+D to run, Ctrl+C to cancel")
            
            edited = await self.cli.multiline_handler.get_multiline_input(
                prompt="",
                initial_text=script_content,
                lexer_type='text'
            )
            
            if edited is not None:
                commands = CommandParser.split_commands(edited)
                for command in commands:
                    if command.strip():
                        if self.cli.verbose:
                            self.formatter.format_info(f"> {command}")
                        await self.cli.handle_command(command)
        else:
            self.formatter.format_info(f"Script: {script_path.name}")
            self.formatter.print(script_content)

    @classmethod
    def _get_friendly_path(cls, path: Path) -> str:
        """Get a user-friendly path display."""
        try:
            cwd = Path.cwd()
            try:
                relative = path.relative_to(cwd)
                return str(relative)
            except ValueError:
                pass
            
            home = Path.home()
            try:
                relative = path.relative_to(home)
                return f"~/{relative}"
            except ValueError:
                pass
            
            return str(path)
        except Exception:
            return str(path)

    @classmethod
    def _get_script_description(cls, script_path: Path) -> Optional[str]:
        """Extract description from script (first non-comment line or first comment)."""
        try:
            with script_path.open() as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        return line[1:].strip()
                    elif line and not line.startswith('#'):
                        return line[:50] + "..." if len(line) > 50 else line
        except Exception:
            pass
        return None


