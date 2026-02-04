"""Test custom field names.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

from collections import namedtuple
import json
import pytest
import blueflow.models as bf_mod

################################################################
# Fixtures


@pytest.fixture
def cleandb(db):
    """Remove custom fields added by migrations.

    For example, the "location" custom field is added by a migration.  These
    tests assume starting without it.
    """
    bf_mod.AssetCustomFieldName.objects.all().delete()


@pytest.fixture
def cfield(cleandb):
    """Prepare some things for reuse

     - an asset
     - a couple of custom fields (names)
     - and a custom field (value)
    """
    asset = bf_mod.Asset.objects.create(hostname='foo.com')
    sparkly_field = bf_mod.AssetCustomFieldName.objects.create(
        field_name='sparkliness')
    shiny_field = bf_mod.AssetCustomFieldName.objects.create(
        field_name='shinyness')
    custom_field = bf_mod.AssetCustomField.objects.create(
        field=shiny_field, asset=asset, value_text='rather dull')
    cfield_tuple = namedtuple(
        'cfield_tuple',
        ['asset', 'sparkly_field', 'shiny_field', 'custom_field'])
    return cfield_tuple(asset, sparkly_field, shiny_field, custom_field)


################################################################
# Tests


def test_custom_field_name(cleandb, auth_client):
    """Test get custom field names."""
    afn_object = bf_mod.AssetCustomFieldName.objects.create(field_name='red')
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 1
    assert len(afn['results']) == 1
    assert afn['results'][0]['field_name'] == afn_object.field_name
    assert afn['results'][0]['field_name'] == 'red'


################################################################
# Adding/deleting

def test_api_add_custom_field_name(cleandb, auth_client, admin_client):
    """Add custom field names via API."""
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 0
    assert len(afn['results']) == 0
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    # NOTE: need admin client to add fields
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400  # Cannot add duplicate field name
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 1
    assert len(afn['results']) == 1
    assert afn['results'][0]['field_name'] == 'sparkliness'


def test_api_delete_custom_field_name(cleandb, auth_client, admin_client):
    """Delete custom field names via API is allowed."""
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    # NOTE: need admin client to add fields
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201
    new_cfn_id = res.json()['id']
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 1
    res = admin_client.delete(
        '/api/assetcustomfieldnames/{}/'.format(new_cfn_id))
    assert res.status_code == 204
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 0


@pytest.mark.parametrize('num_fields', [0, 1, 20, 21, 100])
def test_api_add_many_custom_field_names(
        num_fields, cleandb, auth_client, admin_client):
    """Add custom field names via API."""
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 0
    assert len(afn['results']) == 0
    kwargs = {'content_type': 'application/json'}
    for n in range(num_fields):
        # add num_fields fields, with names 'field_<n>'
        kwargs['data'] = json.dumps({'field_name': 'afield_{}'.format(n)})
        # NOTE: need admin client to add fields
        res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
        assert res.status_code == 201
    res = auth_client.get('/api/assetcustomfieldnames/')
    assert res.status_code == 200
    assert res.json()['count'] == num_fields
    assert len(res.json()['results']) == num_fields


################################################################
# Disable field name

@pytest.mark.xfail(raises=AssertionError,
                   reason="Not yet implemented")
def test_api_disable_custom_field_name(cleandb, auth_client, admin_client):
    """Disabling custom field is allowed.  After, it shouldn't be visible.

    NOTE: disabling passes, however the filtering feature to prevent
      showing disabled fields is not.  Thus the field name will still
      arrive even though it's disabled.
    """
    afn = auth_client.get('/api/assetcustomfieldnames/').json()
    assert afn['count'] == 0

    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    # NOTE: need admin client to add fields
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201
    afn = auth_client.get('/api/assetcustomfieldnames/').json()['results'][0]
    assert afn['enabled'] is True

    kwargs['data'] = json.dumps({'enabled': False})
    res = admin_client.patch(afn['url'], **kwargs)
    assert res.status_code == 200
    res = auth_client.get('/api/assetcustomfieldnames/').json()['results']
    assert len(res) == 0  # Fails since filtering on 'enabled==True' not impl
    # Should not be able to get a field name that's been disabled.
    # Could potentially add a 'disabled=True' in order to see and
    # possibly re-enable fields; but this is *only* for the field names.
    # Need to add more tests: Should also not be able to get field
    # *value* from such a field.  (Several tests to be made.)

    # afn = auth_client.get('/api/assetcustomfieldnames/').json()['results'][0]
    # assert afn['enabled'] is False


def test_api_disable_custom_field_name_get_disabled(
        cleandb, auth_client, admin_client):
    """Disabling custom field is allowed.

    After this is shouldn't be visible unless specifically asked for.

    NOTE: filtering isn't implemented... so this will simply pass on default.
    """
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    # NOTE: need admin client to add fields
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    afn = auth_client.get('/api/assetcustomfieldnames/').json()['results'][0]
    assert afn['enabled'] is True

    kwargs['data'] = json.dumps({'enabled': False})
    res = admin_client.patch(afn['url'], **kwargs)
    assert res.status_code == 200
    res = auth_client.get('/api/assetcustomfieldnames/?disabled=True').json()
    assert len(res['results']) == 1
    afn = res['results'][0]
    assert afn['enabled'] is False


@pytest.mark.xfail(raises=AssertionError,
                   reason="Not yet implemented")
def test_api_disabled_custom_field(cleandb, auth_client, admin_client):
    """Disable custom field."""
    asset_id = bf_mod.Asset.objects.create(hostname='foo.com').id
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    afn = res.json()
    kwargs['data'] = json.dumps({'field_id': afn['id'],
                                 'asset_id': asset_id,
                                 'value_text': 'very sparkly'})
    res = admin_client.post('/api/assetcustomfields/', **kwargs)
    af = auth_client.get('/api/assetcustomfields/').json()
    assert af['results'][0]['field']['field_name'] == 'sparkliness'
    kwargs['data'] = json.dumps({'enabled': False})
    res = admin_client.patch(afn['url'], **kwargs)
    assert res.status_code == 200
    af = auth_client.get('/api/assetcustomfields/').json()
    assert len(af['results']) == 0
    assert af['count'] == 0


@pytest.mark.xfail(raises=AssertionError,
                   reason="Not yet implemented")
def test_api_asset_disabled_custom_field(cleandb, auth_client, admin_client):
    """No custom field arriving with the asset when disabled."""
    asset_id = bf_mod.Asset.objects.create(hostname='foo.com').id
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    afn = res.json()
    asset = auth_client.get('/api/assets/{}/'.format(asset_id)).json()
    assert asset['hostname'] == 'foo.com'
    assert len(asset['asset_custom_fields']) == 0
    assert asset['asset_custom_fields'] == []
    kwargs['data'] = json.dumps({'field_id': afn['id'],
                                 'asset_id': asset_id,
                                 'value_text': 'very sparkly'})
    res = admin_client.post('/api/assetcustomfields/', **kwargs)
    # Disable custom field; it shouldn't be visible
    kwargs['data'] = json.dumps({'enabled': False})
    res = admin_client.patch(afn['url'], **kwargs)
    asset = auth_client.get('/api/assets/{}/'.format(asset_id)).json()
    assert asset['hostname'] == 'foo.com'
    assert len(asset['asset_custom_fields']) == 0


################################################################
# Test post field name with different users

def test_api_field_name_unauthorized_post(auth_client):
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    res = auth_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 403


def test_api_field_name_authorized_post(custom_field_edit_client):
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    res = custom_field_edit_client.post('/api/assetcustomfieldnames/',
                                        **kwargs)
    assert res.status_code == 201


def test_api_field_name_admin_post(admin_client):
    kwargs = {'data': json.dumps({'field_name': 'sparkliness'}),
              'content_type': 'application/json'}
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201


################################################################
# Test patch field name with different users

def test_api_field_name_unauthorized_patch(cfield, auth_client):
    fn_id = cfield.shiny_field.id
    kwargs = {'data': json.dumps({'field_name': 'dullness'}),
              'content_type': 'application/json'}
    res = auth_client.patch('/api/assetcustomfieldnames/{}/'
                            ''.format(fn_id), **kwargs)
    assert res.status_code == 403


def test_api_field_name_authorized_patch(cfield, custom_field_edit_client):
    assert cfield.shiny_field.field_name == 'shinyness'
    fn_id = cfield.shiny_field.id
    kwargs = {'data': json.dumps({'field_name': 'dullness'}),
              'content_type': 'application/json'}
    res = custom_field_edit_client.patch('/api/assetcustomfieldnames/{}/'
                                         ''.format(fn_id), **kwargs)
    assert res.status_code == 200
    cfield.shiny_field.refresh_from_db()
    assert cfield.shiny_field.field_name == 'dullness'


def test_api_field_name_admin_patch(cfield, admin_client):
    fn_id = cfield.shiny_field.id
    kwargs = {'data': json.dumps({'field_name': 'dullness'}),
              'content_type': 'application/json'}
    res = admin_client.patch('/api/assetcustomfieldnames/{}/'
                             ''.format(fn_id), **kwargs)
    assert res.status_code == 200


################################################################
# Test delete field name with different users

def test_api_field_name_unauthorized_delete(cfield, auth_client):
    """Simply Authenticated client should not be allowed to delete."""
    fn_id = cfield.shiny_field.id
    res = auth_client.delete('/api/assetcustomfieldnames/{}/'
                             ''.format(fn_id))
    assert res.status_code == 403


def test_api_field_name_authorized_delete(cfield, custom_field_edit_client):
    """Authorized client should be allowed to delete."""
    cfield.custom_field.delete()
    res = custom_field_edit_client.get('/api/assetcustomfields/')
    assert res.json()['results'] == []
    fn_id = cfield.shiny_field.id
    res = custom_field_edit_client.delete('/api/assetcustomfieldnames/{}/'
                                          ''.format(fn_id))
    assert res.status_code == 204  # No content


def test_api_field_name_admin_delete(cfield, admin_client):
    """Admin client should be allowed to delete."""
    cfield.custom_field.delete()
    res = admin_client.get('/api/assetcustomfields/')
    assert res.json()['results'] == []
    fn_id = cfield.shiny_field.id
    res = admin_client.delete('/api/assetcustomfieldnames/{}/'
                              ''.format(fn_id))
    assert res.status_code == 204  # No content


def test_api_field_name_admin_delete_not_with_fields(cfield, admin_client):
    """Admin client should also be allowed to delete when cust fields exist."""
    res = admin_client.get('/api/assetcustomfields/')
    assert res.json()['results'][0]['value_text'] == 'rather dull'
    fn_id = cfield.shiny_field.id
    res = admin_client.delete('/api/assetcustomfieldnames/{}/'
                              ''.format(fn_id))
    assert res.status_code == 204  # No content


################################################################
# Test field order

def test_api_field_name_order_1(cfield, admin_client):
    """Field names are in alphabetical order."""
    afns = admin_client.get('/api/assetcustomfieldnames/').json()['results']
    assert [a['field_name'] for a in afns] == ['shinyness', 'sparkliness']


def test_api_field_name_order_2(cfield, admin_client):
    """Patching a field name shouldn't change the order."""
    afns = admin_client.get('/api/assetcustomfieldnames/').json()['results']
    fields_ordered = [a['field_name'] for a in afns]

    kwargs = {'content_type': 'application/json'}
    kwargs['data'] = json.dumps({'enabled': False})
    res = admin_client.patch(afns[0]['url'], **kwargs)
    assert res.status_code == 200

    afns = admin_client.get('/api/assetcustomfieldnames/').json()['results']
    assert [a['field_name'] for a in afns] == fields_ordered


