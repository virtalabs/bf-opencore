"""Unit tests for outbound Viper callback auth helpers in celery.tasks."""

import logging

import pytest

from blueflow.celery.tasks import callback_host_allowlisted, viper_request_headers


def test_skips_bearer_without_allowlist(monkeypatch):
    monkeypatch.setenv("VIPER_API_TOKEN", "secret-token")
    monkeypatch.delenv("VIPER_CALLBACK_ALLOWED_HOSTS", raising=False)
    headers = viper_request_headers("https://example.com/viper/webhook/")
    assert "Authorization" not in headers


def test_sends_bearer_when_allowlisted(monkeypatch):
    monkeypatch.setenv("VIPER_API_TOKEN", "secret-token")
    monkeypatch.setenv("VIPER_CALLBACK_ALLOWED_HOSTS", "example.com")
    headers = viper_request_headers("https://example.com/viper/webhook/")
    assert headers["Authorization"] == "Bearer secret-token"


@pytest.mark.parametrize(
    ("url", "env", "expected"),
    [
        ("not-a-url", "", False),
        ("https://example.com", "", False),
        ("https://EXAMPLE.COM", "example.com", True),
        ("https://api.viper.test", "example.com, api.viper.test", True),
    ],
)
def test_callback_host_allowlisted(monkeypatch, url: str, env: str, expected: bool):
    monkeypatch.setenv("VIPER_CALLBACK_ALLOWED_HOSTS", env)
    assert callback_host_allowlisted(url) == expected


def test_warns_when_host_not_allowlisted(monkeypatch, caplog):
    monkeypatch.setenv("VIPER_API_TOKEN", "secret-token")
    monkeypatch.delenv("VIPER_CALLBACK_ALLOWED_HOSTS", raising=False)
    with caplog.at_level(logging.WARNING, logger="blueflow.celery.tasks"):
        viper_request_headers("https://example.com/viper/webhook/")
    assert "skipping Bearer auth" in caplog.text
