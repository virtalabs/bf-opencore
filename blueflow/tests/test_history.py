"""Asset history tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import json

import django.db.models.fields
import pytest
from rest_framework import status
from simple_history import utils as hist_utils

import blueflow.models as bf_mod

# bf_mod models do have 'objects' member, but it's being lazy loaded


################################################################
# Asset History


class TestAssetHistory:
    """Test that history works as expected.

    In particular, test that it works even when there's a
    change made by a "user".
    """

    @pytest.fixture(autouse=True)
    def setup_assets(self, db):
        """Register assets for all these tests."""
        asset_names = ["foo", "bar", "baz", "xyzzy", "spam", "ham", "eggs"]
        self.asset_record = {}
        for hostname in asset_names:
            self.asset_record[hostname] = bf_mod.Asset.objects.create(hostname=hostname)
            # Keep track of the id of 2 particular assets
            if hostname == "spam":
                self.spam_id = self.asset_record[hostname].id
            elif hostname == "eggs":
                self.eggs_id = self.asset_record[hostname].id

    def test_spam_id(self, auth_client):
        res = auth_client.get("/api/assets/", {"hostname__icontains": "spam"})
        spam = res.data["results"].pop()
        assert spam["id"] == self.spam_id

    def test_eggs_id(self, auth_client):
        res = auth_client.get("/api/assets/", {"hostname__icontains": "eggs"})
        eggs = res.data["results"].pop()
        assert eggs["id"] == self.eggs_id

    def test_spam_id_2(self, auth_client):
        res = auth_client.get(f"/api/assets/{self.spam_id}/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["id"] == self.spam_id

    def test_spam_simple_history(self, auth_client):
        res = auth_client.get(f"/api/assets/{self.spam_id}/history/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 2  # noqa: PLR2004  # Creation + initial rescore

    def test_history_simple_change(self, asset_edit_client):
        """History should change after a PATCH request."""
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "nospam"}),
            content_type="application/json",
        )
        assert res.status_code == status.HTTP_200_OK
        res = asset_edit_client.get(f"/api/assets/{self.spam_id}/history/")
        assert res.data["count"] == 3  # noqa: PLR2004  # Creation + initial rescore + patch

    def test_history_change_order(self, asset_edit_client):
        """History should be newest-first."""
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "spam_1"}),
            content_type="application/json",
        )
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "spam_2"}),
            content_type="application/json",
        )
        res = asset_edit_client.get(f"/api/assets/{self.spam_id}/history/")
        assert res.data["count"] == 4  # noqa: PLR2004  # C + R + (2 x patch)
        hostname_history = [
            (hi["hostname"], hi["risk_score"]) for hi in res.data["results"]
        ]
        # Extra 'spam' at the end due to initial rescore on asset creation
        assert hostname_history == [
            ("spam_2", 0.0),
            ("spam_1", 0.0),
            ("spam", 0.0),
            ("spam", None),
        ]

    def test_changelog_change_order(self, asset_edit_client):
        """ChangeLog should be newest-first."""
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "spam_1"}),
            content_type="application/json",
        )
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "spam_2"}),
            content_type="application/json",
        )
        res = asset_edit_client.get(f"/api/assets/{self.spam_id}/changelog/")
        # Remember: changelog is not paginated and thus we access it
        # directly as a list.
        assert len(res.data) == 4  # noqa: PLR2004  # C + R + (2 x patch)
        hostname_changelog = [(hi["hostname"], hi["risk_score"]) for hi in res.data]
        # changelog[-2] is because of initial rescore on asset creation.
        # Notice that unchanged values are None (compare with the
        # history in the test above.)
        assert hostname_changelog == [
            ("spam_2", None),
            ("spam_1", None),
            (None, 0.0),
            ("spam", None),
        ]

    def test_spam_simple_changelog(self, auth_client):
        """Changelog isn't paginated, like the history."""
        res = auth_client.get(f"/api/assets/{self.spam_id}/changelog/")
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data) == 2  # noqa: PLR2004  # Creation + initial rescore

    def test_changelog_simple_change(self, asset_edit_client):
        """Changelog is modified by PATCH request."""
        res = asset_edit_client.patch(
            f"/api/assets/{self.spam_id}/",
            json.dumps({"hostname": "nospam"}),
            content_type="application/json",
        )
        assert res.status_code == status.HTTP_200_OK
        res = asset_edit_client.get(f"/api/assets/{self.spam_id}/changelog/")
        assert len(res.data) == 3  # noqa: PLR2004  # Creation + initial rescore + patch


