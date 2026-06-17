"""Contract: Viper integrationUpload payload validation against OpenAPI specs."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from blueflow.contracts.check_viper_payload import validate_viper_sample

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
