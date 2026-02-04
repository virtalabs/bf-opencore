"""API metadata tests.

Ensure that we can access API docs and API schema.
"""


def test_get_api_docs(auth_client):
    """Test that we can get the api docs."""
    api_docs = auth_client.get('/api/docs/')
    assert 200 <= api_docs.status_code < 300


def test_get_api_schema(auth_client):
    """Test that we can get the api schema."""
    api_schema = auth_client.get('/api/schema/')
    assert 200 <= api_schema.status_code < 300
