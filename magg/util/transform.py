"""Transformation utilities for MCP results.
"""
import base64
from typing import TypeAlias

from mcp import GetPromptResult
from mcp.types import (
    TextContent, ImageContent, EmbeddedResource,
    TextResourceContents, BlobResourceContents, Annotations, Content
)
import json

from pydantic import AnyUrl, ValidationError, BaseModel, TypeAdapter

__all__ = (
    "ToolResult", "ResourceResult", "PromptResult", "ClientMCPResult",
    "is_mcp_result_json_typed", "extract_mcp_result_json",
    "embed_python_object_in_resource", "get_embedded_resource_python_object",
    "resource_result_as_tool_result", "tool_result_as_resource_result",
    "prompt_result_as_tool_result", "tool_result_as_prompt_result",
    "annotate_content", "deserialize_embedded_resource_python_object",
    "embed_python_object_list_in_resource", "get_mcp_result_contents",
)


ToolResult: TypeAlias = TextContent | ImageContent | EmbeddedResource
ResourceResult: TypeAlias = TextResourceContents | BlobResourceContents
PromptResult: TypeAlias = GetPromptResult
ClientMCPResult: TypeAlias = ToolResult | ResourceResult | PromptResult


def get_mcp_result_contents(
    data: ClientMCPResult,
) -> str | bytes | None:
    """
    Get the raw content from a MCP tool or resource result item.

    Args:
        data: The MCP tool or resource result item.

    Returns:
        str | bytes | None: The raw content if available, otherwise None.
    """
    if isinstance(data, TextContent):
        return data.text

    if isinstance(data, EmbeddedResource):
        data = data.resource

    if isinstance(data, (TextResourceContents, BlobResourceContents)):
        return data.text if hasattr(data, 'text') else base64.b64decode(data.blob)

    return None

def is_mcp_result_json_typed(
    data: ClientMCPResult,
) -> bool:
    """
    Check whether the MCP tool or resource result item data is a JSON-typed object
    by looking at mimeType fields or annotations.
    """

    if isinstance(data, TextContent):
        return data.annotations and getattr(data.annotations, "mimeType", None) == "application/json"

    if isinstance(data, EmbeddedResource):
        if data.annotations and getattr(data.annotations, "mimeType", None) == "application/json":
            return True
        else:
            data = data.resource

    if isinstance(data, (TextResourceContents, BlobResourceContents)):
        return data.mimeType == "application/json"

    return False


def extract_mcp_result_json(
        data: ClientMCPResult,
) -> str | None:
    """
    Extract a RAW JSON string from the MCP tool or resource result item.

    Args:
        data: The MCP tool or resource result item.

    Returns:
        str | None: The extracted raw JSON string if available, otherwise None.
    """
    if not is_mcp_result_json_typed(data):
        return None

    if hasattr(data, 'text'):
        return data.text

    elif hasattr(data, 'resource') and hasattr(data.resource, 'text'):
        return data.resource.text

    return None


def embed_python_object_in_resource(
    obj: BaseModel,
    uri: AnyUrl | str,
    **annotations,
) -> EmbeddedResource:
    # noinspection PyArgumentList
    annotations = Annotations(
        pythonType=type(obj).__name__,
        **annotations,
    )

    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri=uri,
            text=json.dumps(obj.model_dump(mode="json"), indent=0, default=str),
            mimeType="application/json",
        ),
        annotations=annotations,
    )


def embed_python_object_list_in_resource(
    typ: type[BaseModel],
    obj: list[BaseModel],
    uri: AnyUrl | str,
    **annotations,
) -> EmbeddedResource:
    # noinspection PyArgumentList
    annotations = Annotations(
        pythonType=getattr(typ, "__name__", str(typ)),  # Union types may not have __name__
        many=True,
        **annotations,
    )

    adapter = TypeAdapter(list[typ])
    encoded = adapter.dump_json(obj, indent=0).decode("utf-8")

    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri=uri,
            text=encoded,
            mimeType="application/json",
        ),
        annotations=annotations,
    )


def get_embedded_resource_python_object(
    data: EmbeddedResource,
        **check: str | None
) -> tuple[str, str, bool] | None:
    """
    Check if the embedded resource has a Python type annotation and JSON data, and return them.

    Args:
        data: The embedded resource with annotations field.
        check: Optional keyword arguments to filter annotations on.

    Returns:
        tuple[str, str, bool] | None: When available, a tuple containing the Python type,
                                      raw JSON string, and a boolean indicating if it is a list.
    """
    object_info = None

    if (
        isinstance(data, EmbeddedResource) and
        data.annotations and getattr(data.annotations, "pythonType", None) and
        is_mcp_result_json_typed(data) and all(
            getattr(data.annotations, key, None) == value for key, value in check.items()
        )
    ):
        python_type = data.annotations.pythonType
        json_data = extract_mcp_result_json(data)
        many = getattr(data.annotations, "many", False)

        if json_data is not None:
            object_info = (python_type, json_data, many)

    return object_info


