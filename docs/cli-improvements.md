# CLI Improvements

## Terminal-Friendly Features

### 1. **Proper Signal Handling** (`magg/utils/server_runner.py`)
- Graceful shutdown with Ctrl+C
- Clear shutdown messages
- Prevents multiple signal handlers from firing
- Proper cleanup of async tasks

### 2. **Colored Terminal Output** (`magg/utils/terminal.py`)
- Success messages in green with ✓
- Error messages in red with ✗
- Warnings in yellow with ⚠
- Info messages in cyan with ℹ
- Automatic color detection (disables for non-TTY)

### 3. **Better User Experience**
- Clear startup banner for HTTP mode
- Confirmation prompts for destructive actions (remove-server)
- `--force` flag to skip confirmations
- Better error messages with context
- Status indicators for enabled/disabled servers

### 4. **Improved Command Help**
- Version flag (`--version` or `-v`)
- Better command descriptions
- Epilog with usage hints
- Detailed help for each subcommand

### 5. **Exit Codes**
- Standard exit code 130 for Ctrl+C (SIGINT)
- Exit code 1 for errors
- Exit code 0 for success

## Usage Examples

```bash
# Start server with clear messages
magg serve --http

# Output:
╔═══════════════════════════════════════╗
║          MAGG - MCP Aggregator        ║
║     Managing your MCP tool ecosystem  ║
╚═══════════════════════════════════════╝

Starting MAGG HTTP server on localhost:8000
Server URL: http://localhost:8000/
Press Ctrl+C to stop gracefully
--------------------------------------------------

# Graceful shutdown
^C

Received SIGINT, shutting down gracefully...
Please wait for cleanup to complete.

MAGG HTTP server stopped.
```

```bash
# Remove with confirmation
magg remove-server myserver

# Output:
ℹ Server to remove: myserver
  URL: https://example.com
  Prefix: myserver
⚠ Are you sure you want to remove this server? [y/N]: n
ℹ Removal cancelled

# Or skip confirmation
magg remove-server myserver --force
✓ Removed server 'myserver'
```

```bash
# Colored server list
magg list-servers

# Output:
Configured Servers

  calculator (calc) - enabled    # Green
    URL: https://github.com/example/calc
    Command: npx calculator
    
  weather (weather) - disabled   # Yellow  
    URL: https://github.com/example/weather
    Notes: Requires API key       # Cyan
```

## Implementation Details

- Server runner uses asyncio events for clean shutdown
- Signal handlers are properly saved and restored
- Colors are ANSI escape codes with automatic TTY detection
- Confirmation prompts handle Ctrl+C gracefully
- All output goes to stderr to keep stdout clean for piping