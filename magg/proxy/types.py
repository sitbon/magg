from typing import Literal, Self

from mcp.types import Annotations
from pydantic import Field

__all__ = "LiteralProxyType", "LiteralProxyAction", "ProxyResponseInfo"

LiteralProxyType = Literal["tool", "resource", "prompt"]
LiteralProxyAction = Literal["list", "info", "call"]


class ProxyResponseInfo(Annotations):
    """Metadata for proxy tool responses, pulled from annotations.

    Note that this info cannot always be retrieved, e.g., for empty results.

    It is mostly useful for introspection and debugging, and identifying
    query-typed results (list, info) that can be further processed by the client.
    """
    proxy_type: LiteralProxyType | None = Field(
        None,
        description="Type of the proxied capability (tool, resource, prompt).",
    )
    proxy_action: LiteralProxyAction | None = Field(
        None,
        description="Action performed by the proxy (list, info, call).",
    )
    proxy_path: str | None = Field(
        None,
        description="Name or URI of the specific tool/resource/prompt (with FastMCP prefixing).",
    )

    @classmethod
    def from_annotations(cls, annotations: Annotations) -> Self:
        """Create ProxyResponseInfo from Annotations."""
        return cls(**annotations.model_dump(mode="json", exclude_unset=True, exclude_defaults=True))
