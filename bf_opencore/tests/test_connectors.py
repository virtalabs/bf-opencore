"""Connector and -Task API tests."""

import json
from connectors.management.commands.create_connectors import create_connectors
import blueflow.models as bf_mod


def test_get_connectors(admin_client):
    """Check that we can get connectors."""
    create_connectors()
    response = admin_client.get('/api/connectors/',
                                # json.dumps({'name': None}),
                                content_type='application/json')
    connectors = response.data['results']
    # Don't know how many connectors we have but for sure we have at least 2
    assert len(connectors) >= 2


def test_create_disabled_connector_task(admin_client):
    """Fail to create a ConnectorTask for a disabled Connector."""
    create_connectors()

    # Django models do have members

    # Disable connector
    connector = bf_mod.Connector.objects.get(id="true")
    connector.enabled = False
    connector.save()

    # Try to run disabled connector
    response = admin_client.post(
        "/api/connectortasks/",
        json.dumps({
            "connector": "/api/connectors/true/",
            "kwargs": {},
        }),
        content_type='application/json',
    )
    assert response.status_code == 201
    assert response.data["status"] == "Failed"
