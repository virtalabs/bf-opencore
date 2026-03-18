"""Tests for structured logging configuration in base settings."""

import importlib


def test_default_log_level_is_info(monkeypatch):
    """Root logger defaults to INFO when LOG_LEVEL is not set."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    import project.settings.base as base

    importlib.reload(base)
    assert base.LOGGING["root"]["level"] == "INFO"


def test_log_level_env_var_is_respected(monkeypatch):
    """Root logger level is driven by LOG_LEVEL env var."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import project.settings.base as base

    importlib.reload(base)
    assert base.LOGGING["root"]["level"] == "DEBUG"


def test_plain_text_output_by_default(monkeypatch):
    """Console handler has no formatter when LOG_FORMAT is not set."""
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    import project.settings.base as base

    importlib.reload(base)
    assert "formatter" not in base.LOGGING["handlers"]["console"]


def test_json_formatter_when_log_format_json(monkeypatch):
    """Console handler uses JSON formatter when LOG_FORMAT=json."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    import project.settings.base as base

    importlib.reload(base)
    assert base.LOGGING["handlers"]["console"].get("formatter") == "json"


def test_console_handler_writes_to_stdout(monkeypatch):
    """Console handler is always configured to write to stdout."""
    import project.settings.base as base

    importlib.reload(base)
    assert base.LOGGING["handlers"]["console"]["stream"] == "ext://sys.stdout"
