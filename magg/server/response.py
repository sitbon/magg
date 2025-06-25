"""Response model for Magg tools.
"""
import json
from typing import Any, Union

from mcp.types import TextContent, EmbeddedResource, Annotations, TextResourceContents
from pydantic import BaseModel, ConfigDict, AnyUrl


class MaggResponse(BaseModel):
    """Standardized response format for Magg tools.

    Provides a consistent structure for both success and error cases,
    optimized for LLM consumption with automatic JSON serialization.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        json_schema_extra={
            "description": "Standardized response format for Magg tools.",
            "examples": [
                {
                    "output": {"message": "Success"},
                    "errors": None
                },
                {
                    "errors": ["An error occurred"],
                    "output": "But there might be some output"
                }
            ]
        }
    )

    errors: list[str | dict] | None = None
    output: Any | None = None

    @classmethod
    def success(cls, output: Any) -> "MaggResponse":
        """Create a success response with output data."""
        return cls(output=output)

    @classmethod
    def error(cls, error: str | dict | list) -> "MaggResponse":
        """Create an error response."""
        return cls(errors=[error] if not isinstance(error, (list, tuple)) else error)

    def add_error(self, error: Union[str, dict]) -> None:
        """Add an error to the response."""
        if self.errors is None:
            self.errors = []
        self.errors.append(error)

    @property
    def is_success(self) -> bool:
        """Check if this is a successful response (no errors)."""
        return self.errors is None or len(self.errors) == 0

    @property
    def is_error(self) -> bool:
        """Check if this response contains errors."""
        return not self.is_success

    @property
    def as_json_text_content(self) -> TextContent:
        """
        Provides a property to retrieve the JSON representation of the current object
        as a TextContent instance. This allows converting the object's content to a
        JSON format for further processing or storage.

        Returns:
            TextContent: The JSON text representation of the current object.
        """
        return self.as_json_response(self)

    def as_json_embedded_resource(
            self,
            embed_uri: str | None = None,
            annotations: dict | None = None,
            json_dump_kwds: dict | None = None,
            model_dump_kwds: dict | None = None,
    ) -> EmbeddedResource:
        """
        Convert the current object into an EmbeddedResource with specific settings.

        This method generates an embedded JSON resource for the object, optionally
        allowing customization through parameters such as annotations, URI embedding,
        and JSON/model serialization keywords.

        Parameters:
            embed_uri: str | None
                An optional URI to embed within the JSON resource.
            annotations: dict | None
                An optional dictionary of metadata or annotations to include in
                the embedded JSON resource.
            json_dump_kwds: dict | None
                Optional keyword arguments to customize the JSON serialization
                process.
            model_dump_kwds: dict | None
                Optional keyword arguments to customize the model serialization
                process before being converted into JSON.

        Returns:
            EmbeddedResource
                The resulting JSON-formatted embedded resource.

        Raises:
            This method does not explicitly specify errors it may raise.
        """
        return self.as_json_response(
            self,
            embed_uri=embed_uri,
            annotations=annotations,
            json_dump_kwds=json_dump_kwds,
            model_dump_kwds=model_dump_kwds,
        )

    @classmethod
    def as_text_resource(
            cls,
            uri: AnyUrl | str,
            data: str | dict,
            mime_type: str | None = None,
            **json_dump_kwds
    ) -> TextResourceContents:
        """
        Create a TextResourceContents from a string or dict.

        If data is a dict, it will be serialized to JSON.
        """
        if isinstance(uri, str):
            uri = AnyUrl(uri)

        if isinstance(data, dict):
            json_dump_kwds.setdefault("indent", None)
            json_dump_kwds.setdefault("default", str)

            text_data = json.dumps(data, **json_dump_kwds)

            if mime_type is None:
                mime_type = "application/json"
        else:
            text_data = data

            if mime_type is None:
                mime_type = "text/plain"

        return TextResourceContents(
            uri=uri,
            mimeType=mime_type,
            text=text_data,
        )

    @classmethod
    def as_json_response(
            cls,
            data: Any, /, *,
            embed_uri: str | None = None,
            annotations: dict | None = None,
            json_dump_kwds: dict | None = None,
            model_dump_kwds: dict | None = None,
    ) -> TextContent | EmbeddedResource:
        """
        Create a JSON response for MCP tools or resources.

        If data is not a dict, attempts to call .model_dump() and then json.dumps() on the data.

        NOTE: This does not handle things like already-serialized TextContent or tool call result lists.
        """
        json_dump_kwds = json_dump_kwds or {"indent": 0, "default": str}
        model_dump_kwds = model_dump_kwds or {}

        model_dump_kwds.setdefault("mode", "json")

        if isinstance(data, dict):
            json_dump_kwds.setdefault("indent", None)
            json_dump_kwds.setdefault("default", str)

            json_data = json.dumps(data, **json_dump_kwds)

        else:
            try:
                json_data = json.dumps(data.model_dump(**model_dump_kwds), **json_dump_kwds)
            except AttributeError:
                json_data = json.dumps(data, **json_dump_kwds)

        annotations = Annotations(**annotations) if annotations else None

        if embed_uri:
            return EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri=AnyUrl(embed_uri),
                    mimeType="application/json",
                    text=json_data,
                ),
                annotations=annotations,
            )

        else:
            if not annotations:
                annotations = Annotations()

            if not hasattr(annotations, "mimeType"):
                annotations.mimeType = "application/json"

            return TextContent(
                type="text",
                text=json_data,
                annotations=annotations,
            )
