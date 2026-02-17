"""Test attachments."""

import io
import json
import os
import urllib
import pytest
from django.conf import settings as django_settings
from bf_opencore import models
from .utils import AttrDict


def qparam(pardict):
    """Get query params as string based on dictionary."""
    return urllib.parse.urlencode(pardict)


# Many functions use Model classes which *do* have an 'objects' member

def test_upload_bad(asset_edit_client):
    """Upload that doesn't contain a file."""
    resp = asset_edit_client.post('/api/attachments/',
                                  json.dumps({'foo': 'bar'}),
                                  content_type='application/json')
    assert resp.status_code == 400
    assert str(resp.data['file'][0]) == 'No file was submitted.'


def test_upload_file(asset_edit_client):
    """Upload that does contain a file, in correct format.

    Could use a real file, but io.BytesIO works just fine (StringIO
    would too...)
    """
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    assert resp.status_code == 201
    attachment = AttrDict(resp.data)
    assert int(attachment.id) > 0
    assert attachment.asset is None
    assert attachment.manufacturer is None
    assert attachment.model is None
    assert attachment.file_name == 'file'  # Not sure how to test anything else
    assert attachment.size_bytes == len(b'bar')
    assert attachment.added_by == resp.wsgi_request.user.username


def test_upload_file_with_manufacturer(asset_edit_client):
    """Upload that does contain a file, associated with one manufacturer."""
    body = {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
    }
    resp = asset_edit_client.post('/api/attachments/', body)
    assert resp.status_code == 201
    attachment = AttrDict(resp.data)
    assert int(attachment.id) > 0
    assert attachment.asset is None
    assert attachment.manufacturer == "ACME, Inc."
    assert attachment.model is None


def test_upload_file_with_model(asset_edit_client):
    """Upload that's associated with a manufacturer/model combo."""
    body = {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
        'model': "Instant Tunnel",
    }
    resp = asset_edit_client.post('/api/attachments/', body)
    assert resp.status_code == 201
    attachment = AttrDict(resp.data)
    assert int(attachment.id) > 0
    assert attachment.asset is None
    assert attachment.manufacturer == "ACME, Inc."
    assert attachment.model == "Instant Tunnel"


def test_upload_file_with_asset(asset_edit_client):
    """Upload that's associated with an asset."""
    asset = models.Asset.objects.create()
    body = {
        'file': io.BytesIO(b'bar'),
        'asset_id': asset.id,
    }
    resp = asset_edit_client.post('/api/attachments/', body)
    assert resp.status_code == 201
    attachment = AttrDict(resp.data)
    assert int(attachment.id) > 0
    assert attachment.asset_id == asset.id
    assert attachment.manufacturer is None
    assert attachment.model is None


def test_upload_file_with_name(asset_edit_client):
    """Upload file with descriptive name."""
    body = {
        'file': io.BytesIO(b'bar'),
        'name': "Descriptive",
    }
    resp = asset_edit_client.post('/api/attachments/', body)
    assert resp.status_code == 201
    attachment = AttrDict(resp.data)
    assert int(attachment.id) > 0
    assert attachment.file_name == 'file'
    assert attachment.name == 'Descriptive'


def test_get_attachments(asset_edit_client):
    """Get the attachment object(s) we just uploaded (list)."""
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert len(resp.data['results']) == 1


def test_get_attachment(asset_edit_client):
    """Get the attachment object we just uploaded (detail)."""
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    assert resp.status_code == 201
    att_id = resp.data['id']
    resp = asset_edit_client.get('/api/attachments/{}/'.format(att_id))
    assert resp.status_code == 200
    attachment = AttrDict(resp.data)
    assert attachment.id == att_id


MEDIA_URL_PREFIX = f'http://testserver{django_settings.MEDIA_URL}attachments/'
if hasattr(django_settings, 'MEDIA_ROOT'):
    MEDIA_FS_PATH = os.path.join(django_settings.MEDIA_ROOT, 'attachments')
else:
    MEDIA_FS_PATH = os.path.join(os.path.dirname(__file__),
                                 os.pardir, os.pardir,
                                 'media', 'attachments')