def test_api_field_name_order_3(cfield, admin_client):
    """Adding a field - list still alphabetical."""
    kwargs = {'content_type': 'application/json'}
    kwargs['data'] = json.dumps({'field_name': 'a'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201

    afns = admin_client.get('/api/assetcustomfieldnames/').json()['results']
    assert [a['field_name'] for a in afns] == ['a', 'shinyness', 'sparkliness']


def test_reject_similar_to_asset_field(admin_client):
    """Adding a field simliar to an asset field is not OK."""
    kwargs = {'content_type': 'application/json'}

    kwargs['data'] = json.dumps({'field_name': 'rIsK sCoRe'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400

    kwargs['data'] = json.dumps({'field_name': 'os'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400

    kwargs['data'] = json.dumps({'field_name': 'operating   ____ system'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400


def test_reject_similar_to_other_custom_field(admin_client):
    """Adding a field simliar to an existing custom field is not OK."""
    kwargs = {'content_type': 'application/json'}
    kwargs['data'] = json.dumps({'field_name': 'shinyness'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 201
    kwargs['data'] = json.dumps({'field_name': 'shiny_ness'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400
    kwargs['data'] = json.dumps({'field_name': 'ShinyNess'})
    res = admin_client.post('/api/assetcustomfieldnames/', **kwargs)
    assert res.status_code == 400
