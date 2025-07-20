# mbro - MCP Browser and Management Tool

`mbro` (MCP Browser) is a command-line tool for browsing, managing, and interacting with MCP (Model Context Protocol) servers. It provides an interactive command shell for exploring MCP capabilities and executing tools.

## Overview

`mbro` allows you to:
- Browse and discover MCP servers
- List available tools, resources, and prompts
- Execute MCP tools, resources, and prompts with proper argument formatting
- View server metadata and capabilities

## Installation

`mbro` is included as part of the Magg package:

### Recommended: Install with uv tool
```bash
uv tool install magg
```

### Alternative Installation Methods

**With Poetry:**
```bash
poetry add magg
```

**With pip:**
```bash
pip install magg
```

**Direct run without installation (requires uvx):**
```bash
# Run mbro directly
uvx --from magg mbro
```

## Quick Start

### Basic Usage

Start mbro in interactive mode:
```bash
mbro
```

Then connect to an MCP server using the `connect` command (requires both a name and connection string):
```bash
mbro> connect memory npx -y @modelcontextprotocol/server-memory
mbro> connect magg http://localhost:8080
mbro> connect myserver python -m mypackage.mcp_server
```

Or execute commands directly from the command line:
```bash
# Connect and list tools in one command
mbro connect calc npx -y @modelcontextprotocol/server-calculator \; tools

# Multiple commands separated by semicolons
mbro connect magg http://localhost:8080 \; call magg_status

# Read commands from stdin
echo "connect calc npx calculator; tools" | mbro -

# Execute a script file
mbro -x setup.mbro
```

### Authentication

When connecting to HTTP servers that require bearer token authentication, mbro automatically checks for JWT tokens in these environment variables (in order):
1. `MAGG_JWT`
2. `MBRO_JWT`
3. `MCP_JWT`

```bash
# Set authentication token
export MAGG_JWT=$(magg auth token -q)

# Connect to authenticated server
mbro
mbro> connect magg http://localhost:8080
```

### Command Examples

Once connected to a server, you can use these commands:

```
# List available tools
mbro:memory> tools

# Get detailed information about a tool
mbro:memory> info tool create_memory

# Call a tool with shell-style arguments (preferred)
mbro:memory> call create_memory content="Remember this important note"

# Call a tool with JSON arguments (when needed for complex structures)
mbro:memory> call create_memory {"content": "Remember this", "tags": ["important", "todo"]}

# List resources
mbro:memory> resources

# Read a resource
mbro:memory> resource memory://notes/123

# List prompts
mbro:memory> prompts

# Use a prompt with shell-style arguments
mbro:memory> prompt summarize topic=recent_memories max_length=500
```

## Commands Reference

### Connection Management

| Command | Description | Example |
|---------|-------------|---------|
| `connections` | List all connections | `connections` |
| `connect <name> <connection>` | Connect to a server | `connect calc npx -y @modelcontextprotocol/server-calculator` |
| `switch <name>` | Switch to another connection | `switch calc` |
| `disconnect` | Disconnect from current server | `disconnect` |

### Tool Operations

| Command | Description | Example |
|---------|-------------|---------|
| `tools` | List all available tools | `tools` |
| `call <tool> <args>` | Execute a tool | `call add a=5 b=3` |

### Resource Operations

| Command | Description | Example |
|---------|-------------|---------|
| `resources` | List all resources | `resources` |
| `resource <uri>` | Read resource content | `resource file:///data.txt` |

### Prompt Operations

| Command | Description | Example |
|---------|-------------|---------|
| `prompts` | List all prompts | `prompts` |
| `prompt <name> [args]` | Execute a prompt | `prompt code_review file=main.py` |

### Search and Information

| Command | Description | Example |
|---------|-------------|---------|
| `search <query>` | Search tools, resources, and prompts | `search add` |
| `info <type> <name>` | Get detailed info | `info tool add` |
| `status` | Show connection status | `status` |

### Utility Commands

