"""Consumer-side Viper payload validation against a live OpenAPI spec."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import RefResolver

_HTTP_METHODS = ("post", "put", "patch")
_DEFAULT_OPERATION_ID = "integrationUpload"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        msg = f"Unsupported $ref (expected local): {ref}"
        raise ValueError(msg)
    node: Any = spec
    try:
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
    except KeyError as exc:
        msg = f"$ref path not found: {ref}"
        raise ValueError(msg) from exc
    if not isinstance(node, dict):
        msg = f"$ref did not resolve to an object: {ref}"
        raise TypeError(msg)
    return node


def _resolve_schema_node(
    spec: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    if "$ref" in schema:
        return _resolve_ref(spec, schema["$ref"])
    return schema


def _item_schema_from_request_schema(
    spec: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Unwrap a request body schema to the JSON Schema for one page item."""
    resolved = _resolve_schema_node(spec, schema)
    items_prop = resolved.get("properties", {}).get("items")
    if not isinstance(items_prop, dict):
        return resolved

    if "$ref" in items_prop:
        items_prop = _resolve_ref(spec, items_prop["$ref"])

    nested = items_prop.get("items")
    if isinstance(nested, dict):
        return _resolve_schema_node(spec, nested)

    return resolved


def _find_operation(spec: dict[str, Any], operation_id: str) -> dict[str, Any]:
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if (
                isinstance(operation, dict)
                and operation.get("operationId") == operation_id
            ):
                return operation
    msg = f"operationId {operation_id!r} not found in OpenAPI paths"
    raise ValueError(msg)


def find_integration_upload_item_schema(
    spec: dict[str, Any],
    operation_id: str = _DEFAULT_OPERATION_ID,
) -> dict[str, Any]:
    """Return the JSON Schema for a single integrationUpload page item."""
    operation = _find_operation(spec, operation_id)
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    media = content.get("application/json", {})
    schema = media.get("schema")
    if not isinstance(schema, dict):
        msg = f"{operation_id} request body schema not found in OpenAPI spec"
        raise TypeError(msg)
    return _item_schema_from_request_schema(spec, schema)


def validate_viper_sample(
    *,
    spec: dict[str, Any],
    sample: dict[str, Any],
    operation_id: str = _DEFAULT_OPERATION_ID,
) -> None:
    """Validate each item in a Viper page body against the integrationUpload schema."""
    item_schema = find_integration_upload_item_schema(spec, operation_id)
    resolver = RefResolver.from_schema(spec)
    items = sample.get("items", [])
    if not items:
        msg = "Sample payload has no items"
        raise ValueError(msg)
    for item in items:
        jsonschema.validate(instance=item, schema=item_schema, resolver=resolver)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Viper integrationUpload page body against an OpenAPI spec"
        )
    )
    parser.add_argument("--spec", required=True, type=Path, help="Path to openapi.json")
    parser.add_argument(
        "--sample", required=True, type=Path, help="Path to emitted page body JSON"
    )
    args = parser.parse_args(argv)
    spec = _load_json(args.spec)
    sample = _load_json(args.sample)
    try:
        validate_viper_sample(spec=spec, sample=sample)
    except (jsonschema.ValidationError, ValueError, TypeError) as exc:
        sys.stderr.write(f"Contract validation failed: {exc}\n")
        return 1
    sys.stdout.write("Contract validation passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
