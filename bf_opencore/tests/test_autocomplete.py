"""Test autocomplete interface."""

# "redefine outer name" is how pytest fixtures work.
# In tests it's often more descriptive to use len(SEQUENCE) == 0

import pytest
from bf_opencore import models
from .test_custom_field_names import cleandb, cfield


def test_autocomplete_no_error(auth_client):
    """Simply test that we don't get a 500 error when attempting complete."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=spam')
    assert candidates.status_code == 200


def test_autocomplete_no_error_order(auth_client):
    """Simply test that we don't get a 500 error when attempting ordering."""
    candidates = auth_client.get('/api/autocomplete/'
                                 '?autocomplete=spam&ordering=suggestion')
    assert candidates.status_code == 200


def test_autocomplete_numeric(auth_client, completables):
    """Autocompleting a string that is just a number finds IPs."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=1')
    assert candidates.status_code == 200
    assert candidates.data['count'] == 6


def test_autocomplete_simple(auth_client, completables):
    """Test that we get some results.

    There should be 5 suggestions when searching for 'acm':

     - The base search (open ended search for 'acm')
     - The tag 'ACME products'
     - A manufacturer search for 'starts with "acm"'
     - A manufacturer page for 'ACME'
     - A manufacturer page for 'ACME Inc.'
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    assert candidates.data['count'] == 5   # Base search, Tag, 3 manufacturer


def test_autocomplete_fields(auth_client, completables):
    """Test that the fields are what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    first_c = candidates.data['results'][0]
    assert set(first_c.keys()) == set([
        'term', 'suggestion', 'suggestion_type', 'url', 'query'])


def test_autocomplete_tag(auth_client, completables):
    """Test that the tag result is what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    tag_cands = [c for c in candidates.data['results']
                 if c['suggestion_type'] == 'Tag']
    assert len(tag_cands) == 1
    tag_cand = tag_cands[0]
    acme_tag = models.Tag.objects.get(name="ACME products")
    assert tag_cand['url'] == f'/tags/{acme_tag.id}/'


def test_autocomplete_vuln(auth_client, completables):
    """Test that the vulnerability result is what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=quux')
    vuln_cands = [c for c in candidates.data['results']
                  if c['suggestion_type'] == 'Vulnerability']
    assert len(vuln_cands) == 1
    vuln_cand = vuln_cands[0]
    vulns = auth_client.get('/api/vulnerabilities/')
    assert vulns.data['count'] == 1
    vuln_id = vulns.data['results'][0]['id']
    assert vuln_cand['url'] == f'/vulnerabilities/{vuln_id}/'
    assert vuln_cand['query'] == {'vulnerability': vuln_id}


def test_autocomplete_group(auth_client, completables):
    """Test that we can autocomplete a Group."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=Bargl')
    grp_cands = [c for c in candidates.data['results']
                 if c['suggestion_type'] == 'Group']
    assert len(grp_cands) == 1
    groups = auth_client.get('/api/groups/')
    assert groups.data['count'] == 1
    grp_id = groups.data['results'][0]['id']
    assert grp_cands[0]['url'] == f'/groups/{grp_id}/'
    assert grp_cands[0]['query'] == {'group': grp_id}


def test_autocomplete_network(auth_client, completables):
    """Test that we can autocomplete a Network."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=Blorp')
    net_cands = [c for c in candidates.data['results']
                 if c['suggestion_type'] == 'Network']
    assert len(net_cands) == 1
    groups = auth_client.get('/api/networks/')
    assert groups.data['count'] == 1
    net_id = groups.data['results'][0]['id']
    assert net_cands[0]['url'] == f'/networks/{net_id}/'
    assert net_cands[0]['query'] == {'network': net_id}


def test_autocomplete_base(auth_client, completables):
    """Test that the base result is what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    base_cand = candidates.data['results'][0]
    assert base_cand['suggestion_type'] is None
    assert base_cand['url'] == '/search/?search=acm'
    assert base_cand['query'] == {'search': 'acm'}


def test_autocomplete_manufs_0(auth_client, completables):
    """Test that the manufacturer results are what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert len(manuf_cands) == 3
    assert manuf_cands[0]['url'] == '/search/?manufacturer__istartswith=acm'
    assert manuf_cands[0]['query'] == {'manufacturer__istartswith': 'acm'}


def test_autocomplete_manufs_1(auth_client, completables):
    """Test that the manufacturer results are what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert manuf_cands[1]['url'] == '/manufacturer/?manufacturer=ACME'
    assert manuf_cands[1]['query'] == {'manufacturer': 'ACME'}