| Command | Description | Example |
|---------|-------------|---------|
| `exit` / `quit` | Exit mbro | `exit` |

## Advanced Features

### Scripts

mbro supports executing scripts from `.mbro` files. Scripts are plain text files containing mbro commands, one per line.

#### Creating Scripts

Create a file with `.mbro` extension:
```bash
# setup.mbro
# Connect to calculator and memory servers
connect calc npx -y @modelcontextprotocol/server-calculator
connect memory npx -y @modelcontextprotocol/server-memory

# Test calculator
switch calc
call add a=5 b=3

# Save result to memory
switch memory
call create_memory content="5 + 3 = 8"
```

#### Running Scripts

```bash
# Execute a script
mbro -x setup.mbro

# Execute multiple scripts
mbro -x init.mbro -x test.mbro

# Combine scripts with interactive mode
mbro -x setup.mbro  # Runs script then drops to interactive mode

# Run script and exit
mbro -x setup.mbro -n
```

#### Script Features

- **Comments**: Lines starting with `#` are ignored
- **Empty lines**: Ignored for readability
- **Line continuation**: Use backslash `\` at end of line
- **All commands supported**: Any interactive command works in scripts
- **Error handling**: Scripts continue on errors unless fatal

#### Script Discovery

mbro can discover scripts in configured paths:
```bash
# List available scripts
mbro scripts

# Scripts are searched in:
# - Current directory: ./.mbro/
# - Home directory: ~/.mbro/
# - MAGG_PATH directories
```

#### Example Scripts

**Development setup** (`dev-setup.mbro`):
```bash
# Connect to development servers
connect db npx -y @modelcontextprotocol/server-sqlite -- dev.db
connect fs npx -y @modelcontextprotocol/server-filesystem -- --readonly .
connect git npx -y @modelcontextprotocol/server-git

# Check status
status
tools
```

**Testing workflow** (`test-flow.mbro`):
```bash
# Connect to test server
connect test python -m myproject.test_server

# Run test sequence
call setup_test_data
call run_test suite=integration
call get_test_results format=json

# Cleanup
call cleanup_test_data
disconnect
```

### Modern CLI Features

mbro includes modern command-line features for better usability:

#### 📝 Shell-Style Argument Parsing
Supports key=value syntax with automatic type conversion:
```bash
# Shell-style key=value format (preferred)
mbro> call weather location=London units=celsius

# Quotes only when needed (spaces or special characters)
mbro> call weather location="New York" units=celsius

# Mixed types with automatic conversion
mbro> call search query=python limit=10 include_examples=true

# JSON format for complex structures
mbro> call create_task {"details": {"repo": "myproject", "pr": 123}}
```

#### 📄 Python REPL-Style Multiline Input
Natural multiline command editing:
```bash
# Press Enter to continue on next line
mbro> call complex_tool {
...   "data": {
...     "key": "value"
...   }
... }

# Use backslash for explicit line continuation
mbro> call tool arg1="value1" \
...          arg2="value2"
```

#### 🔍 Rich Tab Completion
Intelligent parameter completion with documentation:
```bash
# Press Tab after tool name to see parameters
mbro> call magg_server_enable <TAB>
┌─────────────────────────────────────────────────────┐
│ server=    │ string  │ required │ Name of server... │
│ force=     │ boolean │ optional │ Force enable...   │
└─────────────────────────────────────────────────────┘
```

#### 🔍 Tab Completion
Tab completion provides rich parameter information:
- **Parameter names with types**: `server=` | `string` | `required` | `Name of server to enable`
- **Type-aware value suggestions**: Enum values, boolean `true/false`, examples
- **Browse-then-apply behavior**: Browse options with Tab, press Enter to select
- **ESC to cancel**: Exit completion without selecting
- **Smart parsing**: Detects existing parameters to avoid duplicates

#### 💡 Intelligent Error Suggestions
When errors occur, get helpful suggestions:
```bash
mbro> call wether {"city": "London"}
Error: Tool 'wether' not found.
Did you mean: weather, whether_tool?
```

#### ⚡ Search
- Multi-word search support: `search file manager`
- Searches across names, descriptions, and URIs
- More flexible matching algorithms

### Keyboard Shortcuts

| Shortcut | Action | Context |
|----------|--------|---------|
| `Tab` | Smart completion with parameter hints | While typing |
| `Escape` | Cancel current completion | During completion |
| `Enter` | Submit command or continue multiline | Command prompt |
| `↑/↓` | Navigate command history | Any prompt |
| `Ctrl+C` | Cancel current command | Any time |
| `Ctrl+D` | Exit mbro | Empty prompt |
| `Ctrl+L` | Clear screen | Any time |

### Tool Argument Formatting

mbro supports multiple ways to provide tool arguments:

#### JSON Format (Traditional)
```bash
# In interactive mode, use JSON directly (no surrounding quotes)
call search {"query": "python tutorials", "limit": 10}

