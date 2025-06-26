# Configuration Reload in Magg

Magg supports dynamic configuration reloading, allowing you to update server configurations without restarting the main Magg process. This feature helps maintain service availability while making configuration changes.

## Features

- **Automatic file watching**: Detects changes to `config.json` and reloads automatically
  - Uses file system notifications (inotify/FSEvents) when available for zero CPU usage
  - Falls back to polling when watchdog is not available
- **SIGHUP signal support**: Send SIGHUP to trigger reload (Unix-like systems)
- **Manual reload tool**: Use `magg_reload_config` via MCP client
- **Graceful transitions**: Only affected servers are restarted
- **Validation before apply**: Invalid configurations are rejected
- **Works in read-only mode**: External processes can modify config even when Magg can't

## How It Works

When a configuration change is detected, Magg:

1. Loads and validates the new configuration
2. Compares it with the current configuration
3. Identifies what changed (added, removed, modified, enabled/disabled servers)
4. Applies changes in a specific order to minimize disruption:
   - Removes deleted servers
   - Disables servers marked as disabled
   - Updates modified servers (unmount then remount)
   - Enables servers marked as enabled
   - Adds new servers

## Configuration Options

### Environment Variables

- `MAGG_AUTO_RELOAD`: Enable/disable automatic config reloading (default: `true`)
- `MAGG_RELOAD_POLL_INTERVAL`: File check interval in seconds when polling (default: `1.0`)
- `MAGG_RELOAD_USE_WATCHDOG`: Force watchdog on/off, or auto-detect (default: `null` for auto)
- `MAGG_READ_ONLY`: When `true`, Magg cannot modify config but can still reload external changes

### Example

```bash
# Disable auto-reload
export MAGG_AUTO_RELOAD=false

# Check for changes every 5 seconds (polling mode)
export MAGG_RELOAD_POLL_INTERVAL=5.0

# Force polling mode (disable watchdog)
export MAGG_RELOAD_USE_WATCHDOG=false

# Run in read-only mode (Magg can't modify, but can reload)
export MAGG_READ_ONLY=true
```

### File System Notifications vs Polling

By default, Magg will use file system notifications if the `watchdog` package is installed:

- **File system notifications (preferred)**:
  - Zero CPU usage when idle - perfect for spot/serverless platforms
  - Instant detection of changes
  - Uses inotify (Linux), FSEvents (macOS), or Windows APIs
  
- **Polling fallback**:
  - Used when watchdog is not available
  - Checks file modification time periodically
  - Configurable interval via `MAGG_RELOAD_POLL_INTERVAL`

To check which mode is active, look for this log message on startup:
```
INFO: Started config file watcher using file system notifications (watchdog)
# or
INFO: Started config file watcher using polling (interval: 1.0s)
```

## Usage Methods

### 1. Automatic File Watching (Default)

When Magg starts with auto-reload enabled (default), it monitors `config.json` for changes:

```bash
# Start Magg with auto-reload
magg serve

# In another terminal, edit the config
vim ~/.magg/config.json

# Changes are detected and applied automatically
```

### 2. SIGHUP Signal (Unix/Linux/macOS)

Send a SIGHUP signal to trigger immediate reload:

```bash
# Find Magg process ID
ps aux | grep magg

# Send SIGHUP
kill -HUP <pid>

# Or if you know the process name
pkill -HUP -f "magg serve"
```

### 3. MCP Tool

Use the `magg_reload_config` tool from any MCP client:

```python
# Using magg Python client
from magg.client import MaggClient

async with MaggClient() as client:
    result = await client.call_tool("magg_reload_config")
    print(result)
```

**Note**: The MCP tool will fail if:
- `MAGG_AUTO_RELOAD` is set to `false` (config reload is disabled)
- `MAGG_READ_ONLY` is set to `true` (read-only mode)

### 4. Manual Reload in Code

```python
from magg.server.server import MaggServer

server = MaggServer()
async with server:
    # Trigger manual reload
    success = await server.reload_config()
    if success:
        print("Config reloaded successfully")
```

## What Can Be Reloaded

The following changes can be applied without restarting Magg:

- ✅ Adding new servers
- ✅ Removing existing servers
- ✅ Enabling/disabling servers
- ✅ Changing server configurations:
  - Command and arguments
  - Environment variables
  - Working directory
  - Transport settings
  - Source URL

## What Cannot Be Reloaded

Some settings require a full restart:

- ❌ Magg's own settings (log level, port, auto_reload, etc.)
- ❌ Authentication configuration
- ❌ Server prefixes (changing prefix requires remove + add)

## Monitoring Reload Events

Reload events are logged at INFO level:

```
INFO: Config file changed, reloading...
INFO: Config changes: + new-server, - old-server, ~ modified-server
INFO: Applying configuration changes...
INFO: Adding new server: new-server
INFO: Removing server: old-server
INFO: Updating server: modified-server
INFO: Configuration reload complete
```

## Best Practices

1. **Test configs before applying**: Validate JSON syntax before saving
2. **Monitor logs during reload**: Watch for any errors or warnings
3. **Use atomic writes**: Write to a temp file and move it to avoid partial reads
4. **Backup before major changes**: Keep a copy of working configurations
5. **Gradual rollout**: Test changes with one server before applying broadly

## Troubleshooting

### Config reload not working

1. Check if auto-reload is enabled:
   ```bash
   echo $MAGG_AUTO_RELOAD
   ```

2. Verify file permissions:
   ```bash
   ls -la ~/.magg/config.json
   ```

3. Check logs for errors:
   ```bash
   # Set debug logging
   export MAGG_LOG_LEVEL=DEBUG
   magg serve
   ```

### Reload fails with validation error

The logs will show which validation failed:
```
ERROR: Duplicate prefix 'test' found in servers 'server1' and 'server2'
ERROR: Server 'myserver' has neither command nor uri
```

Fix the configuration issue and save again.

### Server not responding after reload

If a server fails to start after reload:
1. Check the server's specific error in logs
2. Use `magg_check` tool to diagnose issues
3. Disable the problematic server until fixed

## Demo Script

Try the included demo script to see config reloading in action:

```bash
# Demo automatic reload with file watching
python scripts/demo_config_reload.py --mode auto

# Demo manual reload
python scripts/demo_config_reload.py --mode manual
```