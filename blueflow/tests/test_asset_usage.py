"""Tests for the Asset usage tracking via the Usage FK model.

Each Asset can have up to 7 Usage rows (one per weekday). Each row holds 24
integer hour columns (hour_00..hour_23) and a last_window_started_at
timestamp used for Usage.USAGE_WINDOW_MINUTES-deduped increments.

The wire contract on AssetSerializer.usage is a Monday-first 7-element array
of {str(hour) -> count} maps with zero-count hours stripped.
"""

import datetime
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from blueflow import models

DAYS_IN_WEEK = 7


def _fixed(year, month, day, hour, minute):
    return datetime.datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=datetime.UTC,
    )


def test_asset_response_includes_usage_field(auth_client):
    """Each asset response includes a usage field as a 7-element array."""
    asset = models.Asset.objects.create(hostname="usage-test.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert "usage" in body
    assert isinstance(body["usage"], list)
    assert len(body["usage"]) == DAYS_IN_WEEK


def test_asset_with_no_usage_rows_emits_empty_hour_dicts(auth_client):
    """An asset with no Usage rows serializes 7 empty hour dicts."""
    asset = models.Asset.objects.create(hostname="usage-empty.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    body = response.json()
    for index, hours in enumerate(body["usage"]):
        assert hours == {}, f"index {index} should be empty (got {hours!r})"


def test_usage_default_day_of_week_is_monday():
    """A bare Usage() (no day_of_week supplied) defaults to Monday."""
    asset = models.Asset.objects.create(hostname="usage-default.example.com")
    usage = models.Usage(asset=asset)
    assert usage.day_of_week == models.DayOfWeek.MONDAY == 0


def test_usage_window_constant_is_five_minutes():
    """The dedup window constant lives on Usage and is 5 minutes."""
    assert models.Usage.USAGE_WINDOW_MINUTES == 5  # noqa: PLR2004


def test_upsert_creates_usage_row_with_correct_hour(auth_client):
    """A single upsert creates one Usage row for the current weekday."""
    # 2026-05-19 is a Tuesday (weekday=1)
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 0),
    ):
        response = auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": "aa:bb:cc:dd:ee:01"},
            format="json",
        )
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get(mac_address="aa:bb:cc:dd:ee:01")
    rows = list(asset.usage.all())
    assert len(rows) == 1
    assert rows[0].day_of_week == 1
    assert rows[0].hour_14 == 1


def test_two_upserts_within_same_5min_window_count_as_one(auth_client):
    """14:01 and 14:02 share the 14:00-14:05 window → counts as 1."""
    mac = "aa:bb:cc:dd:ee:02"
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 1),
    ):
        auth_client.put("/api/assets/upsert/", data={"mac_address": mac}, format="json")
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 2),
    ):
        response = auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": mac},
            format="json",
        )
    assert response.json()["usage"][1] == {"14": 1}


def test_upserts_in_different_5min_windows_increment_separately(auth_client):
    """14:01 and 14:06 cross a 5-min boundary → counts as 2 in the same hour."""
    mac = "aa:bb:cc:dd:ee:03"
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 1),
    ):
        auth_client.put("/api/assets/upsert/", data={"mac_address": mac}, format="json")
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 6),
    ):
        response = auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": mac},
            format="json",
        )
    assert response.json()["usage"][1] == {"14": 2}


def test_upsert_at_exact_window_boundary_increments(auth_client):
    """14:04:59 and 14:05:00 fall in different windows → counts as 2."""
    mac = "aa:bb:cc:dd:ee:04"
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=datetime.datetime(
            2026,
            5,
            19,
            14,
            4,
            59,
            tzinfo=datetime.UTC,
        ),
    ):
        auth_client.put("/api/assets/upsert/", data={"mac_address": mac}, format="json")
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 14, 5),
    ):
        response = auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": mac},
            format="json",
        )
    assert response.json()["usage"][1] == {"14": 2}