def deserialize_embedded_resource_python_object[T: BaseModel](
        target_type: type[BaseModel],
        python_type: str,
        json_data: str,
        *,
        many: bool = False,
) -> T | list[T] | None:

    if not target_type or not python_type or not json_data:
        return None

    target_type_name = getattr(target_type, "__name__", str(target_type))

    if target_type_name != python_type:
        return None

    if many:
        target_type = TypeAdapter(list[target_type])
        return target_type.validate_json(json_data)

    if hasattr(target_type, "model_validate_json"):
        return target_type.model_validate_json(json_data)

    else:
        target_type = TypeAdapter(target_type)
        return target_type.validate_json(json_data)


def resource_result_as_tool_result(
        data: ResourceResult,
        as_json: bool | None = None,
        encoder: json.JSONEncoder | None = None,
        decoder: json.JSONDecoder | None = None,
        **annotations,
) -> EmbeddedResource:
    """
    Converts resource result data into a tool result format.

    This function processes a given resource result, which can be either text or
    binary (blob) content, and re-formats the data into a tool result. It provides
    optional formatting of the result as JSON when specified.

    Args:
        data: The resource content, which can be an instance of TextResourceContents
            or BlobResourceContents.
        as_json: An optional flag indicating whether to format TextResourceContents as JSON.
            Defaults to None, which will auto-detect JSON and set the mimeType accordingly.
        encoder: An optional JSON encoder to use for serializing the content. If not provided,
            the default JSON encoder will be used.
        decoder: An optional JSON decoder to use for deserializing the content. If not provided,
            the default JSON decoder will be used.
        **annotations: Additional annotations to include in the result.
    """
    if not isinstance(data, (TextResourceContents, BlobResourceContents)):
        raise TypeError("Data must be TextResourceContents or BlobResourceContents")

    resource_data = data

    if isinstance(data, TextResourceContents) and data.mimeType != "application/json":
        encoder = encoder or json.JSONEncoder(indent=0, ensure_ascii=False)
        decoder = decoder or json.JSONDecoder()
        json_data = None

        if as_json in {True, None}:
            try:
                json_data = decoder.decode(data.text)
                as_json = True
            except json.JSONDecodeError:
                as_json = False

        if as_json:
            resource_data = TextResourceContents(
                uri=data.uri,
                text=encoder.encode(json_data),
                mimeType="application/json",
                contentType=data.mimeType,  # type: ignore # class has extra=allow
            )

    annotations.setdefault("proxyType", "resource")
    annotations = Annotations(**annotations) if annotations else None

    return EmbeddedResource(
        type="resource",
        resource=resource_data,
        annotations=annotations,
    )


def tool_result_as_resource_result(
        data: ToolResult,
) -> ResourceResult | None:
    """
    Extracts a resource result from a tool result when available.

    Args:
        data: The tool result, which will be an EmbeddedResource when it contains a resource.

    Returns:
        ResourceResult | None: The original resource result, or None if the data is not a resource result.
    """
    if isinstance(data, EmbeddedResource):
        if (
            getattr(data.annotations, "proxyType", None) == "resource" and
            data.resource and
            isinstance(data.resource, (TextResourceContents, BlobResourceContents))
        ):
            return data.resource

    return None


def prompt_result_as_tool_result(
        data: PromptResult,
        name: str,
        **annotations,
) -> EmbeddedResource:
    """
    Converts a GetPromptResult into a tool result format.

    Specifically, this creates an EmbeddedResource containing a JSON dump of the GetPromptResult.

    The Python type is set in the annotations to `type(mcp.GetPromptResult).__name__`.

    Args:
        data: The GetPromptResult instance to convert.
        name: The name of the prompt, or any URI-compatible string to use as the resource URI.
        annotations: Additional annotations to include in the result.
    """
    try:
        uri = AnyUrl(name)
    except ValidationError:
        uri = AnyUrl(f"urn:prompt:{name}")

    annotations.setdefault("proxyType", "prompt")

    return embed_python_object_in_resource(
        obj=data,
        uri=uri,
        **annotations,
    )


def tool_result_as_prompt_result(
        data: ToolResult,
) -> PromptResult | None:
    """
    Extracts a prompt call result from a tool result when available.

    Args:
        data: The tool result, which can be TextContent, ImageContent, or EmbeddedResource.

    Returns:
        GetPromptResult | None: The original prompt call result, or None if the data is not a prompt result.
    """
    if object_info := get_embedded_resource_python_object(data, proxyType="prompt"):
        python_type, json_data, many = object_info

        return deserialize_embedded_resource_python_object(
            target_type=GetPromptResult,
            python_type=python_type,
            json_data=json_data,
            many=many,
        )

    return None


def annotate_content(
        data: Content,
        **annotations,
) -> Content:
    """
    Annotate Content with additional annotations.

    Args:
        data: The Content to annotate.
        **annotations: Additional annotations to add.

    Returns:
        Content: The annotated Content.
    """
    if annotations:
        if data.annotations is None:
            data.annotations = Annotations(**annotations)
        else:
            for key, value in annotations.items():
                setattr(data.annotations, key, value)

    return data
