"""Source metadata collection and analysis."""

import asyncio
import aiohttp
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .catalog import CatalogManager
from .search import ToolSearchResult


class SourceMetadataCollector:
    """Collects rich metadata about MCP sources from multiple sources."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.catalog_manager = CatalogManager()

    async def collect_metadata(self, url: str, name: str | None = None) -> list[dict[str, Any]]:
        """Collect metadata from all available sources."""
        metadata = []

        # Determine collection strategy based on URL type
        if url.startswith('file://') or (not url.startswith('http') and '/' in url):
            # Local file system source
            tasks = [
                self._collect_filesystem_metadata(url),
                self._collect_search_metadata(url, name),  # Still search for name if provided
            ]
        else:
            # Remote source (HTTP/GitHub)
            tasks = [
                self._collect_http_metadata(url),
                self._collect_search_metadata(url, name),
                self._collect_github_metadata(url),
            ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and add successful ones to metadata
        for result in results:
            if isinstance(result, dict) and result:
                metadata.append(result)
            elif isinstance(result, Exception):
                self.logger.debug(f"Metadata collection error: {result}")

        return metadata

    async def _collect_http_metadata(self, url: str) -> dict[str, Any]:
        """Check if URL is a direct MCP server via HTTP with strict detection."""
        try:
            # Skip HTTP check for known non-MCP domains
            known_non_mcp_domains = [
                'npmjs.com', 'github.com', 'gitlab.com', 'bitbucket.org',
                'pypi.org', 'crates.io', 'packagist.org', 'nuget.org'
            ]

            parsed_url = urlparse(url)
            if any(domain in parsed_url.netloc for domain in known_non_mcp_domains):
                return {
                    "source": "http_check",
                    "collected_at": datetime.now().isoformat(),
                    "data": {
                        "is_mcp_server": False,
                        "skipped_reason": f"Known non-MCP domain: {parsed_url.netloc}",
                        "accessible": "unknown"
                    }
                }

            # Only check URLs that look like actual server endpoints
            if not self._looks_like_server_url(url):
                return {
                    "source": "http_check",
                    "collected_at": datetime.now().isoformat(),
                    "data": {
                        "is_mcp_server": False,
                        "skipped_reason": "URL doesn't look like a server endpoint",
                        "accessible": "unknown"
                    }
                }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # Try MCP-specific endpoint first
                mcp_endpoint = url.rstrip('/') + '/mcp'
                try:
                    async with session.post(mcp_endpoint, json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}}
                    }) as response:
                        if response.status == 200:
                            content = await response.text()
                            try:
                                data = json.loads(content)
                                # Valid MCP response should have jsonrpc and result
                                if (data.get("jsonrpc") == "2.0" and
                                    "result" in data and
                                    isinstance(data["result"], dict)):
                                    return {
                                        "source": "http_check",
                                        "collected_at": datetime.now().isoformat(),
                                        "data": {
                                            "is_mcp_server": True,
                                            "verification": "Responded to MCP initialize request",
                                            "mcp_endpoint": mcp_endpoint,
                                            "accessible": True
                                        }
                                    }
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass

                # If no MCP endpoint, mark as not an MCP server
                return {
                    "source": "http_check",
                    "collected_at": datetime.now().isoformat(),
                    "data": {
                        "is_mcp_server": False,
                        "verification": "No response to MCP initialize request",
                        "accessible": True
                    }
                }

        except Exception as e:
            return {
                "source": "http_check",
                "collected_at": datetime.now().isoformat(),
                "data": {
                    "is_mcp_server": False,
                    "error": str(e),
                    "accessible": False
                }
            }

    def _looks_like_server_url(self, url: str) -> bool:
        """Check if URL looks like it could be a server endpoint."""
        parsed = urlparse(url)

        # Skip if it looks like a package page or repository
        path_parts = parsed.path.lower().split('/')

        # NPM package paths
        if 'package' in path_parts:
            return False

        # GitHub repository paths
        if len(path_parts) >= 3 and parsed.netloc == 'github.com':
            return False

        # PyPI package paths
        if 'project' in path_parts and 'pypi.org' in parsed.netloc:
            return False

        # URLs with ports or localhost are more likely to be servers
        if parsed.port or 'localhost' in parsed.netloc or '127.0.0.1' in parsed.netloc:
            return True

        # URLs ending in common server paths
        server_path_indicators = ['/mcp', '/server', '/api', '/rpc']
        if any(indicator in parsed.path for indicator in server_path_indicators):
            return True

        # Base domain without path - could be a server
        if not parsed.path or parsed.path == '/':
            return True

        return False


    async def _collect_search_metadata(self, url: str, name: str | None = None) -> dict[str, Any]:
        """Collect metadata from search results."""
        try:
            # Search for the name or extract from URL
            search_term = name or self._extract_name_from_url(url)
            if not search_term:
                return {}

            # Search across all sources
            search_results = await self.catalog_manager.search_only(search_term, limit_per_source=3)

            # Find matching results
            matching_results = []
            for source_name, results in search_results.items():
                for result in results:
                    if result.url and (url in result.url or result.url in url):
                        matching_results.append({
                            "search_source": source_name,
                            "name": result.name,
                            "description": result.description,
                            "url": result.url,
                            "install_command": result.install_command,
                            "rating": result.rating,
                            "tags": getattr(result, 'tags', [])
                        })

            if matching_results:
                return {
                    "source": "search_results",
                    "collected_at": datetime.now().isoformat(),
                    "data": {
                        "search_term": search_term,
                        "matches": matching_results,
                        "total_matches": len(matching_results)
                    }
                }

        except Exception as e:
            self.logger.debug(f"Search metadata collection failed: {e}")

        return {}

    async def _collect_github_metadata(self, url: str) -> dict[str, Any]:
        """Collect metadata from GitHub if it's a GitHub URL."""
        if 'github.com' not in url:
            return {}

        try:
            # Extract owner/repo from GitHub URL
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 2:
                return {}

            owner, repo = path_parts[0], path_parts[1]

            # Fetch from GitHub API
            async with aiohttp.ClientSession() as session:
                api_url = f"https://api.github.com/repos/{owner}/{repo}"

                async with session.get(api_url) as response:
                    if response.status == 200:
                        repo_data = await response.json()

                        # Get README for setup instructions
                        readme_content = await self._fetch_github_readme(session, owner, repo)
                        setup_hints = self._extract_setup_instructions(readme_content)

                        return {
                            "source": "github",
                            "collected_at": datetime.now().isoformat(),
                            "data": {
                                "name": repo_data.get("name"),
                                "description": repo_data.get("description"),
                                "language": repo_data.get("language"),
                                "stars": repo_data.get("stargazers_count"),
                                "forks": repo_data.get("forks_count"),
                                "topics": repo_data.get("topics", []),
                                "license": repo_data.get("license", {}).get("name") if repo_data.get("license") else None,
                                "updated_at": repo_data.get("updated_at"),
                                "setup_instructions": setup_hints,
                                "clone_url": repo_data.get("clone_url"),
                                "default_branch": repo_data.get("default_branch", "main")
                            }
                        }

        except Exception as e:
            self.logger.debug(f"GitHub metadata collection failed: {e}")

        return {}

    async def _fetch_github_readme(self, session: aiohttp.ClientSession, owner: str, repo: str) -> str:
        """Fetch README content from GitHub."""
        readme_files = ["README.md", "README.rst", "README.txt", "README"]

        for readme_file in readme_files:
            try:
                url = f"https://api.github.com/repos/{owner}/{repo}/contents/{readme_file}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("content"):
                            import base64
                            content = base64.b64decode(data["content"]).decode('utf-8')
                            return content
            except:
                continue

        return ""

    def _extract_setup_instructions(self, readme_content: str) -> list[str]:
        """Extract setup/installation instructions from README."""
        if not readme_content:
            return []

        instructions = []

        # Look for common setup sections
        setup_patterns = [
            r"#+\s*(installation|install|setup|getting started|quick start).*?(?=#+|\Z)",
            r"```(?:bash|shell|sh)\s*(.*?)```",
            r"`([^`]+)`",
        ]

        for pattern in setup_patterns:
            matches = re.finditer(pattern, readme_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                text = match.group(1) if match.groups() else match.group(0)
                if any(keyword in text.lower() for keyword in ['npm', 'pip', 'install', 'run', 'start']):
                    instructions.append(text.strip())

        # Extract command-like patterns
        command_patterns = [
            r"npm\s+install\s+[^\s\n]+",
            r"pip\s+install\s+[^\s\n]+",
            r"npx\s+[^\s\n]+",
            r"python\s+[^\s\n]+\.py",
            r"node\s+[^\s\n]+\.js",
        ]

        for pattern in command_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            instructions.extend(matches)

        return list(set(instructions))  # Remove duplicates

    def _extract_name_from_url(self, url: str) -> str | None:
        """Extract a searchable name from the URL."""
        if 'github.com' in url:
            parsed = urlparse(url)
            parts = parsed.path.strip('/').split('/')
            if len(parts) >= 2:
                return parts[1]  # repo name
        elif 'npmjs.com' in url:
            if '/package/' in url:
                return url.split('/package/')[-1].split('/')[0]

        return None

    async def _collect_filesystem_metadata(self, url: str) -> dict[str, Any]:
        """Collect metadata from local filesystem source."""
        try:
            # Handle file:// URLs and local paths
            if url.startswith('file://'):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                local_path = Path(parsed.path)
            else:
                # Assume it's a local path
                local_path = Path(url).expanduser().resolve()

            if not local_path.exists():
                return {
                    "source": "filesystem",
                    "collected_at": datetime.now().isoformat(),
                    "data": {
                        "exists": False,
                        "error": f"Path does not exist: {local_path}"
                    }
                }

            metadata = {
                "source": "filesystem",
                "collected_at": datetime.now().isoformat(),
                "data": {
                    "exists": True,
                    "path": str(local_path),
                    "is_directory": local_path.is_dir(),
                    "is_file": local_path.is_file(),
                }
            }

            if local_path.is_dir():
                # Collect directory metadata
                dir_metadata = await self._analyze_directory(local_path)
                metadata["data"].update(dir_metadata)
            elif local_path.is_file():
                # Collect file metadata
                file_metadata = await self._analyze_file(local_path)
                metadata["data"].update(file_metadata)

            return metadata

        except Exception as e:
            return {
                "source": "filesystem",
                "collected_at": datetime.now().isoformat(),
                "data": {
                    "exists": False,
                    "error": f"Filesystem analysis failed: {str(e)}"
                }
            }

    async def _analyze_directory(self, dir_path: Path) -> dict[str, Any]:
        """Analyze a local directory for MCP-relevant files and structure."""
        analysis = {
            "project_files": {},
            "config_files": {},
            "documentation": {},
            "potential_commands": [],
            "setup_indicators": [],
            "project_type": "unknown"
        }

        try:
            # Key files to look for
            key_files = {
                # Package management
                "package.json": "node_project",
                "pyproject.toml": "python_project",
                "requirements.txt": "python_project",
                "Pipfile": "python_project",
                "poetry.lock": "python_project",
                "setup.py": "python_project",
                "go.mod": "go_project",
                "Cargo.toml": "rust_project",
                "pom.xml": "java_project",
                "build.gradle": "java_project",

                # Build/Make files
                "Makefile": "make_project",
                "makefile": "make_project",
                "CMakeLists.txt": "cmake_project",
                "Dockerfile": "docker_project",

                # Documentation
                "README.md": "documentation",
                "README.rst": "documentation",
                "README.txt": "documentation",
                "README": "documentation",
                "CLAUDE.md": "claude_instructions",
                ".claude.md": "claude_instructions",

                # MCP specific
                "mcp.json": "mcp_config",
                ".mcp.json": "mcp_config",
                "server.py": "potential_mcp_server",
                "server.js": "potential_mcp_server",
                "index.js": "potential_entry_point",
                "main.py": "potential_entry_point",
                "__main__.py": "potential_entry_point",
            }

            found_files = {}
            project_types = set()

            # Scan directory
            for file_path in dir_path.iterdir():
                if file_path.is_file():
                    filename = file_path.name
                    if filename in key_files:
                        file_type = key_files[filename]
                        found_files[filename] = {
                            "type": file_type,
                            "path": str(file_path),
                            "size": file_path.stat().st_size
                        }

                        if file_type.endswith('_project'):
                            project_types.add(file_type)

            analysis["project_files"] = found_files

            # Determine primary project type
            if project_types:
                # Priority order for project type detection
                type_priority = [
                    "node_project", "python_project", "go_project",
                    "rust_project", "java_project", "make_project"
                ]
                for ptype in type_priority:
                    if ptype in project_types:
                        analysis["project_type"] = ptype
                        break

            # Analyze specific files for setup hints
            if "package.json" in found_files:
                package_analysis = await self._analyze_package_json(dir_path / "package.json")
                analysis["config_files"]["package.json"] = package_analysis
                analysis["potential_commands"].extend(package_analysis.get("scripts", []))

            if "pyproject.toml" in found_files:
                pyproject_analysis = await self._analyze_pyproject_toml(dir_path / "pyproject.toml")
                analysis["config_files"]["pyproject.toml"] = pyproject_analysis
                analysis["potential_commands"].extend(pyproject_analysis.get("scripts", []))

            if "requirements.txt" in found_files:
                req_analysis = await self._analyze_requirements_txt(dir_path / "requirements.txt")
                analysis["config_files"]["requirements.txt"] = req_analysis

            # Analyze README for setup instructions
            readme_files = [f for f in found_files.keys() if f.startswith("README")]
            if readme_files:
                readme_path = dir_path / readme_files[0]  # Use first README found
                readme_analysis = await self._analyze_readme_file(readme_path)
                analysis["documentation"]["readme"] = readme_analysis
                analysis["setup_indicators"].extend(readme_analysis.get("setup_commands", []))

            # Analyze CLAUDE.md if present
            claude_files = [f for f in found_files.keys() if "CLAUDE" in f.upper()]
            if claude_files:
                claude_path = dir_path / claude_files[0]
                claude_analysis = await self._analyze_claude_file(claude_path)
                analysis["documentation"]["claude"] = claude_analysis
                analysis["setup_indicators"].extend(claude_analysis.get("instructions", []))

            # Generate setup hints based on project type
            setup_hints = self._generate_setup_hints(analysis)
            analysis["setup_hints"] = setup_hints

        except Exception as e:
            analysis["error"] = f"Directory analysis failed: {str(e)}"

        return analysis

    async def _analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze a single file."""
        analysis = {
            "filename": file_path.name,
            "size": file_path.stat().st_size,
            "extension": file_path.suffix,
            "file_type": "unknown"
        }

        # Determine file type
        if file_path.suffix in ['.py', '.js', '.ts', '.go', '.rs', '.java']:
            analysis["file_type"] = "executable"
            analysis["language"] = file_path.suffix[1:]  # Remove dot
        elif file_path.suffix in ['.json', '.toml', '.yaml', '.yml']:
            analysis["file_type"] = "config"
        elif file_path.suffix in ['.md', '.rst', '.txt']:
            analysis["file_type"] = "documentation"

        return analysis

    async def _analyze_package_json(self, package_path: Path) -> dict[str, Any]:
        """Analyze package.json for Node.js projects."""
        try:
            with open(package_path, 'r') as f:
                package_data = json.load(f)

            analysis = {
                "name": package_data.get("name"),
                "description": package_data.get("description"),
                "version": package_data.get("version"),
                "main": package_data.get("main", "index.js"),
                "scripts": [],
                "dependencies": list(package_data.get("dependencies", {}).keys()),
                "dev_dependencies": list(package_data.get("devDependencies", {}).keys())
            }

            # Extract relevant scripts
            scripts = package_data.get("scripts", {})
            for script_name, script_cmd in scripts.items():
                if any(keyword in script_name.lower() for keyword in ['start', 'serve', 'server', 'mcp']):
                    analysis["scripts"].append(f"npm run {script_name}")

            # Check for MCP-related dependencies
            all_deps = analysis["dependencies"] + analysis["dev_dependencies"]
            mcp_deps = [dep for dep in all_deps if 'mcp' in dep.lower()]
            if mcp_deps:
                analysis["mcp_dependencies"] = mcp_deps

            return analysis

        except Exception as e:
            return {"error": f"Failed to parse package.json: {str(e)}"}

    async def _analyze_pyproject_toml(self, pyproject_path: Path) -> dict[str, Any]:
        """Analyze pyproject.toml for Python projects."""
        try:
            import tomllib
            with open(pyproject_path, 'rb') as f:
                pyproject_data = tomllib.load(f)

            analysis = {
                "scripts": [],
                "dependencies": [],
                "dev_dependencies": []
            }

            # Extract project info
            if "project" in pyproject_data:
                project = pyproject_data["project"]
                analysis.update({
                    "name": project.get("name"),
                    "description": project.get("description"),
                    "version": project.get("version"),
                    "dependencies": project.get("dependencies", [])
                })

            # Extract scripts from tool.poetry or project.scripts
            if "project" in pyproject_data and "scripts" in pyproject_data["project"]:
                scripts = pyproject_data["project"]["scripts"]
                for script_name, script_path in scripts.items():
                    analysis["scripts"].append(f"python -m {script_path}")

            # Check for MCP dependencies
            deps = analysis["dependencies"]
            mcp_deps = [dep for dep in deps if 'mcp' in dep.lower()]
            if mcp_deps:
                analysis["mcp_dependencies"] = mcp_deps

            return analysis

        except Exception as e:
            return {"error": f"Failed to parse pyproject.toml: {str(e)}"}

    async def _analyze_requirements_txt(self, req_path: Path) -> dict[str, Any]:
        """Analyze requirements.txt for Python projects."""
        try:
            with open(req_path, 'r') as f:
                lines = f.readlines()

            dependencies = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before ==, >=, etc.)
                    package = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                    dependencies.append(package)

            analysis = {
                "dependencies": dependencies,
                "total_dependencies": len(dependencies)
            }

            # Check for MCP dependencies
            mcp_deps = [dep for dep in dependencies if 'mcp' in dep.lower()]
            if mcp_deps:
                analysis["mcp_dependencies"] = mcp_deps

            return analysis

        except Exception as e:
            return {"error": f"Failed to parse requirements.txt: {str(e)}"}

    async def _analyze_readme_file(self, readme_path: Path) -> dict[str, Any]:
        """Analyze README file for setup instructions."""
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Use existing README analysis from parent class
            setup_commands = self._extract_setup_instructions(content)

            analysis = {
                "length": len(content),
                "setup_commands": setup_commands,
                "has_installation_section": any(
                    section in content.lower()
                    for section in ['installation', 'install', 'setup', 'getting started']
                ),
                "mentions_mcp": 'mcp' in content.lower() or 'model context protocol' in content.lower()
            }

            return analysis

        except Exception as e:
            return {"error": f"Failed to parse README: {str(e)}"}

    async def _analyze_claude_file(self, claude_path: Path) -> dict[str, Any]:
        """Analyze CLAUDE.md file for AI instructions."""
        try:
            with open(claude_path, 'r', encoding='utf-8') as f:
                content = f.read()

            analysis = {
                "length": len(content),
                "instructions": [],
                "mentions_mcp": 'mcp' in content.lower(),
                "mentions_server": 'server' in content.lower(),
                "has_setup_info": any(
                    keyword in content.lower()
                    for keyword in ['install', 'setup', 'run', 'start', 'command']
                )
            }

            # Extract command-like patterns from CLAUDE.md
            command_patterns = [
                r"```(?:bash|shell|sh)\s*(.*?)```",
                r"`([^`]+)`",
                r"npm\s+[^\s\n]+",
                r"python\s+[^\s\n]+",
                r"node\s+[^\s\n]+",
            ]

            for pattern in command_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    clean_match = match.strip()
                    if clean_match and len(clean_match) < 200:  # Reasonable command length
                        analysis["instructions"].append(clean_match)

            return analysis

        except Exception as e:
            return {"error": f"Failed to parse CLAUDE.md: {str(e)}"}

    def _generate_setup_hints(self, analysis: dict[str, Any]) -> list[str]:
        """Generate setup hints based on project analysis."""
        hints = []
        project_type = analysis.get("project_type", "unknown")
        project_files = analysis.get("project_files", {})

        # Project-type specific hints
        if project_type == "node_project":
            hints.append("npm install")
            if "package.json" in project_files:
                config = analysis.get("config_files", {}).get("package.json", {})
                main_file = config.get("main", "index.js")
                hints.append(f"node {main_file}")

                # Add script hints
                scripts = config.get("scripts", [])
                hints.extend(scripts)

        elif project_type == "python_project":
            if "requirements.txt" in project_files:
                hints.append("pip install -r requirements.txt")
            if "pyproject.toml" in project_files:
                hints.append("pip install -e .")

            # Look for main entry points
            if "main.py" in project_files:
                hints.append("python main.py")
            elif "__main__.py" in project_files:
                hints.append("python -m .")
            elif "server.py" in project_files:
                hints.append("python server.py")

        elif project_type == "go_project":
            hints.append("go mod tidy")
            hints.append("go run .")

        elif project_type == "make_project":
            hints.append("make")
            hints.append("make install")
            hints.append("make run")

        # Add documentation-based hints
        readme_commands = analysis.get("documentation", {}).get("readme", {}).get("setup_commands", [])
        hints.extend(readme_commands[:5])  # Limit to first 5

        claude_instructions = analysis.get("documentation", {}).get("claude", {}).get("instructions", [])
        hints.extend(claude_instructions[:3])  # Limit to first 3

        return list(dict.fromkeys(hints))  # Remove duplicates while preserving order
