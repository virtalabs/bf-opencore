"""Scalar API Reference HTML shell for OpenAPI documentation.

Loads the browser bundle from jsDelivr and points at the Spectacular schema
served at ``/api/schema/``. See https://scalar.com/products/api-references/
"""

from django.http import HttpRequest, HttpResponse

# Pin for reproducible UI; bump intentionally when upgrading Scalar.
_SCALAR_API_REFERENCE_JS = (
    "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.55.3/dist/browser/"
    "standalone.js"
)

_OPENAPI_RELATIVE_URL = "/api/schema/"
_PAGE_TITLE = "BlueFlow REST API"


def scalar_viewer(_request: HttpRequest) -> HttpResponse:
    """Return a minimal HTML page that embeds Scalar against our OpenAPI schema."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_PAGE_TITLE}</title>
  <style>
    body {{ margin: 0; padding: 0; }}
  </style>
</head>
<body>
  <noscript>
    Scalar requires JavaScript to browse the API reference.
  </noscript>
  <script
    id="api-reference"
    data-url="{_OPENAPI_RELATIVE_URL}"
    data-proxy-url=""
  ></script>
  <script src="{_SCALAR_API_REFERENCE_JS}"></script>
</body>
</html>
"""
    return HttpResponse(html.encode("utf-8"), content_type="text/html; charset=utf-8")
