"""API metadata tests.

Ensure that we can access API docs and API schema.
"""

from http import HTTPStatus


def test_get_api_docs(auth_client):
    """Test that we can get the api docs."""
    api_docs = auth_client.get("/api/docs/")
    assert HTTPStatus.OK <= api_docs.status_code < HTTPStatus.MULTIPLE_CHOICES


def test_get_api_schema(auth_client):
    """Test that we can get the api schema."""
    api_schema = auth_client.get("/api/schema/")
    assert HTTPStatus.OK <= api_schema.status_code < HTTPStatus.MULTIPLE_CHOICES
