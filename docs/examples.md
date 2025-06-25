# Magg Example Sessions

This document provides detailed examples of using Magg in various scenarios. Each example shows the complete flow from discovering servers to using their tools.

Tool call and output formatting is in the style of `mbro` - this package's MCP browsing and management tool.

## Example 1: Adding Browser Automation

This example demonstrates how to discover, add, and use a Playwright MCP server for browser automation tasks.

### Step 1: Search for Browser Automation Tools

**User:** "I need to automate web browser tasks"

**Claude:** Let me search for browser automation MCP servers.

Call tool `magg_search_servers`:
```text
mbro:magg> call magg_search_servers {"query": "browser automation playwright mcp", "limit": 3}
```
Response:
```json
{
  "errors": null,
  "output": {
    "query": "browser automation playwright mcp",
    "results": [
      {
        "source": "glama",
        "name": "dex-metrics-mcp",
        "description": "An MCP server that tracks trading volume metrics segmented by DEX, blockchain, aggregator, frontend, and Telegram bot.",
        "url": "https://glama.ai/mcp/servers/g6ba16nv5a",
        "install_command": "git clone https://github.com/kukapay/dex-metrics-mcp"
      },
      ...
    ],
    "total": 9
  }
}
```

### Step 2: Determine the config \& add the Playwright server

Let's say we eventually find Microsoft's Playwright MCP server, either through Magg's search capability or Claude's web search.

The command to run the server locally without cloning is `npx @playwright/mcp@latest`, but Claude/Magg don't
know that yet. Let's get a prompt from that URL to have Claude determine the parameters for us.

#### 2.1: Generate a prompt

Call prompt `configure_server`:
```text
mbro:magg> prompt configure_server {"url": "https://github.com/microsoft/playwright-mcp"}
```

Response (summary):
```text
role: system
content: You are an expert at configuring MCP servers. Analyze the provided URL and generate optimal server configuration.

role user
content: Configure an MCP server for: https://github.com/microsoft/playwright-mcp
  
Server name: auto-generate

Please determine:
1. name: A string, potentially user provided (can be human-readable)
2. prefix: A valid Python identifier (no underscores)
3. command: The full command to run (e.g., \"python server.py\", \"npx @playwright/mcp@latest\", or null for HTTP)
4. uri: For HTTP servers (if applicable)
5. working_dir: If needed
6. env: Environment variables as an object (if needed)
7. notes: Helpful setup instructions
8. transport: Any transport-specific configuration (optional dict)

Consider the URL type:
- GitHub repos may need cloning and setup
- NPM packages use npx
- Python packages may use uvx or python -m
- HTTP/HTTPS URLs may be direct MCP servers
```

This prompt can be manually fed back into the LLM to get a config response.

#### 2.2: Use LLM sampling instead of prompt

The `smart_configure` tool can be used to automatically generate the configuration based on the URL.

**User:** "Configure an MCP from the following URL using the `magg_smart_configure` tool: https://github.com/microsoft/playwright-mcp"

**LLM:** "... (json configuration) ..."

**User:** "Great, now add the server using the `magg_add_server` tool with the generated configuration, after doing any necessary pre-work like cloning a repository or installing dependencies."


### Step 3: Add the Server

By default, when a server is added it is immediately mounted. Set the enabled parameter to `false` if you want to add it without enabling it right away.

Call tool magg_add_server:

(Multiline mbro commands not yet supported)
```text
mbro:magg> call magg_add_server {"source": "https://github.com/microsoft/playwright-mcp", "name": "playwright", "command": "npx @playwright/mcp@latest", "notes": "Browser automation MCP server using Playwright."}
```
Response:
```json
{
  "errors": null,
  "output": {
    "action": "server_added",
    "server": {
      "name": "playwright",
      "source": "https://github.com/microsoft/playwright-mcp",
      "prefix": "playwright",
      "command": "npx @playwright/mcp@latest",
      "uri": null,
      "working_dir": null,
      "notes": "Browser automation MCP server using Playwright.",
      "enabled": true,
      "mounted": true
    }
  }
}
```

### Step 4: Use the Playwright Server

You can now use the MCP server from your LLM interface or directly from application code. Here's an example with `mbro`:

```text
mbro:magg> tools
```

This will show all available tools from all mounted servers, including the newly added Playwright server tools with the `playwright_` prefix.

You can now use any of the Playwright tools:

```text
mbro:magg> call playwright_browser_navigate {"url": "https://example.com"}
mbro:magg> call playwright_browser_take_screenshot
```
