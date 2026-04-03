"""Test custom fields.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import json

import pytest
from django.db import IntegrityError
from django.db.transaction import TransactionManagementError

from blueflow import models


def test_custom_field_api(cleandb, auth_client):
    """Test get custom fields."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    custom_field_name = models.AssetCustomFieldName.objects.create(field_name="red")
    _ = models.AssetCustomField.objects.create(
        field=custom_field_name, asset=asset_obj, value_text="foovalue"
    )
    asset_custom_field = auth_client.get("/api/assetcustomfields/").json()
    assert asset_custom_field["count"] == 1
    results = asset_custom_field["results"]
    assert len(results) == 1
    assert results[0]["value_text"] == "foovalue"


def test_custom_field_via_model(cleandb, auth_client):
    """Test get Custom fields associated with one asset."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    assert hasattr(asset_obj, "custom_fields")  # The list of field names
    assert hasattr(asset_obj, "asset_custom_fields")  # The list of fields
    asset = auth_client.get(f"/api/assets/{asset_obj.id}/").json()
    assert asset["hostname"] == "foo.com"
    assert asset["asset_custom_fields"] == []  # This fails (no such field)

    custom_field_name = models.AssetCustomFieldName.objects.create(field_name="red")
    asset_custom_field = models.AssetCustomField.objects.create(
        field=custom_field_name, asset=asset_obj
    )
    assert list(asset_obj.asset_custom_fields.all()) == [asset_custom_field]

    asset = auth_client.get(f"/api/assets/{asset_obj.id}/").json()
    assert len(asset["asset_custom_fields"]) == 1
    assert asset["asset_custom_fields"][0]["field"]["id"] == custom_field_name.id


################################################################
# Custom fields ("values")


@pytest.mark.skip(reason="This route isn't implemented (and won't be)")
def test_api_add_custom_field_via_asset(cleandb, auth_client, admin_client):
    """Add custom fields via asset API.

    Not implemented (and probably won't be).
    """
    asset_id = models.Asset.objects.create(hostname="foo.com").id
    custom_fn_id = models.AssetCustomFieldName.objects.create(
        field_name="sparkliness"
    ).id
    kwargs = {
        "data": json.dumps({"field_id": custom_fn_id, "value_text": "very sparkly"}),
        "content_type": "application/json",
    }
    # NOTE: need admin client to add fields
    res = admin_client.post(f"/api/assets/{asset_id}/customfields/", **kwargs)
    assert res.status_code == 201
    # Assert above FAILS with 404 (no such route)
    af = auth_client.get("/api/assetcustomfields/").json()
    assert af["count"] == 1
    assert len(af["results"]) == 1
    assert af["results"][0]["asset_id"] == asset_id
    assert af["results"][0]["field"]["field_name"] == "sparkliness"


def test_api_add_custom_field(cleandb, auth_client, admin_client):
    """Add custom fields via API."""
    asset_id = models.Asset.objects.create(hostname="foo.com").id
    custom_fn_id = models.AssetCustomFieldName.objects.create(
        field_name="sparkliness"
    ).id
    kwargs = {
        "data": json.dumps(
            {
                "field_id": custom_fn_id,
                "asset_id": asset_id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    # NOTE: need admin client to add fields
    res = admin_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 201
    # Assert above FAILS (API wants 'field', not 'field_id')
    af = auth_client.get("/api/assetcustomfields/").json()
    assert af["count"] == 1
    assert len(af["results"]) == 1
    assert af["results"][0]["asset_id"] == asset_id
    assert af["results"][0]["field"]["field_name"] == "sparkliness"


def test_api_change_custom_field(cleandb, auth_client, admin_client):
    """Add custom fields via API."""
    asset_id = models.Asset.objects.create(hostname="foo.com").id
    custom_fn_id = models.AssetCustomFieldName.objects.create(
        field_name="sparkliness"
    ).id
    kwargs = {
        "data": json.dumps(
            {
                "field_id": custom_fn_id,
                "asset_id": asset_id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    # NOTE: need admin client to add fields
    res = admin_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 201
    res = auth_client.get("/api/assetcustomfields/").json()
    assert len(res["results"]) == 1
    custom_field = res["results"][0]
    assert custom_field["asset_id"] == asset_id
    assert custom_field["value_text"] == "very sparkly"
    # In order to *change* a value we need to know the ID and submit a patch.
    kwargs["data"] = json.dumps({"value_text": "not sparkly at all"})
    res = admin_client.patch(
        "/api/assetcustomfields/{}/".format(custom_field["id"]), **kwargs
    )
    assert res.status_code == 200
    res = auth_client.get("/api/assetcustomfields/").json()
    assert res["results"][0]["value_text"] == "not sparkly at all"


def test_api_delete_custom_field(cleandb, auth_client, admin_client):
    """Add custom fields via API."""
    asset_id = models.Asset.objects.create(hostname="foo.com").id
    custom_fn_id = models.AssetCustomFieldName.objects.create(
        field_name="sparkliness"
    ).id
    kwargs = {
        "data": json.dumps(
            {
                "field_id": custom_fn_id,
                "asset_id": asset_id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    # NOTE: need admin client to add fields
    res = admin_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 201
    res = auth_client.get("/api/assetcustomfields/").json()
    assert len(res["results"]) == 1
    custom_field = res["results"][0]
    assert custom_field["asset_id"] == asset_id
    assert custom_field["value_text"] == "very sparkly"
    # In order to "null" a value we need to know the ID and submit delete.
    kwargs["data"] = json.dumps({"value_text": None})
    res = admin_client.delete("/api/assetcustomfields/{}/".format(custom_field["id"]))
    assert res.status_code == 204
    res = auth_client.get("/api/assetcustomfields/").json()
    assert len(res["results"]) == 0


def test_api_asset_custom_field(cleandb, auth_client, admin_client):
    """View custom fields arriving with the asset."""
    asset_id = models.Asset.objects.create(hostname="foo.com").id
    kwargs = {
        "data": json.dumps({"field_name": "sparkliness"}),
        "content_type": "application/json",
    }
    res = admin_client.post("/api/assetcustomfieldnames/", **kwargs)
    afn = res.json()
    asset = auth_client.get(f"/api/assets/{asset_id}/").json()
    assert asset["hostname"] == "foo.com"
    assert len(asset["asset_custom_fields"]) == 0
    assert asset["asset_custom_fields"] == []
    kwargs["data"] = json.dumps(
        {"field_id": afn["id"], "asset_id": asset_id, "value_text": "very sparkly"}
    )
    _ = admin_client.post("/api/assetcustomfields/", **kwargs)
    asset = auth_client.get(f"/api/assets/{asset_id}/").json()
    assert asset["hostname"] == "foo.com"
    assert len(asset["asset_custom_fields"]) == 1
    custom_field = asset["asset_custom_fields"][0]
    assert custom_field["field"]["field_name"] == "sparkliness"
    assert custom_field["value_text"] == "very sparkly"


def test_custom_field(cfield, auth_client):
    """Sanity check."""
    assert cfield.asset.hostname == "foo.com"
    assert cfield.shiny_field.field_name == "shinyness"
    assert cfield.custom_field.value_text == "rather dull"
    asset_custom_field = auth_client.get("/api/assetcustomfields/").json()
    assert asset_custom_field["count"] == 1
    results = asset_custom_field["results"]
    assert len(results) == 1
    assert results[0]["value_text"] == "rather dull"
    assert results[0]["field"]["id"] == cfield.shiny_field.id


@pytest.mark.xfail(
    raises=(IntegrityError, TransactionManagementError),
    reason=(
        "Posting duplicate field value raises IntegrityError;"
        " may cause TransactionManagementError"
    ),
)
def test_api_admin_post_existing(cfield, admin_client):
    """Posting a field value that already exists should fail with 405

    Instead it fails with IntegrityError (for now.)
    """
    kwargs = {
        "data": json.dumps(
            {
                "field_id": cfield.shiny_field.id,
                "asset_id": cfield.asset.id,
                "value_text": "very shiny",
            }
        ),
        "content_type": "application/json",
    }
    res = admin_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 405


################################################################
# Test post with different users


@pytest.mark.xfail(reason="Blueflow has no role-based write permissions")
def test_api_field_unauthorized_post(cfield, auth_client):
    kwargs = {
        "data": json.dumps(
            {
                "field_id": cfield.sparkly_field.id,
                "asset_id": cfield.asset.id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    res = auth_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 403


def test_api_field_authorized_post(cfield, asset_edit_client):
    kwargs = {
        "data": json.dumps(
            {
                "field_id": cfield.sparkly_field.id,
                "asset_id": cfield.asset.id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    res = asset_edit_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 201


def test_api_field_admin_post(cfield, admin_client):
    kwargs = {
        "data": json.dumps(
            {
                "field_id": cfield.sparkly_field.id,
                "asset_id": cfield.asset.id,
                "value_text": "very sparkly",
            }
        ),
        "content_type": "application/json",
    }
    res = admin_client.post("/api/assetcustomfields/", **kwargs)
    assert res.status_code == 201


################################################################
# Test patch with different users


@pytest.mark.xfail(reason="Blueflow has no role-based write permissions")
def test_api_field_unauthorized_patch(cfield, auth_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = auth_client.patch(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 403


def test_api_field_authorized_patch(cfield, asset_edit_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = asset_edit_client.patch(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 200


def test_api_field_admin_patch(cfield, admin_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = admin_client.patch(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 200


################################################################
# Test delete with different users


@pytest.mark.xfail(reason="Blueflow has no role-based write permissions")
def test_api_field_unauthorized_delete(cfield, auth_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = auth_client.delete(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 403


def test_api_field_authorized_delete(cfield, asset_edit_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = asset_edit_client.delete(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 204


def test_api_field_admin_delete(cfield, admin_client):
    cfield_id = cfield.custom_field.id
    kwargs = {
        "data": json.dumps({"value_text": "very shiny"}),
        "content_type": "application/json",
    }
    res = admin_client.delete(f"/api/assetcustomfields/{cfield_id}/", **kwargs)
    assert res.status_code == 204
