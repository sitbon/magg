# MCP Messaging and Notifications

Magg provides comprehensive support for MCP messaging and notifications, enabling real-time communication between clients and backend servers. This feature leverages FastMCP's messaging capabilities to provide transparent message forwarding across multiple backend servers.

## Overview

The messaging system consists of several components:

1. **Client-side message handling** - MaggClient with MessageHandler support
2. **Server-side message coordination** - ProxyFastMCP with message routing
3. **Message forwarding** - Transparent proxy of notifications from backend servers
4. **Message aggregation** - Coordination of notifications from multiple servers

## Client-Side Usage

### Basic Message Handling

```python
from magg import MaggClient, MaggMessageHandler
import mcp.types

# Create a custom message handler
def on_tool_changed(notification: mcp.types.ToolListChangedNotification):
    print(f"Tools changed!")

def on_progress(notification: mcp.types.ProgressNotification):
    print(f"Progress: {notification.progress}/{notification.total}")

# Create handler with callbacks
handler = MaggMessageHandler(
    on_tool_list_changed=on_tool_changed,
    on_progress=on_progress
)

# Create client with message handling
client = MaggClient(
    "http://localhost:8000",
    message_handler=handler
)

async with client:
    # All notifications from backend servers will be forwarded to your handler
    tools = await client.list_tools()
```

### Custom Message Handler Class

```python
from magg.messaging import MaggMessageHandler
import mcp.types

class MyMessageHandler(MaggMessageHandler):
    def __init__(self):
        super().__init__()
        self.tool_cache = []
    
    async def on_tool_list_changed(
        self, 
        notification: mcp.types.ToolListChangedNotification
    ):
        print("Tool list changed - clearing cache")
        self.tool_cache.clear()
    
    async def on_resource_list_changed(
        self, 
        notification: mcp.types.ResourceListChangedNotification
    ):
        print("Resource list changed")
    
    async def on_progress(
        self, 
        notification: mcp.types.ProgressNotification
    ):
        print(f"Progress: {notification.progress}")

# Use custom handler
handler = MyMessageHandler()
client = MaggClient("http://localhost:8000", message_handler=handler)
```

## Supported Notification Types

The messaging system supports all standard MCP notifications:

- **`ToolListChangedNotification`** - Tool inventory changes
- **`ResourceListChangedNotification`** - Resource inventory changes  
- **`PromptListChangedNotification`** - Prompt inventory changes
- **`ResourceUpdatedNotification`** - Individual resource updates
- **`ProgressNotification`** - Progress updates from long-running operations
- **`LoggingMessageNotification`** - Log messages from servers
- **`CancelledNotification`** - Request cancellation notifications

## Server-Side Architecture

### Message Routing

Magg's server automatically sets up message forwarding when mounting backend servers:

```python
# In ServerManager.mount_server():
# 1. Create BackendMessageHandler for each server
# 2. Connect Client with message_handler
# 3. Mount server with ProxyFastMCP.mount_backend_server()
# 4. All notifications automatically forwarded to clients
```

### Message Coordination

The `ServerMessageCoordinator` handles:

- **Deduplication** - Prevents duplicate notifications
- **Aggregation** - Combines notifications from multiple servers
- **Routing** - Sends notifications to appropriate client handlers
- **State tracking** - Maintains notification state for debugging

### Debugging Message Flow

```python
# Access message coordinator for debugging
coordinator = magg_server.mcp.message_coordinator
state = await coordinator.get_notification_state()
print(f"Servers with tool changes: {state.get('tool_changes', set())}")
```

## Implementation Details

### Client Message Handler Registration

MaggClient automatically forwards the message handler to the underlying FastMCP Client:

```python
# In MaggClient.__init__():
super().__init__(
    transport,
    message_handler=message_handler,  # Passed through to FastMCP
    # ... other args
)
```

### Backend Server Message Forwarding

Each backend server gets its own message handler:

```python
# In ServerManager.mount_server():
message_handler = BackendMessageHandler(
    server_id=server.name,
    coordinator=self.mcp.message_coordinator
)
client = Client(transport, message_handler=message_handler)
```

### Message Flow

1. **Backend server** sends notification (e.g., tool list changed)
2. **BackendMessageHandler** receives notification
3. **ServerMessageCoordinator** processes and routes notification
4. **MessageRouter** forwards to registered client handlers
5. **Client MessageHandler** receives and processes notification

## Advanced Features

### Server-Specific Handlers

```python
from magg.messaging import MessageRouter

router = MessageRouter()

# Register handler for specific server
await router.register_handler(my_handler, server_id="weather-server")

# Register global handler for all servers  
await router.register_handler(global_handler, server_id=None)
```

### Manual Notification Sending

From server-side tools using Context:

```python
from fastmcp.server.context import Context

@server.tool
async def my_tool(ctx: Context) -> str:
    # Do some work that changes available tools
    # ...
    
    # Manually trigger tool list change notification
    await ctx.send_tool_list_changed()
    
    return "Tools updated"
```

## Error Handling

Message handlers should be robust:

```python
class RobustMessageHandler(MaggMessageHandler):
    async def on_tool_list_changed(self, notification):
        try:
            # Handle notification
            await self.process_tool_change(notification)
        except Exception as e:
            logger.error(f"Error handling tool change: {e}")
            # Don't re-raise - prevents breaking message flow
```

## Performance Considerations

- **Async handlers** - All message handlers are async to prevent blocking
- **Concurrent processing** - Multiple handlers called concurrently with `asyncio.gather`
- **Error isolation** - Handler exceptions don't affect other handlers or message flow
- **Minimal overhead** - Message routing adds minimal latency to notifications

## Migration from Previous Versions

Existing Magg clients continue to work unchanged. To add message handling:

```python
# Before
client = MaggClient("http://localhost:8000")

# After  
handler = MaggMessageHandler(on_tool_list_changed=my_callback)
client = MaggClient("http://localhost:8000", message_handler=handler)
```

No server-side changes are required - message forwarding is automatically enabled for all mounted servers.