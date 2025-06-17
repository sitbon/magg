# MAGG Example Sessions

This document provides detailed examples of using MAGG in various scenarios. Each example shows the complete flow from discovering servers to using their tools.

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
mbro:magg> call magg_add_server {"url": "https://github.com/microsoft/playwright-mcp", "name": "playwright", "command": "npx @playwright/mcp@latest", "notes": "Browser automation MCP server using Playwright."}
```
Response:
```json
{
  "errors": null,
  "output": {
    "action": "server_added",
    "server": {
      "name": "playwright",
      "url": "https://github.com/microsoft/playwright-mcp",
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

***Note: The `magg_list_tools` command lists all tools available in the MCP servers - the output from `mbro`'s tools command may not be updated yet.***

```text
mbro:magg> call magg_list_tools
```
Result:
```json
{
  "errors": null,
  "output": {
    "tool_groups": [
      {
        "prefix": "magg",
        "tools": [
          "magg_add_server",
          "magg_analyze_servers",
          "magg_disable_server",
          "magg_enable_server",
          "magg_list_servers",
          "magg_list_tools",
          "magg_remove_server",
          "magg_search_servers",
          "magg_smart_configure"
        ],
        "count": 9
      },
      {
        "prefix": "playwright",
        "tools": [
          "playwright_browser_click",
          "playwright_browser_close",
          "playwright_browser_console_messages",
          "playwright_browser_drag",
          "playwright_browser_file_upload",
          "playwright_browser_generate_playwright_test",
          "playwright_browser_handle_dialog",
          "playwright_browser_hover",
          "playwright_browser_install",
          "playwright_browser_navigate",
          "playwright_browser_navigate_back",
          "playwright_browser_navigate_forward",
          "playwright_browser_network_requests",
          "playwright_browser_pdf_save",
          "playwright_browser_press_key",
          "playwright_browser_resize",
          "playwright_browser_select_option",
          "playwright_browser_snapshot",
          "playwright_browser_tab_close",
          "playwright_browser_tab_list",
          "playwright_browser_tab_new",
          "playwright_browser_tab_select",
          "playwright_browser_take_screenshot",
          "playwright_browser_type",
          "playwright_browser_wait_for"
        ],
        "count": 25
      }
    ],
    "total_tools": 34
  }
}
```

For LLM usage, instruct your LLM to use the `magg_list_tools` command to discover newly added tools and use the playwright server as needed.
