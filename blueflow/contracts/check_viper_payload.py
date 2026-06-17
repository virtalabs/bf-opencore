"""Consumer-side Viper payload validation against a live OpenAPI spec."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import RefResolver


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_integration_upload_schema(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON Schema for a single integrationUpload page item."""
    paths = spec.get("paths", {})
    for path_item in paths.values():
        for method in ("post", "put", "patch"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId", "")
            if op_id == "integrationUpload" or "integration" in op_id.lower():
                request_body = operation.get("requestBody", {})
                content = request_body.get("content", {})
                media = content.get("application/json", {})
                schema = media.get("schema")
                if isinstance(schema, dict):
                    if "$ref" in schema:
                        return _resolve_ref(spec, schema["$ref"])
                    items = schema.get("properties", {}).get("items", {})
                    if "$ref" in items:
                        return _resolve_ref(spec, items["$ref"])
                    item_items = items.get("items")
                    if isinstance(item_items, dict):
                        if "$ref" in item_items:
                            return _resolve_ref(spec, item_items["$ref"])
                        return item_items
                    return schema
    msg = "integrationUpload request item schema not found in OpenAPI spec"
    raise ValueError(msg)


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        msg = f"Unsupported $ref (expected local): {ref}"
        raise ValueError(msg)
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    if not isinstance(node, dict):
        msg = f"$ref did not resolve to an object: {ref}"
        raise TypeError(msg)
    return node


def validate_viper_sample(*, spec: dict[str, Any], sample: dict[str, Any]) -> None:
    """Validate each item in a Viper page body against the integrationUpload schema."""
    item_schema = _find_integration_upload_schema(spec)
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
