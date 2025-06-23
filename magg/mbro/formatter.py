"""Output formatters for mbro.
"""
import json
import sys
import traceback
from typing import Any, List

from mcp.types import Content, TextResourceContents, BlobResourceContents, GetPromptResult
from rich.console import Console
from rich.json import JSON
from rich.table import Table


class OutputFormatter:
    """Handle formatted output for mbro."""

    def __init__(self, json_only: bool = False, use_rich: bool | None = True, indent: int = 2):
        self.use_rich = use_rich if use_rich is not None else True
        self.console = Console() if self.use_rich else None
        self.json_only = json_only
        self.indent = indent if indent > 0 else None

    def format_json(self, data: Any) -> None:
        """Format and print JSON data."""
        if self.use_rich:
            output = JSON.from_data(data, indent=self.indent, default=str)
            self.console.print(output)
        else:
            output = json.dumps(data, indent=self.indent, default=str)
            print(output)

    def format_error(self, message: str, exception: Exception | None = None) -> None:
        """Format and print an error message."""
        if self.json_only:
            error_data = {"error": message}
            if exception:
                # noinspection PyTypeChecker
                error_data["exception"] = {
                    "type": type(exception).__name__,
                    "message": str(exception),
                    "traceback": traceback.format_exc().splitlines()
                }

            self.format_json(error_data)
        else:
            if self.use_rich:
                self.console.print(f"[red]Error: {message}[/red]")
                if exception:
                    self.console.print_exception(show_locals=False)
            else:
                print(f"Error: {message}", file=sys.stderr)
                if exception:
                    traceback.print_exc()

    def format_success(self, message: str) -> None:
        """Format and print a success message."""
        if self.json_only:
            self.format_json({"success": message})
        else:
            self.print(
                message if not self.use_rich else
                f"[green]{message}[/green]"
            )

    def format_info(self, message: str, key: str | None = None) -> None:
        """Format and print an info message."""
        if self.json_only:
            self.format_json({key or "info": message})
        else:
            self.print(message)

    def print(self, *objects, **kwds) -> None:
        """Print a message using the console or standard output."""
        file = kwds.pop('file', sys.stdout)

        if self.use_rich:
            self.console.print(*objects, **kwds)
        else:
            kwds['file'] = file
            print(*objects, **kwds)

    def format_resource(self, resource: TextResourceContents | BlobResourceContents):
        """Format a resource for display."""
        resource_data = self.decode_resource(resource)

        if self.json_only:
            if isinstance(resource_data, str):
                resource_dict = resource.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True)
            else:
                resource_dict = resource_data

            self.format_json(resource_dict)

        else:
            if isinstance(resource_data, str):
                self.print(resource_data)

            elif isinstance(resource_data, (list, dict)):
                self.format_json(resource_data)

    def format_content(self, content: Content):
        content_data = self.decode_content(content)

        if self.json_only:
            if isinstance(content_data, str):
                content_dict = content.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True)
            else:
                content_dict = content_data

            self.format_json(content_dict)

        else:
            if isinstance(content_data, str):
                self.print(content_data)

            elif isinstance(content_data, (list, dict)):
                self.format_json(content_data)

    def format_resource_list(self, resources: list[TextResourceContents | BlobResourceContents]) -> None:
        """Format a list of resource objects."""

        if self.json_only:
            output = []

            for resource in resources:
                decoded = self.decode_resource(resource)
                if isinstance(decoded, str):
                    output.append(resource.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True))
                else:
                    output.append(decoded)

            self.format_json(output)

        else:
            for resource in resources:
                self.format_resource(resource)

    def format_content_list(self, contents: List[Content]) -> None:
        """Format a list of Content objects."""
        if self.json_only:
            output = []

            for content in contents:
                decoded = self.decode_content(content)
                if isinstance(decoded, str):
                    output.append(content.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True))
                else:
                    output.append(decoded)

            self.format_json(output)
        else:
            for content in contents:
                self.format_content(content)

    @classmethod
    def decode_resource(cls, resource: TextResourceContents | BlobResourceContents) -> str | dict[str, Any] | list:
        """Decode a resource to a string or dict representation for display.
        """
        if hasattr(resource, 'text'):
            if resource.mimeType == 'application/json':
                try:
                    return json.loads(resource.text)
                except json.JSONDecodeError:
                    return resource.text

            # TODO: Find a way to indicate the mime type when it is not None?
            return resource.text

        elif hasattr(resource, 'blob'):
            # TODO: Find a way to indicate the mime type and/or base64 encoding?
            return resource.blob

        return resource.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True)

    @classmethod
    def decode_content(cls, content: Content) -> str | dict[str, Any] | list:
        """Decode content to a string or dict representation for display.
        """
        match content.type:
            case "text":
                if content.annotations and getattr(content.annotations, 'mimeType', '') == 'application/json':
                    try:
                        return json.loads(content.text)
                    except json.JSONDecodeError:
                        return content.text
                else:
                    return content.text

            case "resource":
                return cls.decode_resource(content.resource)

        return content.model_dump(mode="json", exclude_defaults=True, exclude_none=True, exclude_unset=True)

    def format_connections_table(self, connections: list[dict[str, Any]], *, extended: bool = False) -> None:
        """Format connections as a table.
        """
        if not connections:
            self.format_info("No connections configured.")
            return

        if self.json_only:
            self.format_json({"connections": connections})
        elif self.use_rich:
            table = Table(title="Connections")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Status")

            if extended:
                table.add_column("Tools", justify="right")
                table.add_column("Resources", justify="right")
                table.add_column("Prompts", justify="right")

            for conn in connections:
                status = "[green]Connected[/green]" if conn["connected"] else "[red]Disconnected[/red]"
                if conn["current"]:
                    status += " [bold](current)[/bold]"

                extend = []

                if extended:
                    extend.extend(map(str, [
                        len(conn.get('tools') or []),
                        len(conn.get('resources') or []),
                        len(conn.get('prompts') or []),
                    ]))

                table.add_row(
                    conn['name'],
                    conn['type'],
                    status,
                    *extend,
                )

            self.console.print(table)
        else:
            # Plain text table
            output_lines = ["Connections:"]
            for conn in connections:
                status = "Connected" if conn["connected"] else "Disconnected"
                if conn["current"]:
                    status += " (current)"
                output_lines.append(f"  {conn['name']} ({conn['type']}) - {status}")
                if extended:
                    output_lines.append(
                        f"    Tools: {len(conn.get('tools') or [])}, "
                        f"Resources: {len(conn.get('resources') or [])}, "
                        f"Prompts: {len(conn.get('prompts') or [])}"
                    )
            self.print('\n'.join(output_lines))

    def format_tool_info(self, tool: dict[str, Any]) -> None:
        """Format detailed tool information."""
        if self.json_only:
            tool_data = {
                "type": "tool",
                "name": tool['name'],
                "description": tool['description']
            }
            if tool.get('inputSchema'):
                tool_data["inputSchema"] = tool['inputSchema']

            self.format_json(tool_data)
            return

        # Tool name header
        self.print(
            f"\nTool: {tool['name']}\n" if not self.use_rich else
            f"\n[bold]Tool: [cyan]{tool['name']}[/cyan][/bold]\n"
        )

        # Description
        if tool.get('description'):
            self.print("Description:")
            desc_lines = tool['description'].strip().split('\n')
            for line in desc_lines:
                self.print(f"  {line}")
            self.print("")

        # Input schema
        if tool.get('inputSchema'):
            schema = tool['inputSchema']
            if schema.get('properties'):
                self.print(
                    "Parameters:" if not self.use_rich else
                    "[bold]Parameters:[/bold]"
                )
                for prop_name, prop_info in schema['properties'].items():
                    # Parameter name and type
                    prop_type = prop_info.get('anyOf', prop_info.get('type', 'any'))
                    if isinstance(prop_type, list):
                        prop_type = ' | '.join(x.get('type', 'any') for x in prop_type)
                    required = prop_name in schema.get('required', [])
                    req_marker = " (required)" if required else " (optional)"

                    self.print(
                        f"  {prop_name} ({prop_type}){req_marker}" if not self.use_rich else
                        f"  [cyan]{prop_name}[/cyan] ({prop_type}){req_marker}"
                    )

                    # Parameter description
                    if prop_info.get('description'):
                        desc_lines = prop_info['description'].strip().split('\n')
                        for line in desc_lines:
                            self.print(f"    {line}")
            else:
                self.print("No parameters required")

    def format_resource_info(self, resource: dict[str, Any]) -> None:
        """Format detailed resource information."""
        if self.json_only:
            self.format_json({
                "type": "resource",
                "name": resource['name'],
                "uri": resource.get('uri', resource.get('uriTemplate', '')),
                "is_template": 'uriTemplate' in resource,
                "mime_type": resource.get('mimeType', ''),
                "description": resource.get('description', '')
            })
            return

        # Resource name header
        self.print(
            f"\nResource: {resource['name']}\n" if not self.use_rich else
            f"\n[bold]Resource: [cyan]{resource['name']}[/cyan][/bold]\n"
        )

        # URI or URI template
        if resource.get('uri'):
            self.print(
                f"URI: {resource['uri']}" if not self.use_rich else
                f"[bold]URI:[/bold] {resource['uri']}"
            )
        elif resource.get('uriTemplate'):
            self.print(
                f"URI Template: {resource['uriTemplate']}" if not self.use_rich else
                f"[bold]URI Template:[/bold] {resource['uriTemplate']}"
            )

        # MIME type
        if resource.get('mimeType'):
            self.print(
                f"Type: {resource['mimeType']}" if not self.use_rich else
                f"[bold]Type:[/bold] {resource['mimeType']}"
            )

        # Description
        if resource.get('description'):
            self.print("")
            self.print(
                "Description:" if not self.use_rich else
                "[bold]Description:[/bold]"
            )
            desc_lines = resource['description'].strip().split('\n')
            for line in desc_lines:
                self.print(f"  {line}")

    def format_prompt_info(self, prompt: dict[str, Any]) -> None:
        """Format detailed prompt information."""
        if self.json_only:
            prompt_data = {
                "type": "prompt",
                "name": prompt['name'],
                "description": prompt['description']
            }
            if prompt.get('arguments'):
                prompt_data["arguments"] = prompt['arguments']

            self.format_json(prompt_data)
            return

        # Prompt name header
        self.print(
            f"\nPrompt: {prompt['name']}\n" if not self.use_rich else
            f"\n[bold]Prompt: [cyan]{prompt['name']}[/cyan][/bold]\n"
        )

        # Description
        if prompt.get('description'):
            self.print("Description:")
            desc_lines = prompt['description'].strip().split('\n')
            for line in desc_lines:
                self.print(f"  {line}")
            self.print("")

        # Arguments
        if prompt.get('arguments'):
            self.print(
                "Arguments:" if not self.use_rich else
                "[bold]Arguments:[/bold]"
            )
            for arg in prompt['arguments']:
                arg_name = arg.get('name', 'unknown')
                required = arg.get('required', False)
                req_marker = " (required)" if required else " (optional)"

                self.print(
                    f"  {arg_name}{req_marker}" if not self.use_rich else
                    f"  [cyan]{arg_name}[/cyan]{req_marker}"
                )

                # Argument description
                if arg.get('description'):
                    desc_lines = arg['description'].strip().split('\n')
                    for line in desc_lines:
                        self.print(f"    {line}")
        else:
            self.print("No arguments required")

    def format_prompt_result(self, result: GetPromptResult):
        """Format the result of a prompt call.

        GetPromptResult has a description and messages.
        Each message has "role" and "content" ("type" and "text" for Content, usually).
        """
        if self.json_only:
            prompt_data = result.model_dump(mode="json", exclude_none=True, exclude_defaults=True, exclude_unset=True, by_alias=True)
            self.format_json(prompt_data)
        else:
            if result.description:
                self.print(
                    f"\n{result.description}\n" if not self.use_rich else
                    f"\n[bold]{result.description}[/bold]\n"
                )

            for msg in result.messages:
                role_text = f"{msg.role}:"
                if self.use_rich:
                    match msg.role.lower():
                        case "assistant":
                            role_text = f"[green]{role_text}[/green]"
                        case "user":
                            role_text = f"[blue]{role_text}[/blue]"
                        case "system":
                            role_text = f"[yellow]{role_text}[/yellow]"
                        case _:
                            role_text = f"[white]{role_text}[/white]"

                self.print(role_text)

                content = self.decode_content(msg.content)
                if isinstance(content, str):
                    for line in content.splitlines():
                        self.print(f"  {line}")
                else:
                    self.print("  ", end="")
                    self.format_json(content)

                self.print("")

    def format_search_results(self, term: str, tools: list, resources: list, prompts: list) -> None:
        """Format search results."""
        total_matches = len(tools) + len(resources) + len(prompts)

        if total_matches == 0:
            self.print(f"No results found for '{term}'")
            return

        if self.json_only:
            results = {
                "query": term,
                "total_matches": total_matches,
                "tools": [{"name": t['name'], "description": t['description']} for t in tools],
                "resources": [{"name": r['name'], "uri": r.get('uri', r.get('uriTemplate', '')), "description": r['description']} for r in resources],
                "prompts": [{"name": p['name'], "description": p['description']} for p in prompts]
            }
            self.format_json(results)
            return

        output_lines = [
            f"\nSearch results for '{term}' ({total_matches} matches):\n" if not self.use_rich else
            f"\n[bold]Search results for '{term}' ({total_matches} matches):[/bold]\n"
        ]

        if tools:
            output_lines.append(
                f"Tools ({len(tools)}):" if not self.use_rich else
                f"[bold]Tools ({len(tools)}):[/bold]"
            )
            for tool in tools:
                output_lines.append(
                    f"  {tool['name']}" if not self.use_rich else
                    f"  [cyan]{tool['name']}[/cyan]"
                )
                if tool.get('description'):
                    # Show first line of description
                    desc_first_line = tool['description'].strip().split('\n')[0]
                    if len(desc_first_line) > 60:
                        desc_first_line = desc_first_line[:57] + "..."
                    output_lines.append(f"    {desc_first_line}")
            output_lines.append("")

        if resources:
            output_lines.append(
                f"Resources ({len(resources)}):" if not self.use_rich else
                f"[bold]Resources ({len(resources)}):[/bold]"
            )
            for resource in resources:
                output_lines.append(
                    f"  {resource['name']}" if not self.use_rich else
                    f"  [cyan]{resource['name']}[/cyan]"
                )
                if resource.get('description'):
                    # Show first line of description
                    desc_first_line = resource['description'].strip().split('\n')[0]
                    if len(desc_first_line) > 60:
                        desc_first_line = desc_first_line[:57] + "..."
                    output_lines.append(f"    {desc_first_line}")
            output_lines.append("")

        if prompts:
            output_lines.append(
                f"Prompts ({len(prompts)}):" if not self.use_rich else
                f"[bold]Prompts ({len(prompts)}):[/bold]"
            )
            for prompt in prompts:
                output_lines.append(
                    f"  {prompt['name']}" if not self.use_rich else
                    f"  [cyan]{prompt['name']}[/cyan]"
                )
                if prompt.get('description'):
                    # Show first line of description
                    desc_first_line = prompt['description'].strip().split('\n')[0]
                    if len(desc_first_line) > 60:
                        desc_first_line = desc_first_line[:57] + "..."
                    output_lines.append(f"    {desc_first_line}")
            output_lines.append("")

        # Single print call with joined lines
        self.print('\n'.join(output_lines).rstrip())

    def format_help(self) -> None:
        """Format help text."""
        if self.json_only:
            help_data = {
                "help": {
                    "connection_management": [
                        {"command": "connect <name> <connection_string>", "description": "Connect to an MCP server"},
                        {"command": "connections, conns", "description": "List all connections"},
                        {"command": "switch <name>", "description": "Switch to a different connection"},
                        {"command": "disconnect <name>", "description": "Disconnect from a server"},
                        {"command": "status", "description": "Show current status"},
                    ],
                    "server_exploration": [
                        {"command": "tools [filter]", "description": "List available tools"},
                        {"command": "resources [filter]", "description": "List available resources"},
                        {"command": "prompts [filter]", "description": "List available prompts"},
                        {"command": "search <term>", "description": "Search tools, resources, and prompts"},
                        {"command": "info <tool|resource|prompt> <name>", "description": "Show detailed info"}
                    ],
                    "tool_interaction": [
                        {"command": "call <tool_name> [json_args]", "description": "Call a tool"},
                        {"command": "resource <uri>", "description": "Get a resource"},
                        {"command": "prompt <name> [json_args]", "description": "Get a prompt"}
                    ]
                }
            }
            self.format_json(help_data)
            return

        help_text = """
Available commands:

Connection Management:
  connect <name> <connection_string>  - Connect to an MCP server
  connections, conns                  - List all connections
  switch <name>                       - Switch to a different connection
  disconnect <name>                   - Disconnect from a server
  refresh                             - Refresh capabilities for current connection

Server Exploration:
  tools [filter]                      - List available tools
  resources [filter]                  - List available resources
  prompts [filter]                    - List available prompts
  search <term>                       - Search tools, resources, and prompts
  info <tool|resource|prompt> <name>  - Show detailed info

Tool Interaction:
  call <tool_name> [json_args]        - Call a tool
  resource <uri>                      - Get a resource
  prompt <name> [json_args]           - Get a prompt

Examples:
  connect magg "http://localhost:8080"
  connect calc "npx @wrtnlabs/calculator-mcp"
  tools
  call magg_status
  call magg_search_tools {"query": "calculator", "limit": 3}
  call add {"a": 5, "b": 3}
  search calculator
  info tool magg_status

JSON Tips (REPL):
  - Use double quotes for JSON strings: {"key": "value"}
  - No quotes for numbers: {"count": 42}
  - Boolean values: {"enabled": true}
  - Arrays: {"items": [1, 2, 3]}
        """
        self.print(help_text)

    def format_tools_list(self, tools: list[dict[str, Any]]) -> None:
        """Format a list of tools."""
        if self.json_only:
            self.format_json({"tools": tools})
            return

        output_lines = [
            f"\nTools ({len(tools)} available):\n"
            if not self.use_rich else
            f"\n[bold]Tools ({len(tools)} available):[/bold]\n"
        ]

        for tool in tools:
            # Tool name
            output_lines.append(
                tool['name'] if not self.use_rich else
                f"[cyan bold]{tool['name']}[/cyan bold]"
            )

            # Description (may be multiline)
            if tool.get('description'):
                desc_lines = tool['description'].strip().split('\n')
                for line in desc_lines:
                    output_lines.append(f"  {line}")

            # Input schema
            if tool.get('inputSchema'):
                schema = tool['inputSchema']
                if schema.get('properties'):
                    output_lines.append("  Parameters:")
                    for prop_name, prop_info in schema['properties'].items():
                        # Parameter name and type
                        prop_type = prop_info.get('anyOf', prop_info.get('type', 'any'))
                        if isinstance(prop_type, list):
                            prop_type = ' | '.join(x.get('type', 'any') for x in prop_type)
                        required = prop_name in schema.get('required', [])
                        req_marker = " (required)" if required else ""

                        output_lines.append(f"    - {prop_name} ({prop_type}){req_marker}")

                        # Parameter description (may be multiline)
                        if prop_info.get('description'):
                            desc_lines = prop_info['description'].strip().split('\n')
                            for line in desc_lines:
                                output_lines.append(f"      {line}")
                else:
                    output_lines.append("  No parameters required")

            output_lines.append("")  # Blank line between tools

        # Single print call with joined lines
        self.print('\n'.join(output_lines))

    def format_resources_list(self, resources: list[dict[str, Any]]) -> None:
        """Format a list of resources."""
        if self.json_only:
            self.format_json(resources)
            return

        output_lines = [
            f"\nResources ({len(resources)} available):\n"
            if not self.use_rich else
            f"\n[bold]Resources ({len(resources)} available):[/bold]\n"
        ]

        for resource in resources:
            # Resource name
            output_lines.append(
                resource['name'] if not self.use_rich else
                f"[cyan bold]{resource['name']}[/cyan bold]"
            )

            # URI or URI template
            if resource.get('uri'):
                output_lines.append(f"  URI: {resource['uri']}")
            elif resource.get('uriTemplate'):
                output_lines.append(f"  URI Template: {resource['uriTemplate']}")

            # MIME type
            if resource.get('mimeType'):
                output_lines.append(f"  Type: {resource['mimeType']}")

            # Description (may be multiline)
            if resource.get('description'):
                desc_lines = resource['description'].strip().split('\n')
                output_lines.append("  Description:")
                for line in desc_lines:
                    output_lines.append(f"    {line}")

            output_lines.append("")  # Blank line between resources

        # Single print call with joined lines
        self.print('\n'.join(output_lines))

    def format_prompts_list(self, prompts: list[dict[str, Any]]) -> None:
        """Format a list of prompts."""
        if self.json_only:
            self.format_json({"prompts": prompts})
            return

        output_lines = [
            f"\nPrompts ({len(prompts)} available):\n"
            if not self.use_rich else
            f"\n[bold]Prompts ({len(prompts)} available):[/bold]\n"
        ]

        for prompt in prompts:
            # Prompt name
            output_lines.append(
                prompt['name'] if not self.use_rich else
                f"[cyan bold]{prompt['name']}[/cyan bold]"
            )

            # Description (may be multiline)
            if prompt.get('description'):
                desc_lines = prompt['description'].strip().split('\n')
                for line in desc_lines:
                    output_lines.append(f"  {line}")

            # Arguments
            if prompt.get('arguments'):
                output_lines.append("  Arguments:")
                for arg in prompt['arguments']:
                    arg_name = arg.get('name', 'unknown')
                    required = arg.get('required', False)
                    req_marker = " (required)" if required else ""

                    output_lines.append(f"    - {arg_name}{req_marker}")

                    # Argument description (may be multiline)
                    if arg.get('description'):
                        desc_lines = arg['description'].strip().split('\n')
                        for line in desc_lines:
                            output_lines.append(f"      {line}")
            else:
                output_lines.append("  No arguments required")

            output_lines.append("")  # Blank line between prompts

        # Single print call with joined lines
        self.print('\n'.join(output_lines))