class TestOneFieldHistory:
    """Test that the 'History of one field' works.

    Also more complete tests of the history and changelog.
    """

    @pytest.fixture(autouse=True)
    def setup_history(self, asset_edit_client):
        """Prepare the data that the rest of the class will be using."""
        client = asset_edit_client
        self.change_sequence = [
            ("hostname", "Wile"),
            ("risk_score", 0.0),  # Automagically inserted upon creation
            ("serial_number", "1234567"),
            ("manufacturer", "Acme Medical Inc."),
            ("model", "E. Coyote"),
            ("hostname", "Willy"),
        ]
        self.history_keys = ("hostname", "serial_number", "manufacturer", "model")
        self.history_data = [
            ("Wile", None, None, None),
            ("Wile", None, None, None),
            ("Wile", "1234567", None, None),
            ("Wile", "1234567", "Acme Medical Inc.", None),
            ("Wile", "1234567", "Acme Medical Inc.", "E. Coyote"),
            ("Willy", "1234567", "Acme Medical Inc.", "E. Coyote"),
        ]
        self.changelog_data = [
            ("Wile", None, None, None),
            (None, None, None, None),
            (None, "1234567", None, None),
            (None, None, "Acme Medical Inc.", None),
            (None, None, None, "E. Coyote"),
            ("Willy", None, None, None),
        ]
        self.hostname_history = ["Wile", "Willy"]

        asset = client.post(
            "/api/assets/",
            json.dumps(dict(self.change_sequence[:1])),
            content_type="application/json",
        )
        self.asset_id = asset.data["id"]
        # Note: Skipping change_sequence element #1 ('risk_score') since
        # it's created behind the scenes.
        for new_data in self.change_sequence[2:]:
            _ = client.patch(
                f"/api/assets/{self.asset_id}/",
                json.dumps({new_data[0]: new_data[1]}),
                content_type="application/json",
            )

    def test_setup(self):
        """Basic checks."""
        assert len(self.change_sequence) == len(self.history_data)
        assert len(self.change_sequence) == len(self.changelog_data)
        assert len(self.hostname_history) == 2  # noqa: PLR2004

    def test_history_length(self, asset_edit_client):
        """Verify history length."""
        res = asset_edit_client.get(f"/api/assets/{self.asset_id}/history/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == len(self.change_sequence)

    def test_history_newestfirst(self, asset_edit_client):
        """History should be newest-first."""
        res = asset_edit_client.get(f"/api/assets/{self.asset_id}/history/")
        # NOTE: the history data as seen on the API is newest-first
        for hist_item, api_hist_item in zip(
            reversed(self.history_data), res.data["results"]
        ):
            hist_dict = {k: hist_item[i] for i, k in enumerate(self.history_keys)}
            api_hist_dict = {k: api_hist_item[k] for k in self.history_keys}
            assert hist_dict == api_hist_dict

    def test_changelog(self, asset_edit_client):
        """Changelog should be newest-first."""
        res = asset_edit_client.get(f"/api/assets/{self.asset_id}/changelog/")
        # NOTE: the changelog data as seen on the API is newest-first
        for hist_item, api_hist_item in zip(reversed(self.changelog_data), res.data):
            hist_dict = {k: hist_item[i] for i, k in enumerate(self.history_keys)}
            api_hist_dict = {k: api_hist_item[k] for k in self.history_keys}
            assert hist_dict == api_hist_dict

    def test_one_field_history(self, asset_edit_client):
        """Testing the one-field history.

        The API has yet to be finalized, so this is just a draft...
        """
        res = asset_edit_client.get(
            f"/api/assets/{self.asset_id}/history/?field=hostname"
        )
        # This gives us the history of one particular field.
        # NOTE: the history data as seen on the API is newest-first
        for hist_hostname, api_hist_item in zip(
            reversed(self.hostname_history), res.data
        ):
            assert hist_hostname == api_hist_item["hostname"]

    def test_history_default_null(self, asset_edit_client):
        """Field history for default-NULL field should show creation."""
        # We need access to the _meta field

        # get a field that is default NULL
        default_null_field = "last_scanned"
        field = bf_mod.Asset._meta.get_field(default_null_field)
        # The next two are tests of the model... and as such maybe they
        # belong in app/blueflow/tests/.  However, there are no test
        # files there, and arguably these are just "confirming
        # assumptions" not actually testing.  (It would be nice to have
        # a "warning" class of assertions... so that the rest of the
        # tests would actually be run even thought this failed.)
        assert field.null is True
        assert field.default is django.db.models.fields.NOT_PROVIDED

        # there should be a history entry referring to this asset's creation
        res = asset_edit_client.get(
            f"/api/assets/{self.asset_id}/history/?field={default_null_field}"
        )
        assert res.status_code == status.HTTP_200_OK
        # HHolm maintains that in this case the `len()` comparison conveys the
        # intention far better than a boolean check.
        #
        #             -- A foolish consistency is the hobgoblin of small minds.
        assert len(res.data) > 0

    def test_history_default_blank(self, asset_edit_client):
        """Field history for default-empty field should show creation."""
        # We need access to the _meta field

        # get a field that is default blank (empty string)
        non_null_field = "hostname"
        field = bf_mod.Asset._meta.get_field(non_null_field)
        assert field.null is True
        assert field.default is django.db.models.fields.NOT_PROVIDED

        res = asset_edit_client.get(
            f"/api/assets/{self.asset_id}/history/?field={non_null_field}"
        )
        assert res.status_code == status.HTTP_200_OK
        rj = res.data
        assert len(rj) == 2  # noqa: PLR2004
        assert rj[-1]["history_type"] == "+"


@pytest.mark.parametrize(
    ("field_name", "change_sequence"),
    [
        ("category", ["foo"]),
        ("category", [""]),
        ("category", ["foo", "bar"]),
        ("category", ["", "foo"]),
        ("category", ["foo", ""]),
        ("category", ["", "foo", ""]),
        ("category", ["foo", "", "foo"]),
        ("category", ["foo", "", "bar"]),
        ("risk_score", [1]),
        ("risk_score", [None]),
        ("risk_score", [1, 2]),
        ("risk_score", [None, 1]),
        ("risk_score", [1, None]),
        ("risk_score", [None, 1, None]),
        ("risk_score", [1, None, 1]),
        ("risk_score", [1, None, 2]),
    ],
)
def test_history_empty_values(asset_edit_client, field_name, change_sequence):
    """Records should appear in history even if empty at first."""
    create_json = json.dumps(
        {"hostname": "real_hostname", field_name: change_sequence[0]}
    )
    # update_list is a list of json objects/"dicts"
    update_list = [
        json.dumps({field_name: changeval}) for changeval in change_sequence[1:]
    ]
    # Create the asset, then patch it
    resp = asset_edit_client.post(
        "/api/assets/", create_json, content_type="application/json"
    )
    # asset_url is on the form '/api/assets/<n>/'
    asset_url = resp.data["url"]
    for update_json in update_list:
        asset_edit_client.patch(asset_url, update_json, content_type="application/json")
    # Get the history for that field
    res = asset_edit_client.get(f"{asset_url}history/?field={field_name}")
    # NOTE: the history data as seen on the API is newest-first; we
    # reverse it to make it look chronological.
    api_change_sequence = [hist_item[field_name] for hist_item in reversed(res.data)]
    change_seq_with_rescore = list(change_sequence)
    if field_name == "risk_score":
        # This is a little bit hairy but: Just after creation, the asset
        # will be rescored automagically.  This will set the risk_score
        # to 0.0 (since there are no associated risks).  Then later, the
        # risk_score will be patched via the API.
        change_seq_with_rescore.insert(1, 0.0)
    assert api_change_sequence == change_seq_with_rescore


################################################################
# Risk History


class TestAssetRiskHistory:
    """Test that risk history for individual assets works."""

    @pytest.fixture(autouse=True)
    def setup_history(self, db):
        """Prepare the history for the tests."""
        self.risk_scores = list(range(5))
        asset = bf_mod.Asset.objects.create(
            hostname="risky", risk_score=self.risk_scores[0]
        )
        for risk_score in self.risk_scores[1:]:
            # I'm allowed to save directly to asset.risk_score because it is
            # a *test* (in the interest of making it a *unit* test.)  In real
            # code we'd always add AssetRiskFactor objects and then rescore.
            asset.risk_score = risk_score
            asset.save()
            hist_utils.update_change_reason(asset, "Test History")
        self.asset_id = asset.id

    def test_history_complete(self, auth_client):
        res = auth_client.get(f"/api/assets/{self.asset_id}/history/")
        risk_scores_plus = list(self.risk_scores)
        # Insert 0.0 at location 1 due to the automagic rescore on creation.
        risk_scores_plus.insert(1, 0.0)
        assert res.data["count"] == len(risk_scores_plus)
        api_risk_scores = [hi["risk_score"] for hi in res.data["results"]]
        # NOTE: the history data as seen on the API is newest-first
        assert api_risk_scores == list(reversed(risk_scores_plus))

    def test_risk_history(self, auth_client):
        res = auth_client.get(f"/api/assets/{self.asset_id}/history/?field=risk_score")
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data) == len(self.risk_scores)
        api_risk_scores = [hi["risk_score"] for hi in res.data]
        # NOTE: the history data as seen on the API is newest-first
        assert api_risk_scores == list(reversed(self.risk_scores))
