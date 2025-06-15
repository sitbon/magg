"""MCP client connectivity for mbro."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client


class MCPConnection:
    """Represents a connection to an MCP server."""
    
    def __init__(self, name: str, connection_type: str, connection_string: str):
        self.name = name
        self.connection_type = connection_type  # 'http' or 'command'
        self.connection_string = connection_string
        self.client: Client | None = None
        self.connected = False
        self.tools: list[dict[str, Any]] = []
        self.resources: list[dict[str, Any]] = []
        self.prompts: list[dict[str, Any]] = []
        self._context_manager = None
    
    async def connect(self) -> bool:
        """Connect to the MCP server using FastMCP Client."""
        try:
            # Create FastMCP client 
            if self.connection_string.startswith("http"):
                # For HTTP connections, ensure proper MCP endpoint
                url = self.connection_string
                if not url.endswith("/mcp/"):
                    url = url.rstrip("/") + "/mcp/"
                self.client = Client(url)
            else:
                # For command connections, pass the string directly
                # FastMCP Client will handle the parsing
                self.client = Client(self.connection_string)
            
            # Test connection by listing tools within a context
            async with self.client as conn:
                await self.refresh_capabilities_with_client(conn)
                self.connected = True
                return True
            
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            self.client = None
            return False
    
    async def refresh_capabilities(self) -> None:
        """Refresh the list of available tools, resources, and prompts."""
        if not self.client:
            return
        
        async with self.client as conn:
            await self.refresh_capabilities_with_client(conn)
    
    async def refresh_capabilities_with_client(self, client) -> None:
        """Refresh capabilities using a connected client."""
        try:
            # Get tools
            tools_result = await client.list_tools()
            self.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema.model_dump() if hasattr(tool.inputSchema, 'model_dump') and tool.inputSchema else (tool.inputSchema if tool.inputSchema else {})
                }
                for tool in tools_result
            ]
            
            # Get resources
            try:
                resources_result = await client.list_resources()
                self.resources = [
                    {
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mimeType": resource.mimeType
                    }
                    for resource in resources_result
                ]
            except Exception:
                self.resources = []
            
            # Get prompts
            try:
                prompts_result = await client.list_prompts()
                self.prompts = [
                    {
                        "name": prompt.name,
                        "description": prompt.description,
                        "arguments": [
                            {
                                "name": arg.name,
                                "description": arg.description,
                                "required": arg.required
                            }
                            for arg in (prompt.arguments or [])
                        ]
                    }
                    for prompt in prompts_result
                ]
            except Exception:
                self.prompts = []
                
        except Exception as e:
            print(f"Failed to refresh capabilities: {e}")
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any] = None) -> Any:
        """Call a tool on the connected MCP server."""
        if not self.client or not self.connected:
            raise RuntimeError("Not connected to server")
        
        if arguments is None:
            arguments = {}
        
        try:
            async with self.client as conn:
                result = await conn.call_tool(tool_name, arguments)
                return result
        except Exception as e:
            raise RuntimeError(f"Failed to call tool '{tool_name}': {e}")
    
    async def get_resource(self, uri: str) -> Any:
        """Get a resource from the connected MCP server."""
        if not self.client or not self.connected:
            raise RuntimeError("Not connected to server")
        
        try:
            async with self.client as conn:
                result = await conn.read_resource(uri)
                return result
        except Exception as e:
            raise RuntimeError(f"Failed to get resource '{uri}': {e}")
    
    async def get_prompt(self, name: str, arguments: dict[str, Any] = None) -> Any:
        """Get a prompt from the connected MCP server."""
        if not self.client or not self.connected:
            raise RuntimeError("Not connected to server")
        
        if arguments is None:
            arguments = {}
        
        try:
            async with self.client as conn:
                result = await conn.get_prompt(name, arguments)
                return result
        except Exception as e:
            raise RuntimeError(f"Failed to get prompt '{name}': {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception:
                pass
            self.client = None
        self.connected = False
        self.tools = []
        self.resources = []
        self.prompts = []


class MCPBrowser:
    """Main MCP browser class for managing connections."""
    
    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self.current_connection: str | None = None
    
    async def add_connection(self, name: str, connection_string: str) -> bool:
        """Add a new MCP connection using FastMCP Client connection string."""
        if name in self.connections:
            print(f"Connection '{name}' already exists")
            return False
        
        # Determine connection type from the connection string
        if connection_string.startswith("http"):
            connection_type = "http"
        else:
            connection_type = "command"
        
        connection = MCPConnection(name, connection_type, connection_string)
        success = await connection.connect()
        
        if success:
            self.connections[name] = connection
            if not self.current_connection:
                self.current_connection = name
            print(f"✅ Connected to '{name}' ({connection_type})")
            print(f"   Tools: {len(connection.tools)}, Resources: {len(connection.resources)}, Prompts: {len(connection.prompts)}")
            return True
        else:
            print(f"❌ Failed to connect to '{name}'")
            return False
    
    async def switch_connection(self, name: str) -> bool:
        """Switch to a different connection."""
        if name not in self.connections:
            print(f"Connection '{name}' not found")
            return False
        
        if not self.connections[name].connected:
            print(f"Connection '{name}' is not active")
            return False
        
        self.current_connection = name
        print(f"Switched to connection '{name}'")
        return True
    
    async def remove_connection(self, name: str) -> bool:
        """Remove a connection."""
        if name not in self.connections:
            print(f"Connection '{name}' not found")
            return False
        
        await self.connections[name].disconnect()
        del self.connections[name]
        
        if self.current_connection == name:
            self.current_connection = None
            if self.connections:
                # Switch to first available connection
                self.current_connection = next(iter(self.connections.keys()))
        
        print(f"Removed connection '{name}'")
        return True
    
    def get_current_connection(self) -> MCPConnection | None:
        """Get the current active connection."""
        if not self.current_connection:
            return None
        return self.connections.get(self.current_connection)
    
    def list_connections(self) -> list[dict[str, Any]]:
        """List all connections with their status."""
        result = []
        for name, conn in self.connections.items():
            result.append({
                "name": name,
                "type": conn.connection_type,
                "connected": conn.connected,
                "current": name == self.current_connection,
                "tools": len(conn.tools),
                "resources": len(conn.resources),
                "prompts": len(conn.prompts)
            })
        return result
    
    async def refresh_current(self) -> bool:
        """Refresh capabilities for the current connection."""
        conn = self.get_current_connection()
        if not conn:
            print("No active connection")
            return False
        
        await conn.refresh_capabilities()
        print(f"Refreshed capabilities for '{self.current_connection}'")
        return True
