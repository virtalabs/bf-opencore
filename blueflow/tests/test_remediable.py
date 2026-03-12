"""Remediable value tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

# import pytest
import json

import blueflow.models as bf_mod


def test_create_risk_factor_rem(admin_client):
    """Test that the Risk Factor API accepts the user_remediable flag"""
    params = {
        "name": "My Factor",
        "shortname": "my_factor",
        "factor_type": "cli",
        "weight": 0,
        "range_min": 0,
        "range_max": 1,
        "default_value": 0,
        "user_editable": False,
        "options": [],
        "user_remediable": "True",
    }
    resp = admin_client.post(
        "/api/riskfactors/", json.dumps(params), content_type="application/json"
    )
    assert resp.status_code == 201


def test_create_risk_factor_no_rem(admin_client):
    """Test that the Risk Factor API does not require user_remediable"""
    # Note - this is a duplicate of test_risk_factors.py's
    # test_create_risk_factor
    # We're only keeping it here for verbosity,
    # so that it might be clearer to the user why
    # this test may have failed
    params = {
        "name": "My Factor",
        "shortname": "my_factor",
        "factor_type": "cli",
        "weight": 0,
        "range_min": 0,
        "range_max": 1,
        "default_value": 0,
        "user_editable": False,
        "options": [],
    }
    resp = admin_client.post(
        "/api/riskfactors/", json.dumps(params), content_type="application/json"
    )
    assert resp.status_code == 201


def test_create_risk_factor_rem_override(admin_client):
    """Test that the remediable API endpoint accepts user_remediable"""
    asset = bf_mod.Asset.objects.create(name="spam")

    rf = bf_mod.RiskFactor.objects.create(
        name="Dummy",
        weight=0.5,
        range_min=0,
        range_max=100,
        user_editable=False,
        default_value=0,
    )
    params = {
        "user_remediable": "True",
        "asset_id": asset.id,
        "risk_factor_id": rf.id,
    }
    resp = admin_client.post(
        "/api/assetriskfactorremediables/",
        json.dumps(params),
        content_type="application/json",
    )
    assert resp.status_code == 201


def test_create_risk_factor_rem_override_no_rem(admin_client):
    """Test that the remediable API endpoint doesn't require user_remediable"""
    asset = bf_mod.Asset.objects.create(name="spam")

    rf = bf_mod.RiskFactor.objects.create(
        name="Dummy",
        weight=0.5,
        range_min=0,
        range_max=100,
        user_editable=False,
        default_value=0,
    )
    params = {
        "asset_id": asset.id,
        "risk_factor_id": rf.id,
    }
    resp = admin_client.post(
        "/api/assetriskfactorremediables/",
        json.dumps(params),
        content_type="application/json",
    )
    assert resp.status_code == 201


def test_create_risk_factor_rem_override_bad_rem(admin_client):
    """Test that the remediable API endpoint doesn't accept bad vals"""
    asset = bf_mod.Asset.objects.create(name="spam")

    rf = bf_mod.RiskFactor.objects.create(
        name="Dummy",
        weight=0.5,
        range_min=0,
        range_max=100,
        user_editable=False,
        default_value=0,
    )
    params = {
        "user_remediable": "Foo",
        "asset_id": asset.id,
        "risk_factor_id": rf.id,
    }
    resp = admin_client.post(
        "/api/assetriskfactorremediables/",
        json.dumps(params),
        content_type="application/json",
    )
    assert resp.status_code == 400
