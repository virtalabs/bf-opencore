"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""
import pytest

from datetime import timedelta

from django.utils import timezone

from bf_opencore.models import Alert

# models do have 'objects' member, but it's being lazy loaded


@pytest.mark.django_db
def test_simple(auth_client):
    """Alert API simple test."""
    Alert.objects.create(text="Alert 1")  # date_created is "now"
    Alert.objects.create(text="Alert 2")
    response = auth_client.get("/api/alerts/")
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_order(auth_client):
    """Alerts are ordered with newest first."""
    Alert.objects.create(text="Alert 1")  # date_created is "now"
    Alert.objects.create(
        text="Alert 2",
        date_created=timezone.now() - timedelta(1),  # yesterday
    )
    response = auth_client.get("/api/alerts/")
    assert response.data["results"][0]["text"] == "Alert 1"


@pytest.mark.django_db
def test_count_expiration(auth_client):
    """Alert count excludes expired."""
    Alert.objects.create(
        text="Alert 1",
        date_read=None,  # Not read
        date_expiration=None,  # No expiration
    )
    Alert.objects.create(
        text="Alert 2",
        date_read=None,  # Not read
        date_expiration=timezone.now() - timedelta(1),  # Expired
    )
    Alert.objects.create(
        text="Alert 3",
        date_read=timezone.now(),  # Read
        date_expiration=None,  # No expiration
    )
    Alert.objects.create(
        text="Alert 4",
        date_read=timezone.now(),  # Read
        date_expiration=timezone.now() - timedelta(1),  # Expired
    )
    Alert.objects.create(
        text="Alert 5",
        date_read=timezone.now(),  # Read
        date_expiration=timezone.now() + timedelta(1),  # Expires tomorrow
    )
    Alert.objects.create(
        text="Alert 6",
        date_read=None,  # Not read
        date_expiration=timezone.now() + timedelta(1),  # Expires tomorrow
    )
    response = auth_client.get("/api/alerts/")
    assert response.data["count"] == 4
    assert response.data["count_unread"] == 2
    assert response.data["count_read"] == 2