# Complex nested structures
call create_task {
  "title": "Review PR",
  "details": {
    "repo": "myproject",
    "pr_number": 123
  },
  "tags": ["urgent", "review"]
}

# From command line, quotes may be needed for shell parsing
mbro --call-tool search '{"query": "python tutorials"}'
```

#### Shell-Style Key=Value Format (New!)
```bash
# Simple key=value pairs (no quotes needed for single words)
call weather location=London units=celsius

# Quotes only when values contain spaces
call search query="python tutorials" limit=10 include_examples=true

# Boolean and numeric values
call configure debug=true port=8080 timeout=30.5

# Nested structures need JSON
call create_task title="Review PR" details='{"repo": "myproject", "pr_number": 123}'
```

#### Multiline Support
```bash
# Press Enter to continue on next line
call complex_tool {
  "data": {
    "key": "value"
  }
}

# Use backslash for explicit line continuation
call tool arg1="value1" \
         arg2="value2"
```

### Server Connection Strings

mbro supports various server connection formats with the `connect` command:

```bash
# In interactive mode (no quotes needed)
mbro> connect filesystem npx -y @modelcontextprotocol/server-filesystem
mbro> connect myserver python -m mypackage.mcp_server
mbro> connect api http://localhost:3000
mbro> connect remote https://api.example.com/mcp
mbro> connect local ./my-mcp-server --port 8080
mbro> connect server uvx myserver

# From command line (escape semicolons for multiple commands)
mbro connect filesystem npx -y @modelcontextprotocol/server-filesystem
mbro connect myserver python -m mypackage.mcp_server \; tools
mbro connect api http://localhost:3000 \; status
```

### Running Magg in stdio Mode

A unique feature of mbro is the ability to run Magg directly in stdio mode for quick inspection:

```bash
# Connect to a local Magg instance via stdio
mbro> connect magg magg serve
Connected to 'magg' (Tools: 15, Resources: 0, Prompts: 0)

# Now you can inspect your Magg setup from the MCP side
mbro:magg> call magg_list_servers
{
  "servers": [
    {"name": "calculator", "enabled": true, "prefix": "calc"},
    {"name": "filesystem", "enabled": true, "prefix": "fs"},
    {"name": "memory", "enabled": false, "prefix": "mem"}
  ]
}

mbro:magg> call magg_status
{
  "mounted_servers": 2,
  "total_servers": 3,
  "total_tools": 15,
  "enabled_servers": ["calculator", "filesystem"]
}
```

This is particularly useful for:
- **Quick debugging**: Inspect your Magg configuration without starting an HTTP server
- **Testing changes**: See how Magg looks from an MCP client's perspective
- **Script development**: Test Magg tools before integrating with other clients
- **Configuration validation**: Verify servers are properly configured and mounted

### Async Python REPL

For advanced users and debugging, mbro includes an async Python REPL mode that provides direct access to the underlying MCP client connection:

```bash
# Start mbro with Python REPL mode
mbro --repl
# Then connect to a server
>>> await self.handle_command('connect myserver npx some-server')
```

In the Python REPL, you have access to:
- `current_connection`: The active MCP connection object
- `self`: The MCPBrowserCLI instance for executing commands
- All standard Python functionality with async/await support

Example REPL session:
```python
>>> # Direct access to the current connection
>>> tools = await current_connection.list_tools()
>>> print(tools[0].name)
'add'

