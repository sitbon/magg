# /// script
# requires-python = ">=3.13"
# dependencies = [
# "anthropic>=0.54.0",
# "fastmcp<3",
# "magg>=0.3.4",
# ]
# ///
"""This example demonstrates how to use the FastMCP client with a custom sampling handler.

It connects to a local FastMCP server and uses the Anthropic API to handle sampling requests.
"""

import asyncio
import json

from anthropic import AsyncAnthropic
from fastmcp.client import Client
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
from mcp.types import CreateMessageRequestParams
from rich.traceback import install

from magg.util.transform import is_mcp_result_json_typed, extract_mcp_result_json, get_mcp_result_contents

mcp_url = "http://localhost:8000/mcp"


install(show_locals=True)



async def claude_sampling_handler(
        messages: list[SamplingMessage],
        params: CreateMessageRequestParams,
        context: RequestContext,
):
    client = AsyncAnthropic()

    claude_messages = [
        {"role": msg.role, "content": msg.content.text}
        for msg in messages if hasattr(msg.content, 'text')
    ]

    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        messages=claude_messages,
        max_tokens=params.maxTokens or 4096,
    )

    return response.content[0].text


async def main():
    # Create a client with the custom sampling handler
    client = Client(mcp_url, sampling_handler=claude_sampling_handler)

    async with client:
        # Call a tool that uses sampling
        result = await client.call_tool(
            name="magg_smart_configure",
            arguments={
                "source": "https://github.com/wrtnlabs/calculator-mcp"
            },
        )

        for content in result:
            if is_mcp_result_json_typed(content):
                json_content = extract_mcp_result_json(content)
                print(json.dumps(json.loads(json_content), indent=2))
            else:
                data = get_mcp_result_contents(content)

                if isinstance(data, str):
                    print("Text Result:", data)
                else:
                    print("Data Result:", data)


if __name__ == "__main__":
    asyncio.run(main())