def test_get_attachment_file_url(asset_edit_client):
    """Get the URL of attachment object we just uploaded (detail)."""
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    att_id = resp.data['id']
    resp = asset_edit_client.get('/api/attachments/{}/'.format(att_id))
    attachment = AttrDict(resp.data)
    # Not using .startswith, the construct below gives better error feedback
    assert attachment.file[:len(MEDIA_URL_PREFIX)] == MEDIA_URL_PREFIX


def test_get_attachments_file_url(asset_edit_client):
    """Get the URL of attachment object we just uploaded (download as list).

    NOTE: The URL should always be starting with MEDIA_URL_PREFIX,
    whether downloaded as 'detail' or 'list'.
    """
    _ = asset_edit_client.post('/api/attachments/',
                               {'file': io.BytesIO(b'bar')})
    resp = asset_edit_client.get('/api/attachments/')
    attachment = AttrDict(resp.data['results'][0])
    # Not using .startswith, the construct below gives better error feedback
    assert attachment.file[:len(MEDIA_URL_PREFIX)] == MEDIA_URL_PREFIX


def test_delete_attachment(asset_edit_client):
    """Delete the attachment object we just uploaded (detail)."""
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    att_id = resp.data['id']
    resp = asset_edit_client.delete('/api/attachments/{}/'.format(att_id))
    assert resp.status_code == 204
    resp = asset_edit_client.get('/api/attachments/')
    assert resp.status_code == 200
    assert resp.data['count'] == 0


@pytest.mark.xfail(raises=AssertionError)
def test_upload_attachment_no_manuf_no_mod(asset_edit_client):
    """Can't upload attachment without manufacturer nor model.

    NOTE: this currently fails; we *are* allowed to upload such
      attachments.  Moreover, whenever we implement safeguards so this
      one passes, many other tests will fail (since they rely on the
      current loophole.)
    """
    resp = asset_edit_client.post('/api/attachments/',
                                  {'file': io.BytesIO(b'bar')})
    assert resp.status_code == 403


@pytest.mark.xfail(raises=AssertionError)
def test_upload_attachment_no_manuf_yes_mod(asset_edit_client):
    """Can't upload attachment with model but without manufacturer.

    NOTE: this currently fails; we *are* allowed to upload such attachments.
    """
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'model': "Instant Tunnel",
    })
    assert resp.status_code == 403


def test_get_attachment_manuf_model(asset_edit_client):
    """Get attachment based on manufacturer and model."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
        'model': "Instant Tunnel",
    })
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
        'model__iexact': "Instant Tunnel",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 1


def test_get_attachment_manuf_no_model_one(asset_edit_client):
    """Attachments for a specific model don't match search for null model."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
        'model': "Instant Tunnel"
    })
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
        'model__isnull': 'true',
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 0


def test_get_attachment_manuf_no_model_two(asset_edit_client):
    """Manuf-only doesn't match manuf+model search."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
    })
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
        'model__iexact': "Instant Tunnel",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 0


def test_get_attachment_manuf_no_model_three(asset_edit_client):
    """Wires don't get crossed (no model mismatch)."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
    })
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
        'model__iexact': "Instant Tunnel",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 0


def test_get_attachment_manuf_wrong_model(asset_edit_client):
    """Shouldn't get attachment with wrong model."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
        'model': "Anvil",
    })
    assert resp.status_code == 201
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
        'model__iexact': "Instant Tunnel",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 0
    # assert resp.data['results'][0]['model'] is None


def test_disappearing_attachment(asset_edit_client):
    """Should still be able to respond if attachment goes missing."""
    resp = asset_edit_client.post('/api/attachments/', {
        'file': io.BytesIO(b'bar'),
        'manufacturer': "ACME, Inc.",
    })
    assert resp.status_code == 201
    att_url = resp.data['file']
    filename = urllib.parse.urlparse(att_url).path.split('/')[-1]
    fs_path = os.path.join(MEDIA_FS_PATH, filename)
    assert os.path.exists(fs_path)

    # file should be gettable
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['size_bytes'] == 3

    # now delete the file; should still be gettable w/ HTTP 200
    os.unlink(fs_path)
    resp = asset_edit_client.get('/api/attachments/' + '?' + qparam({
        'manufacturer__iexact': "ACME, Inc.",
    }))
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['size_bytes'] is None
