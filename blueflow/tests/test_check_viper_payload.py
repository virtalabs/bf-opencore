"""Contract: Viper integrationUpload payload validation against OpenAPI specs."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from django.core.management import call_command

from blueflow.contracts.check_viper_payload import (
    find_integration_upload_item_schema,
    main as check_viper_payload_main,
    validate_viper_sample,
)

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIPER_FIXTURES = _REPO_ROOT / "contracts" / "fixtures" / "viper"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_validate_viper_sample_passes_against_baseline_spec() -> None:
    spec = _load_json(_VIPER_FIXTURES / "baseline_openapi.json")
    sample = _load_json(_VIPER_FIXTURES / "sample_page.json")
    validate_viper_sample(spec=spec, sample=sample)


def test_validate_viper_sample_fails_when_required_field_added() -> None:
    spec = _load_json(_VIPER_FIXTURES / "live_breaking_openapi.json")
    sample = _load_json(_VIPER_FIXTURES / "sample_page.json")
    with pytest.raises(jsonschema.ValidationError):
        validate_viper_sample(spec=spec, sample=sample)


def test_page_ref_unwrap_resolves_item_schema() -> None:
    spec = _load_json(_VIPER_FIXTURES / "verify_openapi.json")
    item_schema = find_integration_upload_item_schema(spec)
    assert item_schema.get("required") == [
        "ip",
        "upstreamApi",
        "vendorId",
        "status",
        "utilization",
    ]
    assert "macAddress" in item_schema.get("properties", {})


def test_find_integration_upload_item_schema_unknown_operation_raises() -> None:
    spec = _load_json(_VIPER_FIXTURES / "baseline_openapi.json")
    with pytest.raises(ValueError, match="operationId 'missingOp' not found"):
        find_integration_upload_item_schema(spec, operation_id="missingOp")


def test_validate_viper_sample_fails_on_missing_required_item_field() -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/integration": {
                "post": {
                    "operationId": "integrationUpload",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["ip"],
                                    "properties": {"ip": {"type": "string"}},
                                }
                            }
                        }
                    },
                }
            }
        },
    }
    sample = _load_json(_VIPER_FIXTURES / "sample_page_missing_field.json")
    with pytest.raises(jsonschema.ValidationError):
        validate_viper_sample(spec=spec, sample=sample)


def test_emit_viper_sample_validates_against_verify_fixture(tmp_path) -> None:
    output = tmp_path / "sample.json"
    call_command("emit_viper_sample", output=str(output))
    spec = _load_json(_VIPER_FIXTURES / "verify_openapi.json")
    sample = _load_json(output)
    validate_viper_sample(spec=spec, sample=sample)


def test_check_viper_payload_main_malformed_spec_json(tmp_path) -> None:
    bad_spec = tmp_path / "bad.json"
    sample = tmp_path / "sample.json"
    bad_spec.write_text("{not json", encoding="utf-8")
    sample.write_text('{"items": [{"ip": "10.0.0.1"}]}', encoding="utf-8")
    assert (
        check_viper_payload_main(
            ["--spec", str(bad_spec), "--sample", str(sample)]
        )
        == 1
    )


def test_check_viper_payload_main_invalid_ref(tmp_path) -> None:
    spec = tmp_path / "spec.json"
    sample = tmp_path / "sample.json"
    spec.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/integration": {
                        "post": {
                            "operationId": "integrationUpload",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Missing"
                                        }
                                    }
                                }
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    sample.write_text('{"items": [{"ip": "10.0.0.1"}]}', encoding="utf-8")
    assert (
        check_viper_payload_main(
            ["--spec", str(spec), "--sample", str(sample)]
        )
        == 1
    )
