"""Test attachments."""

import io
import json
import urllib

import pytest
from django.conf import settings as django_settings

from bf_opencore import models


def qparam(pardict):
    """Get query params as string based on dictionary."""
    return urllib.parse.urlencode(pardict)


# Many functions use Model classes which *do* have an 'objects' member


def test_upload_bad(asset_edit_client, media_root):
    """Upload that doesn't contain a file."""
    resp = asset_edit_client.post(
        "/api/attachments/", json.dumps({"foo": "bar"}), content_type="application/json"
    )
    assert resp.status_code == 400
    assert str(resp.data["file"][0]) == "No file was submitted."


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param("file_only", id="file_only"),
        pytest.param("with_manufacturer", id="with_manufacturer"),
        pytest.param("with_model", id="with_model"),
        pytest.param("with_asset", id="with_asset"),
        pytest.param("with_name", id="with_name"),
    ],
)
def test_upload_variants(asset_edit_client, media_root, variant):
    """Upload with different body options; assert response matches expected fields."""
    body = {"file": io.BytesIO(b"bar")}
    if variant == "with_manufacturer":
        body["manufacturer"] = "ACME, Inc."
    elif variant == "with_model":
        body["manufacturer"] = "ACME, Inc."
        body["model"] = "Instant Tunnel"
    elif variant == "with_asset":
        asset = models.Asset.objects.create()
        body["asset_id"] = asset.id
    elif variant == "with_name":
        body["name"] = "Descriptive"

    resp = asset_edit_client.post("/api/attachments/", body)
    assert resp.status_code == 201
    assert int(attachment["id"]) > 0

    if variant == "file_only":
        assert attachment.asset is None
        assert attachment.manufacturer is None
        assert attachment.model is None
        assert attachment.file_name == "file"
        assert attachment.size_bytes == len(b"bar")
        assert attachment.added_by == resp.wsgi_request.user.username
    elif variant == "with_manufacturer":
        assert attachment.asset is None
        assert attachment.manufacturer == "ACME, Inc."
        assert attachment.model is None
    elif variant == "with_model":
        assert attachment.asset is None
        assert attachment.manufacturer == "ACME, Inc."
        assert attachment.model == "Instant Tunnel"
    elif variant == "with_asset":
        assert attachment.asset_id == asset.id
        assert attachment.manufacturer is None
        assert attachment.model is None
    elif variant == "with_name":
        assert attachment.file_name == "file"
        assert attachment.name == "Descriptive"