def test_autocomplete_manufs_2(auth_client, completables):
    """Test that the manufacturer results are what we expect."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acm')
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert manuf_cands[2]['url'] == '/manufacturer/?manufacturer=ACME+Inc.'
    assert manuf_cands[2]['query'] == {'manufacturer': 'ACME Inc.'}


def test_autocomplete_limit_manufs(auth_client, completables):
    """Test that we don't get repeated results.

    When our term matches a manufacturer eaxtly, the exact result isn't
    repeated. When searching for 'ACME' there should thuse be 4
    suggestions, the ones above minus the "manufacturer search for ...";
    it would now be subsumed into the Manufacturer page suggestion.
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=ACME')
    assert candidates.data['count'] == 4   # Base search, Tag, 2 manufacturer
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert len(manuf_cands) == 2
    assert manuf_cands[0]['url'] == '/manufacturer/?manufacturer=ACME'
    assert manuf_cands[1]['url'] == '/manufacturer/?manufacturer=ACME+Inc.'
    assert manuf_cands[0]['query'] == {'manufacturer': 'ACME'}
    assert manuf_cands[1]['query'] == {'manufacturer': 'ACME Inc.'}


def test_autocomplete_limit_manufs_lowercase(auth_client, completables):
    """Test that we don't get repeated results also with lowercase.

    Like above, but our search term is lowercase.  This shouldn't make a
    difference.
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=acme')
    assert candidates.data['count'] == 4   # Base search, Tag, 2 manufacturer
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert len(manuf_cands) == 2
    assert manuf_cands[0]['url'] == '/manufacturer/?manufacturer=ACME'
    assert manuf_cands[1]['url'] == '/manufacturer/?manufacturer=ACME+Inc.'
    assert manuf_cands[0]['query'] == {'manufacturer': 'ACME'}
    assert manuf_cands[1]['query'] == {'manufacturer': 'ACME Inc.'}


def test_autocomplete_manufs_space(auth_client, completables):
    """Test that manufacturer search works even when there's a space char.

    When our term matches a manufacturer eaxtly, the exact result isn't
    repeated. When searching for 'ACME' there should thuse be 4
    suggestions, the ones above minus the "manufacturer search for ...";
    it would now be subsumed into the Manufacturer page suggestion.
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=ACME%20In')
    assert candidates.data['count'] == 3   # Base search, 2 manufacturer
    manuf_cands = [c for c in candidates.data['results']
                   if c['suggestion_type'] == 'Manufacturer']
    assert len(manuf_cands) == 2
    assert manuf_cands[0]['url'] == ('/search/?manufacturer__istartswith='
                                     'ACME+In')
    assert manuf_cands[1]['url'] == '/manufacturer/?manufacturer=ACME+Inc.'
    assert manuf_cands[0]['query'] == {'manufacturer__istartswith': 'ACME In'}
    assert manuf_cands[1]['query'] == {'manufacturer': 'ACME Inc.'}


def test_autocomplete_mac_address(auth_client, completables):
    """Test that autocompleter matches MAC address."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=8')
    mac_cands = [c for c in candidates.data['results']
                 if c['suggestion_type'] == 'Mac Address']
    assert len(mac_cands) == 2
    assert mac_cands[0]['url'] == '/search/?mac_address__istartswith=8'
    assert mac_cands[1]['url'] == \
        '/search/?mac_address__istartswith=88%3Aaa%3Abb%3Acc%3Add%3Aee'
    assert mac_cands[0]['query'] == {'mac_address__istartswith': '8'}
    assert mac_cands[1]['query'] == {'mac_address__istartswith':
                                     '88:aa:bb:cc:dd:ee'}


def test_autocomplete_os(auth_client, completables):
    """Test that autocompleter matches operating system."""
    candidates = auth_client.get('/api/autocomplete/?autocomplete=win')
    os_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'OS']
    assert len(os_cands) == 2
    assert os_cands[0]['url'] == ('/search/?os__istartswith=win')
    assert os_cands[1]['url'] == ('/search/?os__istartswith=Windows+95')
    assert os_cands[0]['query'] == {'os__istartswith': 'win'}
    assert os_cands[1]['query'] == {'os__istartswith': 'Windows 95'}


def test_autocomplete_serial_number(auth_client, completables):
    candidates = auth_client.get('/api/autocomplete/?autocomplete=wile')
    sn_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'Serial Number']
    assert len(sn_cands) == 2
    assert sn_cands[0]['url'] == '/search/?serial_number__istartswith=wile'
    assert sn_cands[1]['url'] == \
        '/search/?serial_number__istartswith=WILE-E-1234'
    assert sn_cands[0]['query'] == {'serial_number__istartswith': 'wile'}
    assert sn_cands[1]['query'] == {'serial_number__istartswith':
                                    'WILE-E-1234'}


################################################################
#  Autocomplete on custom field names/fields

def test_autocomplete_custom_field_name(auth_client, cfield):
    """Autocomplete on the field_name of a custom field.

    The asset 'foo.com' (created in cfield) has a value (it doesn't
    matter what it is) in the custom field 'shinyness'.

    Still, 'shinyness' should not return any results.
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=shiny')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] is not None]
    assert len(cv_cands) == 0


