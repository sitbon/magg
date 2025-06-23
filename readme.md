# 🧲 MAGG - The MCP (Model Context Protocol) Aggregator

[![Tests](https://img.shields.io/github/actions/workflow/status/sitbon/magg/test.yml?style=flat-square&label=tests)](https://github.com/sitbon/magg/actions/workflows/test.yml)
[![Python Version](https://img.shields.io/pypi/pyversions/magg?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/magg/)
[![PyPI Version](https://img.shields.io/pypi/v/magg?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/magg/)
[![GitHub Release](https://img.shields.io/github/v/release/sitbon/magg?style=flat-square&logo=github)](https://github.com/sitbon/magg/releases)
[![Downloads](https://img.shields.io/pypi/dm/magg?style=flat-square)](https://pypistats.org/packages/magg)

An MCP server that manages and aggregates other MCP servers, enabling LLMs to dynamically extend their own capabilities.

## What is MAGG?

MAGG (MCP Aggregator) is a meta-MCP server that acts as a central hub for managing multiple MCP servers. It provides tools that allow LLMs to:

- Search for new MCP servers and discover setup instructions
- Add and configure MCP servers dynamically
- Enable/disable servers on demand
- Aggregate tools from multiple servers under unified prefixes
- Persist configurations across sessions

Think of MAGG as a "package manager for LLM tools" - it lets AI assistants install and manage their own capabilities at runtime.

## Key Features

- **Self-Service Tool Management**: LLMs can search for and add new MCP servers without human intervention
- **Automatic Tool Proxying**: Tools from added servers are automatically exposed with configurable prefixes
- **Smart Configuration**: Uses MCP sampling to intelligently configure servers from just a URL
- **Persistent Configuration**: Maintains server configurations in `.magg/config.json`
- **Multiple Transport Support**: Works with stdio, HTTP, and other MCP transports

## Installation

### Prerequisites

- Python 3.13 or higher
- `uv`, `poetry`, or `pip`

### Run Directly from GitHub

The easiest way to run MAGG is directly from GitHub using `uvx`:

```bash
# Run with stdio transport (for Claude Desktop, Cline, etc.)
uvx --from git+https://github.com/sitbon/magg.git magg

# Run with HTTP transport (for system-wide access)
uvx --from git+https://github.com/sitbon/magg.git magg serve --http
```

### Local Development

For development, clone the repository and install in editable mode:

```bash
# Clone the repository
git clone https://github.com/sitbon/magg.git
cd magg

# Install in development mode with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .

# Run the CLI
magg --help
```

## Usage

### Running MAGG

MAGG can run in two modes:

1. **Stdio Mode** (default) - For integration with Claude Desktop, Cline, Cursor, etc.:
   ```bash
   magg serve
   ```

2. **HTTP Mode** - For system-wide access or web integrations:
   ```bash
   magg serve --http --port 8000
   ```

### Available Tools

Once MAGG is running, it exposes the following tools to LLMs:

- `magg_list_servers` - List all configured MCP servers
- `magg_add_server` - Add a new MCP server
- `magg_remove_server` - Remove a server
- `magg_enable_server` / `magg_disable_server` - Toggle server availability
- `magg_search_servers` - Search for MCP servers online
- `magg_list_tools` - List all available tools from all servers
- `magg_smart_configure` - Intelligently configure a server from a URL
- `magg_analyze_servers` - Analyze configured servers and suggest improvements

### Configuration

MAGG stores its configuration in `.magg/config.json` in your current working directory. This allows for project-specific tool configurations.

Example configuration:
```json
{
  "servers": {
    "calculator": {
      "name": "calculator",
      "source": "https://github.com/executeautomation/calculator-mcp",
      "command": "npx @executeautomation/calculator-mcp",
      "prefix": "calc",
      "enabled": true
    }
  }
}
```

### Adding Servers

Servers can be added in several ways:

1. **Using the LLM** (recommended):
   ```
   "Add the Playwright MCP server"
   "Search for and add a calculator tool"
   ```

2. **Manual configuration** via `magg_add_server`:
   ```
   name: playwright
   url: https://github.com/microsoft/playwright-mcp
   command: npx @playwright/mcp@latest
   prefix: pw
   ```

3. **Direct config editing**: Edit `.magg/config.json` directly

## Documentation

For more documentation, see [docs/](docs/index.md).