def test_get_attachments(asset_edit_client, media_root):
    """Get the attachment object(s) we just uploaded (list)."""
    resp = asset_edit_client.post("/api/attachments/", {"file": io.BytesIO(b"bar")})
    assert resp.status_code == 201
    resp = asset_edit_client.get("/api/attachments/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert len(resp.data["results"]) == 1


def test_get_attachment(asset_edit_client, media_root):
    """Get the attachment object we just uploaded (detail)."""
    resp = asset_edit_client.post("/api/attachments/", {"file": io.BytesIO(b"bar")})
    assert resp.status_code == 201
    att_id = resp.data["id"]
    resp = asset_edit_client.get(f"/api/attachments/{att_id}/")
    assert resp.status_code == 200
    attachment = resp.data
    assert attachment["id"] == att_id


MEDIA_URL_PREFIX = f"http://testserver{django_settings.MEDIA_URL}attachments/"


@pytest.mark.parametrize(
    "endpoint_style",
    [
        pytest.param("detail", id="detail"),
        pytest.param("list", id="list"),
    ],
)
def test_get_attachment_file_url(asset_edit_client, media_root, endpoint_style):
    """Get the URL of attachment; assert it starts with MEDIA_URL_PREFIX.

    NOTE: The URL should always start with MEDIA_URL_PREFIX,
    whether fetched as detail or list.
    """
    resp = asset_edit_client.post("/api/attachments/", {"file": io.BytesIO(b"bar")})
    att_id = resp.data["id"]
    if endpoint_style == "detail":
        resp = asset_edit_client.get(f"/api/attachments/{att_id}/")
        attachment = resp.data
    else:
        resp = asset_edit_client.get("/api/attachments/")
        attachment = resp.data["results"][0]
    file = attachment["file"]
    assert file[: len(MEDIA_URL_PREFIX)] == MEDIA_URL_PREFIX


def test_delete_attachment(asset_edit_client, media_root):
    """Delete the attachment object we just uploaded (detail)."""
    resp = asset_edit_client.post("/api/attachments/", {"file": io.BytesIO(b"bar")})
    att_id = resp.data["id"]
    resp = asset_edit_client.delete(f"/api/attachments/{att_id}/")
    assert resp.status_code == 204
    resp = asset_edit_client.get("/api/attachments/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


@pytest.mark.xfail(raises=AssertionError)
def test_upload_attachment_no_manuf_no_mod(asset_edit_client, media_root):
    """Can't upload attachment without manufacturer nor model.

    NOTE: this currently fails; we *are* allowed to upload such
      attachments.  Moreover, whenever we implement safeguards so this
      one passes, many other tests will fail (since they rely on the
      current loophole.)
    """
    resp = asset_edit_client.post("/api/attachments/", {"file": io.BytesIO(b"bar")})
    assert resp.status_code == 403


@pytest.mark.xfail(raises=AssertionError)
def test_upload_attachment_no_manuf_yes_mod(asset_edit_client, media_root):
    """Can't upload attachment with model but without manufacturer.

    NOTE: this currently fails; we *are* allowed to upload such attachments.
    """
    resp = asset_edit_client.post(
        "/api/attachments/",
        {
            "file": io.BytesIO(b"bar"),
            "model": "Instant Tunnel",
        },
    )
    assert resp.status_code == 403


def test_get_attachment_manuf_model(asset_edit_client, media_root):
    """Get attachment based on manufacturer and model."""
    resp = asset_edit_client.post(
        "/api/attachments/",
        {
            "file": io.BytesIO(b"bar"),
            "manufacturer": "ACME, Inc.",
            "model": "Instant Tunnel",
        },
    )
    assert resp.status_code == 201
    resp = asset_edit_client.get(
        "/api/attachments/"
        "?"
        + qparam(
            {
                "manufacturer__iexact": "ACME, Inc.",
                "model__iexact": "Instant Tunnel",
            }
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 1


@pytest.mark.parametrize(
    "upload_manuf,upload_model,filter_params,expected_count",
    [
        pytest.param(
            "ACME, Inc.",
            "Instant Tunnel",
            {"manufacturer__iexact": "ACME, Inc.", "model__isnull": "true"},
            0,
            id="manuf_model_search_null",
        ),
        pytest.param(
            "ACME, Inc.",
            None,
            {"manufacturer__iexact": "ACME, Inc.", "model__iexact": "Instant Tunnel"},
            0,
            id="manuf_only_search_model",
        ),
        pytest.param(
            "ACME, Inc.",
            "Anvil",
            {"manufacturer__iexact": "ACME, Inc.", "model__iexact": "Instant Tunnel"},
            0,
            id="wrong_model",
        ),
    ],
)
def test_get_attachment_manuf_model_filters(
    asset_edit_client,
    media_root,
    upload_manuf,
    upload_model,
    filter_params,
    expected_count,
):
    """Upload with manufacturer/model; filter with different params; assert count."""
    body = {"file": io.BytesIO(b"bar"), "manufacturer": upload_manuf}
    if upload_model is not None:
        body["model"] = upload_model
    resp = asset_edit_client.post("/api/attachments/", body)
    assert resp.status_code == 201
    resp = asset_edit_client.get("/api/attachments/" + "?" + qparam(filter_params))
    assert resp.status_code == 200
    assert resp.data["count"] == expected_count


def test_disappearing_attachment(asset_edit_client, media_root):
    """Should still be able to respond if attachment goes missing."""
    resp = asset_edit_client.post(
        "/api/attachments/",
        {
            "file": io.BytesIO(b"bar"),
            "manufacturer": "ACME, Inc.",
        },
    )
    assert resp.status_code == 201
    att_url = resp.data["file"]
    filename = urllib.parse.urlparse(att_url).path.split("/")[-1]
    fs_path = media_root / "attachments" / filename
    assert fs_path.exists()

    # file should be gettable
    resp = asset_edit_client.get(
        "/api/attachments/"
        "?"
        + qparam(
            {
                "manufacturer__iexact": "ACME, Inc.",
            }
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["size_bytes"] == 3

    # now delete the file; should still be gettable w/ HTTP 200
    fs_path.unlink()
    resp = asset_edit_client.get(
        "/api/attachments/"
        "?"
        + qparam(
            {
                "manufacturer__iexact": "ACME, Inc.",
            }
        )
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["size_bytes"] is None
