"""Prism callback URL construction for Viper integration upload."""

from __future__ import annotations

import os
from urllib.parse import quote

DEFAULT_INTEGRATION_TOKEN = "contract-test-token"
INTEGRATION_UPLOAD_PATH = "/assets/integrationUpload/{token}"


def build_prism_callback_url(
    base_url: str,
    integration_token: str | None = None,
) -> str:
    """Build callback URL for Prism mock (base + path, with path params filled)."""
    token = integration_token or os.environ.get(
        "VIPER_INTEGRATION_TOKEN", DEFAULT_INTEGRATION_TOKEN
    )
    encoded_token = quote(token, safe="")
    path = INTEGRATION_UPLOAD_PATH.replace("{token}", encoded_token)
    base = base_url.rstrip("/")
    return f"{base}{path}"
