"""Authentication and Authorization/Permissions Tests."""

import pytest
from django.contrib.auth.models import Group, User

from bf_opencore.management.commands import create_permission_groups as cpg


@pytest.fixture(autouse=True)
def setup_user(db):
    """Create a user, needed in all these tests."""
    dummy_user = User.objects.create_user(
        "blueflow", "blueflow@virtalabs.com", "blueflow"
    )


def test_not_authenticated(client):
    """Ensure we can't get anything unless we're logged in."""
    assets = client.get("/api/assets/")
    assert assets.status_code == 403


def test_authenticate_post(client):
    """One way to authenticate in the test system."""
    authenticated = client.post(
        "/accounts/login/", {"username": "blueflow", "password": "blueflow"}
    )
    assert authenticated.status_code == 302


def test_authenticate_login(client):
    """Another way to authenticate in the test system.

    However generally, one should use the auth_client fixture
    defined in conftest.py.
    """
    authenticated = client.login(username="blueflow", password="blueflow")
    assert authenticated is True


def test_get_empty_assets_custom_user(client):
    """Test that asset list is empty unless we do something special."""
    authenticated = client.login(username="blueflow", password="blueflow")
    assert authenticated is True
    assets = client.get("/api/assets/")
    assert assets.status_code == 200
    assert assets.data["count"] == 0


def test_get_empty_assets_standard_user(auth_client):
    """Test that auth_client works as expected."""
    assets = auth_client.get("/api/assets/")
    assert assets.status_code == 200
    assert assets.data["count"] == 0


def test_test_module_user():
    """Ensure that user supplied to all functions in this module is here."""
    users = User.objects.all()
    assert users.count() == 1
    user = users.first()
    assert user.username == "blueflow"


def test_auth_user(auth_client):
    """Ensure that auth_client supplies another user.

    This test (and the previous one) are really only sanity checks... to
    make sure that the user creation etc. work exactly as expected.
    """
    # auth_client is only there to create that extra user, under the hood.
    users = User.objects.all()
    assert users.count() == 2
    names = {u.username for u in users}
    assert names == {"blueflow", "roald"}  # 'roald' is from auth_client


def test_perm_user(asset_edit_client):
    """Ensure that asset_edit_client supplies another user.

    This test (and the previous one) are really only sanity checks... to
    make sure that the user creation etc. work exactly as expected.
    """
    # asset_edit_client is only there to create extra user, under the hood.
    users = User.objects.all()
    assert users.count() == 2
    names = {u.username for u in users}
    assert names == {"blueflow", "fridtjof"}


def test_perm_auth_user(asset_edit_client, auth_client):
    """Ensure that asset_edit_client supplies another user.

    This test (and the previous one) are really only sanity checks... to
    make sure that the user creation etc. work exactly as expected.
    """
    # client args are only there to create extra users under the hood.
    users = User.objects.all()
    assert users.count() == 3
    names = {u.username for u in users}
    assert names == {"blueflow", "fridtjof", "roald"}


@pytest.mark.xfail(
    raises=AssertionError,
    reason="Not sure why, but we're not able to pass 2 "
    "separate clients to the test function.",
)
def test_perm_auth_clients(asset_edit_client, auth_client):
    """Would have expected that these two clients are, indeed, different.

    They are, in fact, the same!  Thus this fails.  This is the reason
    why test_assets.py::test_api_create_unauth_patch_asset also fails.
    """
    assert auth_client is not asset_edit_client


@pytest.mark.xfail(raises=AssertionError, reason="Same as above")
def test_perm_auth_clients_swap(auth_client, asset_edit_client):
    """Same as above, just swapped."""
    assert auth_client is not asset_edit_client


def test_perm_auth_clients_admin(admin_client, auth_client):
    """admin_client and auth_client *are* different."""
    assert auth_client != admin_client


def test_no_groups():
    """Ensure that by default, there are no groups."""
    groups = Group.objects.all()
    assert groups.count() == 0


def test_create_permission_groups_default():
    """Test group creation by our create_permissions_groups function."""
    # create_permission_groups.BLUEFLOW_GROUPS
    cpg.create_permission_groups()
    groups = Group.objects.all()
    assert groups.count() == len(cpg.BLUEFLOW_GROUPS)


def test_create_permission_groups_custom():
    """Test flexibility of our create_permissions_groups function."""
    # create_permission_groups.BLUEFLOW_GROUPS
    group_name = "foo"
    perms = [("blueflow", "add_asset"), ("blueflow", "change_asset")]
    custom_groups = {group_name: perms}
    cpg.create_permission_groups(groups=custom_groups)
    groups = Group.objects.all()
    assert groups.count() == 1
    group = groups.first()
    assert group.name == group_name
    gperms = {
        (perm.content_type.app_label, perm.codename) for perm in group.permissions.all()
    }
    assert gperms == set(perms)