def test_upserts_across_midnight_land_in_different_weekday_rows(auth_client):
    """23:58 Tuesday and 00:03 Wednesday produce two Usage rows."""
    mac = "aa:bb:cc:dd:ee:05"
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 19, 23, 58),  # Tuesday
    ):
        auth_client.put("/api/assets/upsert/", data={"mac_address": mac}, format="json")
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 20, 0, 3),  # Wednesday
    ):
        response = auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": mac},
            format="json",
        )
    asset = models.Asset.objects.get(mac_address=mac)
    rows = {u.day_of_week: u for u in asset.usage.all()}
    assert rows[1].hour_23 == 1
    assert rows[2].hour_00 == 1
    usage = response.json()["usage"]
    assert usage[1] == {"23": 1}
    assert usage[2] == {"0": 1}


def test_weekday_index_zero_is_monday(auth_client):
    """2026-05-18 is a Monday — Usage row has day_of_week=0."""
    with mock.patch(
        "blueflow.views.asset.timezone.now",
        return_value=_fixed(2026, 5, 18, 10, 0),  # Monday
    ):
        auth_client.put(
            "/api/assets/upsert/",
            data={"mac_address": "aa:bb:cc:dd:ee:06"},
            format="json",
        )
    asset = models.Asset.objects.get(mac_address="aa:bb:cc:dd:ee:06")
    row = asset.usage.get()
    assert row.day_of_week == 0


def test_get_response_omits_zero_count_hours(auth_client):
    """Hours with zero observations are stripped from the response."""
    asset = models.Asset.objects.create(hostname="usage-strip.example.com")
    models.Usage.objects.create(
        asset=asset,
        day_of_week=0,
        hour_09=0,
        hour_10=3,
    )
    body = auth_client.get(f"/api/assets/{asset.id}/").json()
    assert body["usage"][0] == {"10": 3}


def test_at_most_one_usage_row_per_asset_per_weekday(auth_client):
    """Repeated upserts on the same weekday reuse the same Usage row."""
    mac = "aa:bb:cc:dd:ee:07"
    for minute in (0, 6, 12):
        with mock.patch(
            "blueflow.views.asset.timezone.now",
            return_value=_fixed(2026, 5, 19, 14, minute),
        ):
            auth_client.put(
                "/api/assets/upsert/",
                data={"mac_address": mac},
                format="json",
            )
    asset = models.Asset.objects.get(mac_address=mac)
    rows = list(asset.usage.all())
    assert len(rows) == 1
    assert rows[0].hour_14 == 3  # noqa: PLR2004


def _seed_assets_with_usage(prefix, count):
    for i in range(count):
        asset = models.Asset.objects.create(hostname=f"{prefix}-{i}.example.com")
        models.Usage.objects.create(asset=asset, day_of_week=0, hour_10=1)


def _count_usage_queries(captured):
    return sum(1 for q in captured.captured_queries if "blueflow_usage" in q["sql"])


def test_asset_list_usage_does_not_n_plus_one(auth_client):
    """Listing N assets fires a constant number of usage queries (prefetch active).

    Scope: this test only guards the Usage FK prefetch. AssetSerializer has
    additional, separate N+1 problems (notably the nested asset_tags and
    asset_vulnerabilities serializers) that are still unfixed. Asserting on
    the total query count would entangle this regression test with those
    pre-existing fan-outs, so we filter captured queries to the
    blueflow_usage table and assert only that the usage-specific count is
    flat across page sizes. When the other relations get prefetched, add
    sibling tests rather than broadening this one.
    """
    _seed_assets_with_usage("nplus1-base", 1)
    with CaptureQueriesContext(connection) as baseline:
        auth_client.get("/api/assets/")

    _seed_assets_with_usage("nplus1-scaled", 9)
    with CaptureQueriesContext(connection) as scaled:
        auth_client.get("/api/assets/")

    baseline_usage = _count_usage_queries(baseline)
    scaled_usage = _count_usage_queries(scaled)
    assert scaled_usage == baseline_usage, (
        f"N+1 regression on Asset.usage: 1 asset → {baseline_usage} usage queries, "
        f"10 assets → {scaled_usage} usage queries"
    )
