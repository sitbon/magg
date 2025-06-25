MAGG_INSTRUCTIONS = """
Magg (MCP Aggregator) manages and aggregates other MCP servers.

Key capabilities:
- Add and manage MCP servers with intelligent configuration
- Aggregate tools from multiple servers with prefixes to avoid conflicts
- Search for new MCP servers online
- Export/import configurations
- Smart configuration assistance using LLM sampling
- Expose server metadata as resources for LLM consumption

Use {self_prefix}_add_server to register new MCP servers, then they will be automatically mounted.
Tools from mounted servers are available with their configured prefixes.
"""


MAGG_ADD_SERVER_DOC = """
Tool: magg_add_server

Description:
  Add a new MCP server.

Parameters:
  name (string) (required)
    Unique server name
  source (string) (required)
    URL of the server package/repository
  prefix (string | null) (optional)
    Tool prefix (defaults to conformed server name)
  command (string | null) (optional)
    Full command to run (e.g., 'python server.py', 'npx @playwright/mcp@latest')
    NOTE: This should include the full command, not just the executable name.
          Arguments will be split automatically.
  uri (string | null) (optional)
    URI for HTTP servers
  env_vars (object | null) (optional)
    Environment variables
  working_dir (string | null) (optional)
    Working directory (for commands)
  notes (string | null) (optional)
    Setup notes
  enable (boolean | null) (optional)
    Whether to enable the server immediately (default: True)
  transport (object | null) (optional)
    Transport-specific configuration (optional)
    Common options for all command-based servers:
    - `keep_alive` (boolean): Keep the process alive between requests (default: true)

    Python servers (command="python ..."):
    - `python_cmd` (string): Python executable path (default: sys.executable)

    Node.js servers (command="node ..."):
    - `node_cmd` (string): Node executable path (default: "node")

    NPX servers (command="npx ..."):
    - `use_package_lock` (boolean): Use package-lock.json if present (default: true)

    UVX servers (command="uvx ..."):
    - `python_version` (string): Python version to use (e.g., "3.11")
    - `with_packages` (array): Additional packages to install
    - `from_package` (string): Install tool from specific package

    HTTP/SSE servers (uri-based):
    - `headers` (object): HTTP headers to include
    - `auth` (string): Authentication method ("oauth" or bearer token)
    - `sse_read_timeout` (number): Timeout for SSE reads in seconds

    Examples:
    - Python: `{"keep_alive": false, "python_cmd": "/usr/bin/python3"}`
    - UVX: `{"python_version": "3.11", "with_packages": ["requests", "pandas"]}`
    - HTTP: `{"headers": {"Authorization": "Bearer token123"}, "sse_read_timeout": 30}`

Example configurations arguments:
[
    "calc": {
      "name": "Calculator MCP",
      "source": "https://github.com/wrtnlabs/calculator-mcp",
      "prefix": "calc",
      "command": "npx -y @wrtnlabs/calculator-mcp@latest"
    },
    "playwright": {
      "name": "Playwright MCP",
      "source": "https://github.com/microsoft/playwright-mcp",
      "prefix": "playwright",
      "notes": "Browser automation MCP server using Playwright.",
      "command": "npx @playwright/mcp@latest"
    },
    "test": {
      "name": "test",
      "source": "play",
      "command": "python play/test_server.py"
    },
    "hello": {
      "name": "hello",
      "source": "https://www.npmjs.com/package/mcp-hello-world",
      "command": "npx mcp-hello-world@latest"
    }
]
"""


PROXY_TOOL_DOC = """
Tool: proxy

Description:
  Main proxy tool for dynamic access to mounted MCP servers.

  This tool provides a unified interface for:
  - Listing available tools, resources, or prompts across servers
  - Getting detailed info about specific capabilities
  - Calling tools, reading resources, or getting prompts

  Annotations are used to provide rich type information for results,
  which can generally be expected to ultimately include JSON-encoded
  EmbeddedResource results that can be interpreted by the client.

Parameters:
  action (string) (required)
    Action to perform: list, info, or call.
  type (string) (required)
    Type of MCP capability to interact with: tool, resource, or prompt.
  args (object | null) (optional)
    Arguments for a 'call' action (call tool, read resource, or get prompt).
  path (string | null) (optional)
    Name or URI of the specific tool/resource/prompt (with FastMCP prefixing).
    Not allowed for 'list' and 'info' actions.

Example usage (MBRO commands):
  - List all tools:
    -  `call proxy {"action": "list", "type": "tool"}`

  - Get info about a specific tool:
    -  `call proxy {"action": "info", "type": "tool", "path": "calc:add"}`

  - Call a tool with arguments:
    -  `call proxy {"action": "call", "type": "tool", "path": "calc:add", "args": {"a": 5, "b": 10}}`
"""