>>> # Execute mbro commands via self
>>> await self.handle_command('tools')
Available tools:
  - add: Add two numbers
  ...

>>> # Call a tool directly
>>> result = await current_connection.call_tool('add', {'a': 5, 'b': 3})
>>> print(result)
[TextContent(type='text', text='8')]
```

This is particularly useful for:
- Testing and debugging MCP servers
- Exploring the raw MCP protocol responses
- Building custom scripts and automation

## Integration with Magg

When used with Magg, mbro can browse the aggregated server:

```bash
# Start Magg server
magg serve --http --port 8000

# In another terminal, connect mbro to Magg
mbro --connect magg http://localhost:8000
```

This allows you to use mbro to explore all tools from all servers managed by Magg through a single interface.

## Examples

### Example 1: Calculator Operations

```bash
$ mbro
mbro> connect calc npx -y @modelcontextprotocol/server-calculator
Connected to 'calc' (Tools: 4, Resources: 0, Prompts: 0)

mbro:calc> tools
Available tools:
  - add: Add two numbers
  - subtract: Subtract two numbers
  - multiply: Multiply two numbers
  - divide: Divide two numbers

mbro:calc> call add a=42 b=58
100

mbro:calc> call divide a=100 b=4
25
```

### Example 2: File System Operations

```bash
$ mbro
mbro> connect fs npx -y @modelcontextprotocol/server-filesystem -- --readonly /
Connected to 'fs' (Tools: 3, Resources: 100+, Prompts: 0)

mbro:fs> resources
Available resources:
  - file:///etc/hosts
  - file:///etc/passwd
  - ...

mbro:fs> resource file:///etc/hosts
127.0.0.1   localhost
::1         localhost
...
```

### Example 3: Working with Magg

```bash
# Terminal 1: Start Magg with multiple servers configured
$ magg serve --http

# Terminal 2: Connect mbro to Magg
$ mbro
mbro> connect magg http://localhost:8000
Connected to 'magg' (Tools: 11, Resources: 5, Prompts: 2)

mbro:magg> tools
Tool Groups:
- calc (6 tools): calc_add, calc_sub, calc_mul, calc_div, calc_mod, calc_sqrt
- fs (3 tools): fs_read, fs_list, fs_search
- weather (2 tools): weather_current, weather_forecast
Total tools: 11

mbro:magg> call calc_add a=10 b=20
30

mbro:magg> call weather_current location=London
{
  "temperature": 15,
  "conditions": "Partly cloudy",
  "humidity": 65
}
```

### Example 3.1: Using Magg in Hybrid Mode

```bash
# mbro can host Magg in hybrid mode and connect via stdio
$ mbro
mbro> connect magg "magg serve --hybrid --port 8080"
Connected to 'magg' (Tools: 11, Resources: 5, Prompts: 2)

# Now Magg is:
# - Connected to mbro via stdio
# - Also accessible via HTTP at http://localhost:8080

# In another terminal, different mbro instances can connect via HTTP
$ mbro
mbro> connect magg-remote http://localhost:8080
Connected to 'magg-remote' (Tools: 11, Resources: 5, Prompts: 2)

# Both connections can use Magg simultaneously
mbro:magg> call calc_add a=5 b=3
8

mbro:magg-remote> call calc_multiply a=5 b=3
15
```

### Example 4: Script Automation

```bash
# Create a script file for common tasks
$ cat > weather_check.mbro << 'EOF'
# Weather check script
connect weather npx -y @modelcontextprotocol/server-weather
call get_forecast location="San Francisco" days=3
disconnect
quit
EOF

