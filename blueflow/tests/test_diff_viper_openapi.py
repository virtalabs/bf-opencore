"""Tests for Viper OpenAPI drift classification."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from blueflow.contracts.diff_viper_openapi import diff_viper_openapi, slice_for_operation

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIPER_FIXTURES = _REPO_ROOT / "contracts" / "fixtures" / "viper"


def test_diff_skips_when_baseline_missing(tmp_path, capsys) -> None:
    live = tmp_path / "live.json"
    live.write_text("{}", encoding="utf-8")
    baseline = tmp_path / "missing.json"

    assert diff_viper_openapi(baseline=baseline, live=live) == 0
    assert "seeding from live fetch" in capsys.readouterr().out


def test_slice_openapi_for_operation_keeps_matching_path_only() -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/integration": {
                "post": {"operationId": "integrationUpload", "responses": {"200": {}}}
            },
            "/other": {"get": {"operationId": "otherOp", "responses": {"200": {}}}},
        },
    }
    sliced = slice_for_operation(spec, "integrationUpload")
    assert list(sliced["paths"]) == ["/integration"]
    assert "post" in sliced["paths"]["/integration"]
    assert "get" not in sliced["paths"]["/integration"]


def test_diff_returns_zero_when_no_breaking_changes(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    spec = json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "paths": {
                "/integration": {
                    "post": {"operationId": "integrationUpload", "responses": {}}
                }
            },
        }
    )
    baseline.write_text(spec, encoding="utf-8")
    live.write_text(spec, encoding="utf-8")

    ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch(
        "blueflow.contracts.diff_viper_openapi.subprocess.run", return_value=ok
    ) as mock_run:
        assert (
            diff_viper_openapi(
                baseline=baseline,
                live=live,
                operation="integrationUpload",
                oasdiff="/usr/bin/oasdiff",
            )
            == 0
        )
    assert mock_run.call_count == 2
    breaking_call = mock_run.call_args_list[0].args[0]
    assert breaking_call[:3] == ["/usr/bin/oasdiff", "breaking", breaking_call[2]]
    assert breaking_call[2].endswith("baseline.json")
    assert "--fail-on" in breaking_call
    assert "ERR" in breaking_call


def test_diff_returns_one_when_breaking_changes(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    baseline.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/integration": {
                        "post": {"operationId": "integrationUpload", "responses": {}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    live.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/integration": {
                        "post": {"operationId": "integrationUpload", "responses": {}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    breaking = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="required property 'foo' added\n",
        stderr="",
    )
    with patch(
        "blueflow.contracts.diff_viper_openapi.subprocess.run", return_value=breaking
    ):
        assert (
            diff_viper_openapi(
                baseline=baseline,
                live=live,
                operation="integrationUpload",
                oasdiff="/usr/bin/oasdiff",
            )
            == 1
        )
    assert "Breaking Viper OpenAPI changes" in capsys.readouterr().err


def test_diff_returns_two_on_malformed_baseline_json(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    baseline.write_text("{not json", encoding="utf-8")
    live.write_text('{"openapi":"3.0.0","paths":{}}', encoding="utf-8")
    assert diff_viper_openapi(baseline=baseline, live=live) == 2


def test_diff_returns_two_when_oasdiff_missing(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    spec = json.dumps(
        {
            "openapi": "3.0.0",
            "paths": {
                "/integration": {
                    "post": {"operationId": "integrationUpload", "responses": {}}
                }
            },
        }
    )
    baseline.write_text(spec, encoding="utf-8")
    live.write_text(spec, encoding="utf-8")

    with patch(
        "blueflow.contracts.diff_viper_openapi.subprocess.run",
        side_effect=FileNotFoundError(2, "No such file"),
    ):
        assert (
            diff_viper_openapi(
                baseline=baseline,
                live=live,
                operation="integrationUpload",
                oasdiff="/nonexistent/oasdiff",
            )
            == 2
        )


@pytest.mark.integration
def test_diff_integration_with_oasdiff_binary() -> None:
    if shutil.which("oasdiff") is None:
        pytest.skip("oasdiff not installed")

    baseline = _VIPER_FIXTURES / "baseline_openapi.json"
    live = _VIPER_FIXTURES / "live_breaking_openapi.json"

    assert diff_viper_openapi(baseline=baseline, live=live, operation="integrationUpload") == 1
