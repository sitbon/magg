#!/usr/bin/env python3
"""Example demonstrating Magg's messaging and notifications feature.

This example shows how to use MaggClient with message handlers to receive
notifications from backend MCP servers.
"""
import asyncio
import mcp.types
from magg import MaggClient, MaggMessageHandler


class CustomMessageHandler(MaggMessageHandler):
    """Custom message handler that logs all notifications."""

    def __init__(self):
        super().__init__()
        self.notification_count = 0

    async def on_message(self, message):
        """Called for all messages."""
        self.notification_count += 1
        print(f"📥 Received message #{self.notification_count}: {type(message).__name__}")

    async def on_tool_list_changed(self, notification: mcp.types.ToolListChangedNotification):
        """Called when tool list changes."""
        print("🔧 Tool list changed! Available tools may have been updated.")

    async def on_resource_list_changed(self, notification: mcp.types.ResourceListChangedNotification):
        """Called when resource list changes."""
        print("📁 Resource list changed! Available resources may have been updated.")

    async def on_progress(self, notification: mcp.types.ProgressNotification):
        """Called for progress updates."""
        if notification.params:
            progress = notification.params.progress
            total = notification.params.total
            if total:
                percentage = (progress / total) * 100
                print(f"⏳ Progress: {progress}/{total} ({percentage:.1f}%)")
            else:
                print(f"⏳ Progress: {progress}")

    async def on_logging_message(self, notification: mcp.types.LoggingMessageNotification):
        """Called for log messages from servers."""
        if notification.params:
            level = notification.params.level
            data = notification.params.data
            print(f"📝 Log [{level.upper()}]: {data}")


async def callback_example():
    """Example using callback-based message handler."""
    print("🚀 Starting callback-based message handler example...")

    def on_tool_change(notification):
        print("🔧 [Callback] Tools changed!")

    def on_progress(notification):
        if notification.params and notification.params.progress is not None:
            print(f"⏳ [Callback] Progress: {notification.params.progress}")

    # Create handler with callbacks
    handler = MaggMessageHandler(
        on_tool_list_changed=on_tool_change,
        on_progress=on_progress
    )

    # Create client with message handler
    client = MaggClient(
        "http://localhost:8000/mcp/",  # MCP endpoint with trailing slash
        message_handler=handler
    )

    try:
        async with client:
            print("✅ Connected to Magg server with message handling")

            # List tools to see what's available
            tools = await client.list_tools()
            print(f"📋 Found {len(tools)} tools available")

            # Keep connection open to receive notifications
            print("👂 Listening for notifications... (press Ctrl+C to stop)")
            await asyncio.sleep(30)  # Listen for 30 seconds

    except KeyboardInterrupt:
        print("\n🛑 Stopped listening for notifications")
    except Exception as e:
        print(f"❌ Error: {e}")


async def class_example():
    """Example using class-based message handler."""
    print("🚀 Starting class-based message handler example...")

    # Create custom handler
    handler = CustomMessageHandler()

    # Create client with message handler
    client = MaggClient(
        "http://localhost:8000/mcp/",  # MCP endpoint with trailing slash
        message_handler=handler
    )

    try:
        async with client:
            print("✅ Connected to Magg server with custom message handler")

            # List available capabilities
            tools = await client.list_tools()
            resources = await client.list_resources()
            prompts = await client.list_prompts()

            print(f"📋 Available capabilities:")
            print(f"  🔧 Tools: {len(tools)}")
            print(f"  📁 Resources: {len(resources)}")
            print(f"  💬 Prompts: {len(prompts)}")

            # Keep connection open to receive notifications
            print("👂 Listening for notifications... (press Ctrl+C to stop)")
            await asyncio.sleep(30)  # Listen for 30 seconds

            print(f"📊 Total notifications received: {handler.notification_count}")

    except KeyboardInterrupt:
        print("\n🛑 Stopped listening for notifications")
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run both examples."""
    print("🧲 Magg Messaging Example")
    print("=" * 50)
    print()
    print("This example demonstrates Magg's real-time messaging capabilities.")
    print("Make sure you have a Magg server running at http://localhost:8000")
    print()

    # Run callback example
    await callback_example()
    print()

    # Wait a bit between examples
    await asyncio.sleep(2)

    # Run class example
    await class_example()

    print()
    print("✨ Examples completed!")
    print()
    print("💡 Tips:")
    print("- Try adding/removing servers while the client is connected")
    print("- Run operations that trigger progress notifications")
    print("- Check server logs to see notifications being sent")


if __name__ == "__main__":
    asyncio.run(main())
