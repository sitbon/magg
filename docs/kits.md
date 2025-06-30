# Magg Kits

Kits are a way to bundle related MCP servers together for easy installation and management. Think of them as "packages" or "toolkits" that group servers with similar functionality.

## Overview

A kit is a JSON file that contains:
- Metadata about the kit (name, description, author, version, etc.)
- One or more server configurations
- Links to documentation and resources

When you load a kit into Magg, all its servers are added to your configuration. When you unload a kit, servers that were only loaded from that kit are removed (servers shared by multiple kits are preserved).

## Kit Discovery

Magg looks for kits in these locations:
1. `$MAGG_KITD_PATH` (defaults to `~/.magg/kit.d`)
2. `.magg/kit.d` in the same directory as your `config.json`

Kit files must have a `.json` extension and follow the kit schema.

## Kit File Format

```json
{
  "name": "calculator",
  "description": "Basic calculator functionality for MCP",
  "author": "Magg Team",
  "version": "1.0.0",
  "keywords": ["math", "calculator", "arithmetic"],
  "links": {
    "homepage": "https://github.com/example/calculator-kit",
    "docs": "https://github.com/example/calculator-kit/wiki"
  },
  "servers": {
    "calc": {
      "source": "https://github.com/example/mcp-calc-server",
      "command": "python",
      "args": ["-m", "mcp_calc_server"],
      "notes": "Basic calculator server",
    }
  }
}
```

## Kit Management Tools

Magg provides these tools for managing kits:

### List Available Kits
```bash
# Using mbro
mbro call magg_list_kits

# Shows all kits with their status (loaded/available)
```

### Load a Kit
```bash
# Load a kit and all its servers
mbro call magg_load_kit name="calculator"

# This will:
# 1. Load the kit from calculator.json
# 2. Add all servers from the kit
# 3. Mount any enabled servers
# 4. Update config.json
```

### Unload a Kit
```bash
# Unload a kit
mbro call magg_unload_kit name="calculator"

# This will:
# 1. Remove servers that only belong to this kit
# 2. Update servers that belong to multiple kits
# 3. Unmount removed servers
# 4. Update config.json
```

### Get Kit Information
```bash
# Get detailed info about a kit
mbro call magg_kit_info name="web-tools"

# Shows:
# - Kit metadata
# - All servers in the kit
# - Whether the kit is loaded
```

## Server Tracking

Each server in `config.json` now has a `kits` field that tracks which kits it was loaded from:

```json
{
  "servers": {
    "calc": {
      "source": "...",
      "command": "python",
      "kits": ["calculator", "math-tools"]
    }
  }
}
```

This allows Magg to:
- Know which servers came from which kits
- Only remove servers when their last kit is unloaded
- Handle servers that appear in multiple kits

## Creating Your Own Kits

To create a kit:

1. Create a JSON file in `~/.magg/kit.d/` (e.g., `my-tools.json`)
2. Add kit metadata and server configurations
3. Use `magg_load_kit` to load it

Example custom kit:
```json
{
  "name": "my-tools",
  "description": "My personal MCP server collection",
  "author": "Your Name",
  "version": "1.0.0",
  "servers": {
    "tool1": {
      "source": "https://github.com/you/tool1",
      "command": "node",
      "args": ["index.js"],
      "enabled": true
    },
    "tool2": {
      "source": "https://github.com/you/tool2",
      "uri": "http://localhost:8080/mcp",
      "enabled": false
    }
  }
}
```

## Best Practices

1. **Kit Naming**: Use descriptive names that indicate the kit's purpose
2. **Versioning**: Include version numbers for tracking updates
3. **Documentation**: Provide links to docs and setup instructions
4. **Server Names**: Use consistent, meaningful server names
5. **Keywords**: Add relevant keywords for discoverability

## Example Kits

### Web Tools Kit
Groups web automation and scraping servers:
- Playwright server for browser automation
- Puppeteer server as an alternative
- Web scraping utilities

### Development Kit
Groups development-related servers:
- Git operations server
- GitHub API server
- Code analysis tools

### Data Kit
Groups data processing servers:
- SQLite database server
- CSV processing server
- Data transformation tools
