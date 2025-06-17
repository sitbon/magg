# mbro - MCP Browser and Management Tool

`mbro` (MCP Browser) is a command-line tool for browsing, managing, and interacting with MCP (Model Context Protocol) servers. It provides an interactive REPL interface for exploring MCP capabilities and executing tools.

## Overview

`mbro` allows you to:
- Browse and discover MCP servers
- List available tools, resources, and prompts
- Execute MCP tools, resources, and prompts with proper argument formatting
- View server metadata and capabilities

## Installation

`mbro` is included as part of the MAGG package:

```bash
# Install via pip
pip install magg

# Or use uvx for isolated execution
uvx magg mbro
```

## Quick Start

### Basic Usage

Connect to an MCP server using the `--connect` option (requires both a name and connection string):
```bash
# Connect to an NPX-based server
mbro --connect memory "npx -y @modelcontextprotocol/server-memory"

# Connect to an HTTP MCP server
mbro --connect magg http://localhost:8080

# Connect to a Python-based server
mbro --connect myserver "python -m mypackage.mcp_server"
```

Start mbro in interactive mode (without a server):
```bash
mbro
```

### Command Examples

Once connected to a server, you can use these commands:

```
# List available tools
mbro:memory> tools

# Get detailed information about a tool
mbro:memory> tool create_memory

# Call a tool with arguments
mbro:memory> call create_memory {"content": "Remember this important note"}

# List resources
mbro:memory> resources

# Read a resource
mbro:memory> read memory://notes/123

# List prompts
mbro:memory> prompts

# Use a prompt
mbro:memory> prompt summarize {"topic": "recent_memories"}
```

## Commands Reference

### Server Management

| Command | Description | Example |
|---------|-------------|---------|
| `servers` | List configured servers | `servers` |
| `server <name>` | Show server details | `server memory` |
| `connect <server>` | Connect to a server | `connect "npx calculator"` |
| `disconnect` | Disconnect from current server | `disconnect` |

### Tool Operations

| Command | Description | Example |
|---------|-------------|---------|
| `tools` | List all available tools | `tools` |
| `tool <name>` | Show tool details | `tool add_numbers` |
| `call <tool> <args>` | Execute a tool | `call add_numbers {"a": 5, "b": 3}` |

### Resource Operations

| Command | Description | Example |
|---------|-------------|---------|
| `resources` | List all resources | `resources` |
| `resource <uri>` | Show resource details | `resource file:///data.txt` |
| `read <uri>` | Read resource content | `read memory://notes/latest` |

### Prompt Operations

| Command | Description | Example |
|---------|-------------|---------|
| `prompts` | List all prompts | `prompts` |
| `prompt <name> [args]` | Execute a prompt | `prompt code_review {"file": "main.py"}` |

### Search and Discovery

| Command | Description | Example |
|---------|-------------|---------|
| `search <query>` | Search for MCP servers | `search weather` |
| `install <server>` | Install and connect to server | `install @example/weather-mcp` |

### Utility Commands

| Command | Description | Example |
|---------|-------------|---------|
| `help` | Show help message | `help` |
| `debug` | Toggle debug mode | `debug` |
| `clear` | Clear the screen | `clear` |
| `history` | Show command history | `history` |
| `exit` / `quit` | Exit mbro | `exit` |

## Advanced Features

### Tool Argument Formatting

mbro supports multiple ways to provide tool arguments:

```bash
# JSON object notation
call search {"query": "python tutorials", "limit": 10}

# Single string argument (automatically wrapped in JSON)
call echo "Hello, World!"

# Complex nested structures
call create_task {
  "title": "Review PR",
  "details": {
    "repo": "myproject",
    "pr_number": 123
  },
  "tags": ["urgent", "review"]
}
```

### Server Connection Strings

mbro supports various server connection formats with the `--connect` option (format: `--connect NAME CONNECTION`):

```bash
# NPX packages
mbro --connect filesystem "npx -y @modelcontextprotocol/server-filesystem"

# Python modules
mbro --connect myserver "python -m mypackage.mcp_server"

# HTTP servers
mbro --connect api http://localhost:3000
mbro --connect remote https://api.example.com/mcp

# Local executables
mbro --connect local "./my-mcp-server --port 8080"

# UV/UVX packages
mbro --connect server "uvx myserver"
```

## Integration with MAGG

When used with MAGG, mbro can browse the aggregated server:

```bash
# Start MAGG server
magg serve --http --port 8000

# In another terminal, connect mbro to MAGG
mbro --connect magg http://localhost:8000
```

This allows you to use mbro to explore all tools from all servers managed by MAGG through a single interface.

## Examples

### Example 1: Calculator Operations

```bash
$ mbro --connect calc "npx -y @modelcontextprotocol/server-calculator"

mbro:calc> tools
Available tools:
  - add: Add two numbers
  - subtract: Subtract two numbers
  - multiply: Multiply two numbers
  - divide: Divide two numbers

mbro:calc> call add {"a": 42, "b": 58}
100

mbro:calc> call divide {"a": 100, "b": 4}
25
```

### Example 2: File System Operations

```bash
$ mbro --connect fs "npx -y @modelcontextprotocol/server-filesystem -- --readonly /"

mbro:fs> resources
Available resources:
  - file:///etc/hosts
  - file:///etc/passwd
  - ...

mbro:fs> read file:///etc/hosts
127.0.0.1   localhost
::1         localhost
...
```

### Example 3: Working with MAGG

```bash
# Terminal 1: Start MAGG with multiple servers configured
$ magg serve --http

# Terminal 2: Connect mbro to MAGG
$ mbro --connect magg http://localhost:8000

mbro:magg> tools
Tool Groups:
- calc (6 tools): calc_add, calc_sub, calc_mul, calc_div, calc_mod, calc_sqrt
- fs (3 tools): fs_read, fs_list, fs_search
- weather (2 tools): weather_current, weather_forecast
Total tools: 11

mbro:magg> call calc_add {"a": 10, "b": 20}
30

mbro:magg> call weather_current {"location": "London"}
{
  "temperature": 15,
  "conditions": "Partly cloudy",
  "humidity": 65
}
```

## Tips and Tricks

1. **Tab Completion**: mbro supports tab completion for commands and tool names
2. **History**: Use up/down arrows to navigate command history
3. **Piping**: mbro can read commands from stdin: `echo "tools" | mbro --connect calc "npx calculator"`
4. **Command Line Options**: 
   - `--connect NAME CONNECTION` - Connect to a server on startup
   - `--list-connections` - List all available connections
   - `--list-tools` - List available tools
   - `--list-resources` - List available resources  
   - `--list-prompts` - List available prompts
   - `--call-tool TOOL [ARGS]` - Call a tool directly
   - `--get-resource URI` - Get a resource directly
   - `--search TERM` - Search tools, resources, and prompts
   - `--info TYPE NAME` - Show info about tool/resource/prompt
   - `--help` - Show help message

## Troubleshooting

### Common Issues

1. **Connection Failed**: Ensure the MCP server is installed and the command is correct
2. **Tool Not Found**: Use `tools` to list available tools and check the exact name
3. **Invalid Arguments**: Tool arguments must be valid JSON
4. **Permission Denied**: Some servers require specific permissions or environment variables

## See Also

- [MAGG Documentation](index.md) - MCP Aggregator
- [MCP Specification](https://modelcontextprotocol.io) - Model Context Protocol details
- [Examples](examples.md) - More usage examples with MAGG
