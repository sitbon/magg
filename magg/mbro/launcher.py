"""
Server launcher module for mbro.

Provides intelligent detection and execution of MCP servers from various sources:
- Command strings
- NPM packages 
- Python packages
- Git repositories
- HTTP endpoints

Uses FastMCP capabilities and optionally LLM sampling to determine the best way to run a server.
"""

import asyncio
import shutil
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass

from fastmcp import Client


@dataclass
class ServerLaunchInfo:
    """Information needed to launch an MCP server."""
    name: str
    launch_method: str  # 'command', 'npm', 'python', 'http', 'git'
    connection_string: str
    description: str = ""
    working_dir: str | None = None
    environment: dict[str, str] | None = None
    install_command: str | None = None


class ServerLauncher:
    """Intelligent MCP server launcher."""
    
    def __init__(self):
        self.known_patterns = {
            # NPM patterns
            'npx': 'npm',
            'npm': 'npm', 
            'node': 'node',
            # Python patterns
            'python': 'python',
            'python3': 'python',
            'uv': 'python',
            'uvx': 'python',
            'pip': 'python',
            'pipx': 'python',
            # Git patterns
            'git': 'git',
            # HTTP patterns
            'http': 'http',
            'https': 'http'
        }
    
    def analyze_server_description(self, description: str) -> ServerLaunchInfo:
        """
        Analyze a server description and determine how to launch it.
        
        Args:
            description: Can be:
                - Command: "npx @wrtnlabs/calculator-mcp" 
                - NPM package: "@wrtnlabs/calculator-mcp"
                - HTTP URL: "http://localhost:8080"
                - Git repo: "https://github.com/user/repo.git"
                - Complex command: "uv run python -m mypackage"
        """
        description = description.strip()
        
        # HTTP URLs
        if description.startswith(('http://', 'https://')):
            return ServerLaunchInfo(
                name=self._extract_name_from_url(description),
                launch_method='http',
                connection_string=description,
                description=f"HTTP MCP server at {description}"
            )
        
        # Git repositories
        if description.endswith('.git') or 'github.com' in description:
            return ServerLaunchInfo(
                name=self._extract_name_from_git(description),
                launch_method='git',
                connection_string=description,
                description=f"Git repository: {description}",
                install_command=f"git clone {description}"
            )
        
        # NPM packages (starting with @)
        if description.startswith('@') and not ' ' in description:
            return ServerLaunchInfo(
                name=description.replace('@', '').replace('/', '-'),
                launch_method='npm',
                connection_string=self._generate_npm_command(description),
                description=f"NPM package: {description}",
                install_command=f"npm install -g {description}"
            )
        
        # Command strings
        parts = description.split()
        if len(parts) > 0:
            first_cmd = parts[0]
            
            # Detect command type
            if first_cmd in self.known_patterns:
                method = self.known_patterns[first_cmd]
                return ServerLaunchInfo(
                    name=self._extract_name_from_command(description),
                    launch_method='command',
                    connection_string=self._normalize_command(description),
                    description=f"Command: {description}"
                )
        
        # Fallback - treat as generic command
        return ServerLaunchInfo(
            name=self._extract_name_from_command(description),
            launch_method='command', 
            connection_string=description,
            description=f"Generic command: {description}"
        )
    
    def _extract_name_from_url(self, url: str) -> str:
        """Extract a name from a URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.path and parsed.path != '/':
            return parsed.path.strip('/').replace('/', '_')
        return f"{parsed.hostname}_{parsed.port or 80}"
    
    def _extract_name_from_git(self, git_url: str) -> str:
        """Extract a name from a git URL."""
        # Extract repo name from URL like https://github.com/user/repo.git
        if 'github.com' in git_url:
            parts = git_url.split('/')
            repo_name = parts[-1].replace('.git', '')
            return repo_name
        return 'git_repo'
    
    def _extract_name_from_command(self, command: str) -> str:
        """Extract a reasonable name from a command string."""
        parts = command.split()
        if len(parts) == 0:
            return 'unknown'
        
        # Try to find a meaningful name
        for part in parts:
            if part.startswith('@'):
                return part.replace('@', '').replace('/', '-')
            elif part.endswith('-mcp') or 'mcp' in part:
                return part.replace('-', '_')
        
        # Use first command as fallback
        return parts[0].replace('-', '_')
    
    def _generate_npm_command(self, package: str) -> str:
        """Generate the best npm command for a package."""
        # Check if npx is available, otherwise use npm + node
        if shutil.which('npx'):
            return f"npx {package}"
        else:
            return f"npm install -g {package} && node $(npm root -g)/{package}"
    
    def _normalize_command(self, command: str) -> str:
        """Normalize a command string for FastMCP compatibility."""
        parts = command.split()
        
        # Handle special cases
        if len(parts) >= 3 and parts[0] == 'uv' and parts[1] == 'run':
            # Convert "uv run magg" to FastMCP-compatible format
            # For now, return as-is and let FastMCP handle it
            return command
        
        # For most commands, return as-is
        return command
    
    async def test_server_launch(self, launch_info: ServerLaunchInfo, timeout: float = 10.0) -> bool:
        """Test if a server can be successfully launched and responds to MCP calls."""
        try:
            if launch_info.launch_method == 'http':
                return await self._test_http_server(launch_info.connection_string, timeout)
            else:
                return await self._test_command_server(launch_info.connection_string, timeout)
        except Exception as e:
            print(f"Failed to test server launch: {e}")
            return False
    
    async def _test_http_server(self, url: str, timeout: float) -> bool:
        """Test HTTP MCP server connectivity."""
        try:
            # Ensure URL has MCP endpoint
            if not url.endswith('/mcp'):
                url = url.rstrip('/') + '/mcp'
            
            client = Client(url)
            async with client as conn:
                await conn.list_tools()
                return True
        except Exception:
            return False
    
    async def _test_command_server(self, command: str, timeout: float) -> bool:
        """Test command-based MCP server connectivity."""
        try:
            # Try different FastMCP Client formats
            formats_to_try = [
                command,  # As string
                command.split(),  # As list
            ]
            
            for cmd_format in formats_to_try:
                try:
                    client = Client(cmd_format)
                    async with client as conn:
                        await asyncio.wait_for(conn.list_tools(), timeout=timeout)
                        return True
                except Exception:
                    continue
            
            return False
        except Exception:
            return False
    
    def get_installation_suggestions(self, launch_info: ServerLaunchInfo) -> list[str]:
        """Get installation suggestions for a server that fails to launch."""
        suggestions = []
        
        if launch_info.launch_method == 'npm':
            suggestions.extend([
                "npm install -g " + launch_info.name,
                "npx " + launch_info.name + " --help",
                "Check if Node.js and npm are installed"
            ])
        
        elif launch_info.launch_method == 'python':
            suggestions.extend([
                "pip install " + launch_info.name,
                "uv add " + launch_info.name,
                "uvx " + launch_info.name + " --help",
                "Check if Python and pip/uv are installed"
            ])
        
        elif launch_info.launch_method == 'git':
            suggestions.extend([
                launch_info.install_command or f"git clone {launch_info.connection_string}",
                "cd to cloned directory and check README for setup instructions",
                "Look for package.json, pyproject.toml, or requirements.txt"
            ])
        
        elif launch_info.launch_method == 'http':
            suggestions.extend([
                "Check if the HTTP server is running",
                "Verify the URL is correct and accessible",
                "Check firewall settings"
            ])
        
        else:
            suggestions.extend([
                "Check if the command exists in PATH",
                "Try running the command manually first",
                "Check for typos in the command"
            ])
        
        return suggestions
    
    async def smart_launch_with_retry(self, description: str, max_retries: int = 3) -> tuple[bool, ServerLaunchInfo, list[str]]:
        """
        Intelligently launch a server with retries and suggestions.
        
        Returns:
            (success, launch_info, error_messages)
        """
        launch_info = self.analyze_server_description(description)
        errors = []
        
        for attempt in range(max_retries):
            try:
                success = await self.test_server_launch(launch_info)
                if success:
                    return True, launch_info, []
                
                errors.append(f"Attempt {attempt + 1}: Server did not respond to MCP calls")
                
                # Try alternative approaches
                if attempt < max_retries - 1:
                    if launch_info.launch_method == 'command':
                        # Try with different command formats
                        alternatives = self._generate_command_alternatives(description)
                        for alt in alternatives:
                            alt_info = ServerLaunchInfo(
                                name=launch_info.name,
                                launch_method='command',
                                connection_string=alt,
                                description=f"Alternative: {alt}"
                            )
                            if await self.test_server_launch(alt_info):
                                return True, alt_info, []
                
            except Exception as e:
                errors.append(f"Attempt {attempt + 1}: {e}")
        
        return False, launch_info, errors
    
    def _generate_command_alternatives(self, original: str) -> list[str]:
        """Generate alternative command formats to try."""
        alternatives = []
        parts = original.split()
        
        # Try different quoting approaches
        if len(parts) > 1:
            alternatives.append(f'"{original}"')  # Quoted entire command
            alternatives.append(' '.join(f'"{part}"' for part in parts))  # Quote each part
        
        # Try with explicit shell
        alternatives.append(f"sh -c '{original}'")
        alternatives.append(f"bash -c '{original}'")
        
        # Try with path resolution
        if len(parts) > 0:
            first_cmd = parts[0]
            which_result = shutil.which(first_cmd)
            if which_result:
                alternatives.append(' '.join([which_result] + parts[1:]))
        
        return alternatives


# Convenience functions for external use
async def quick_launch(description: str) -> tuple[bool, ServerLaunchInfo]:
    """Quick server launch test."""
    launcher = ServerLauncher()
    success, info, errors = await launcher.smart_launch_with_retry(description)
    return success, info


def analyze_server(description: str) -> ServerLaunchInfo:
    """Analyze a server description without launching."""
    launcher = ServerLauncher()
    return launcher.analyze_server_description(description)