def test_autocomplete_custom_field_name_nocust(auth_client, cfield):
    """Autocomplete on the field_name of a custom field.

    The asset 'bar.com' (just created) has no value in custom field
    'shinyness'

    Still, 'shinyness' should not return any results.
    """
    asset_foo = models.Asset.objects.get(hostname='foo.com')
    asset_foo.delete()
    models.Asset.objects.create(hostname='bar.com')
    candidates = auth_client.get('/api/autocomplete/?autocomplete=shiny')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] is not None]
    assert len(cv_cands) == 0


def test_autocomplete_custom_value(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The asset 'foo.com' has value 'rather dull' in custom field 'shinyness'.
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=rath')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'Custom Field']
    assert len(cv_cands) == 2
    assert cv_cands[0]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rath'
    assert cv_cands[1]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rather+dull'
    assert cv_cands[0]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rath'}
    assert cv_cands[1]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rather dull'}


def test_autocomplete_custom_value_notprefix(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The asset 'foo.com' has value 'rather dull' in custom field
    'shinyness', but we autocomplete only on prefix.

    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=dull')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] is not None]
    assert len(cv_cands) == 0


def test_autocomplete_custom_value_duplicate_1(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The assets 'foo.com' and 'bar.com' both have value 'rather dull' in
    custom field 'shinyness'.

    We should still only see one autocomplete for 'rather dull'.
    """
    asset = models.Asset.objects.create(hostname='bar.com')
    shiny_field = models.AssetCustomFieldName.objects.get(
        field_name='shinyness')
    assert models.AssetCustomField.objects.count() == 1
    models.AssetCustomField.objects.create(
        field=shiny_field, asset=asset, value_text='rather dull')
    assert models.AssetCustomField.objects.count() == 2

    candidates = auth_client.get('/api/autocomplete/?autocomplete=rath')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'Custom Field']
    assert len(cv_cands) == 2
    assert cv_cands[0]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rath'
    assert cv_cands[1]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rather+dull'
    assert cv_cands[0]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rath'}
    assert cv_cands[1]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rather dull'}


def test_autocomplete_custom_value_duplicate_2(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The assets 'foo.com' and 'bar.com' both have value 'rather dull', one in
    custom field 'shinyness', the other in 'sparkliness'.

    We should still only see one autocomplete for 'rather dull'.
    """
    asset = models.Asset.objects.create(hostname='bar.com')
    sparkly_field = models.AssetCustomFieldName.objects.get(
        field_name='sparkliness')
    assert models.AssetCustomField.objects.count() == 1
    models.AssetCustomField.objects.create(
        field=sparkly_field, asset=asset, value_text='rather dull')
    assert models.AssetCustomField.objects.count() == 2

    candidates = auth_client.get('/api/autocomplete/?autocomplete=rath')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'Custom Field']
    assert len(cv_cands) == 2
    assert cv_cands[0]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rath'
    assert cv_cands[1]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rather+dull'
    assert cv_cands[0]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rath'}
    assert cv_cands[1]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rather dull'}


def test_autocomplete_custom_value_duplicate_3(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The asset 'foo.com' has value 'rather dull', both in
    custom field 'shinyness' and in 'sparkliness'.

    We should still only see one autocomplete for 'rather dull'.
    """
    asset = models.Asset.objects.get(hostname='foo.com')
    sparkly_field = models.AssetCustomFieldName.objects.get(
        field_name='sparkliness')
    assert models.AssetCustomField.objects.count() == 1
    models.AssetCustomField.objects.create(
        field=sparkly_field, asset=asset, value_text='rather dull')
    assert models.AssetCustomField.objects.count() == 2

    candidates = auth_client.get('/api/autocomplete/?autocomplete=rath')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] == 'Custom Field']
    assert len(cv_cands) == 2
    assert cv_cands[0]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rath'
    assert cv_cands[1]['url'] == \
        '/search/?asset_custom_fields__value_text__istartswith=rather+dull'
    assert cv_cands[0]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rath'}
    assert cv_cands[1]['query'] == {
        'asset_custom_fields__value_text__istartswith': 'rather dull'}


def test_autocomplete_custom_value_badcust(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    The asset 'foo.com' has value 'rather dull' in custom field 'shinyness',
    but not 'shinny'.
    (Deliberately misspelled so that it won't match the custom field name!)
    """
    candidates = auth_client.get('/api/autocomplete/?autocomplete=shinny')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] is not None]
    assert len(cv_cands) == 0


def test_autocomplete_custom_value_nocust(auth_client, cfield):
    """Autocomplete on the value of a custom field.

    No asset has a value in custom field 'shinyness'.
    """
    asset_foo = models.Asset.objects.get(hostname='foo.com')
    asset_foo.delete()
    candidates = auth_client.get('/api/autocomplete/?autocomplete=rath')
    cv_cands = [c for c in candidates.data['results']
                if c['suggestion_type'] is not None]
    assert len(cv_cands) == 0