# Execute the script
$ mbro -x weather_check.mbro

# Or execute non-interactively
$ mbro -X weather_check.mbro

# Chain multiple scripts
$ mbro -x setup.mbro -x weather_check.mbro -x cleanup.mbro
```

## Output Modes

mbro supports different output modes for various use cases:

### Default Mode (Rich Formatting)
Uses Rich library for beautiful, colored output with tables and formatting:
```bash
mbro
```

### Plain Text Mode
Disables Rich formatting for simpler output:
```bash
mbro --no-rich
```

### JSON-Only Mode
Machine-readable JSON output for scripting and automation:
```bash
# Standard JSON with indentation
mbro --json

# Compact JSON (no indentation)
mbro --json --indent 0

# Custom indentation
mbro --json --indent 4
```

In JSON mode:
- All output is valid JSON
- Errors include exception details
- No interactive prompts are shown
- Perfect for piping to other tools

Example using JSON mode in a script:
```bash
# Get tools list as JSON
mbro --json connect calc npx -y @modelcontextprotocol/server-calculator \; tools | jq

# Call a tool and parse result
result=$(mbro --json connect calc npx calculator \; call add a=5 b=3)
echo $result | jq

# One-liner with proper escaping
mbro --json connect calc npx -y @modelcontextprotocol/server-calculator \; call add a=5 b=3 | jq

# Quiet mode - suppress informational messages
mbro -q connect calc npx -y @modelcontextprotocol/server-calculator \; call add a=5 b=3
```

## Tips and Tricks

1. **Tab Completion**: After connecting, tab completion shows available tools and their parameters with rich documentation
2. **Minimal Quoting**: Only use quotes when values contain spaces or special characters. Single words don't need quotes.
3. **Scripts**: Create reusable `.mbro` scripts for common workflows and execute with `-x script.mbro`
4. **Multiple Connections**: Connect to multiple servers and switch between them using the `switch` command
5. **Shell Escaping**: When using semicolons on command line, escape them with backslash: `\;`
6. **Empty Arguments**: When calling tools with no arguments, simply use the tool name: `call my_tool`

### Command Line Options 
   - `commands` - Commands to execute (positional arguments)
   - `--version` / `-V` - Show version information
   - `--json` / `-j` - Output only JSON (machine-readable)
   - `--no-rich` - Disable Rich formatting
   - `--indent N` - Set JSON indent level (0 for compact, default: 2)
   - `--verbose` / `-v` - Enable verbose output (can be used multiple times)
   - `--quiet` / `-q` - Suppress informational messages
   - `--env-pass` / `-e` - Pass environment to stdio MCP servers
   - `--env-set KEY VALUE` / `-E KEY VALUE` - Set environment variable for stdio MCP servers (can be used multiple times)
   - `--repl` - Drop into REPL mode on startup
   - `-n` / `--no-interactive` - Don't drop into interactive mode after commands
   - `-x SCRIPT` / `--execute-script SCRIPT` - Execute .mbro script file (can be used multiple times)
   - `-X SCRIPT` / `--execute-script-n SCRIPT` - Execute script in non-interactive mode (equivalent to -n -x)
   - `--help` - Show help message

Special command line usage:
   - Use `-` as command to read from stdin
   - Use `\;` to separate multiple commands (escape semicolon)
   - Scripts provide reusable command sequences
   - Minimal quoting: only quote values with spaces

## Troubleshooting

### Common Issues

1. **Connection Failed**: Ensure the MCP server is installed and the command is correct
2. **Tool Not Found**: Use `tools` to list available tools and check the exact name
3. **Invalid Arguments**: Use shell-style key=value arguments. Only use JSON for complex nested structures.
4. **Permission Denied**: Some servers require specific permissions or environment variables

## See Also

- [Magg Documentation](index.md) - MCP Aggregator
- [MCP Specification](https://modelcontextprotocol.io) - Model Context Protocol details
- [Examples](examples.md) - More usage examples with Magg
