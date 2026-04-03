"""Factory helpers for blueflow tests (model_bakery).

Use these instead of ad hoc Model.objects.create().
"""

from model_bakery import baker


def make_tag(**kwargs):
    """Create a Tag for tests. Defaults: name, color."""
    defaults = {
        "name": kwargs.pop("name", "test-tag"),
        "color": kwargs.pop("color", "#cccccc"),
    }
    return baker.make("blueflow.Tag", **{**defaults, **kwargs})


def make_user(**kwargs):
    """Create a regular user via Django's create_user (correct password hashing).

    For APIClient auth, use auth_client fixture or
    force_authenticate(user=make_user(...)).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()  # noqa: N806
    username = kwargs.pop("username", "testuser")
    password = kwargs.pop("password", "testpass")
    return User.objects.create_user(username=username, password=password, **kwargs)


def make_superuser(**kwargs):
    """Create a superuser via Django's create_superuser (correct password hashing).

    For admin-style tests, use admin_client fixture or
    force_authenticate(user=make_superuser(...)).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()  # noqa: N806
    username = kwargs.pop("username", "admin")
    email = kwargs.pop("email", "admin@test.example")
    password = kwargs.pop("password", "adminpass")
    return User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        **kwargs,
    )
