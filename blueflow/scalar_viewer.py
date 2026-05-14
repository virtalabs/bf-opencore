r"""Scalar API Reference HTML shell for OpenAPI documentation.

Serves Scalar's browser bundle from Django staticfiles (Whitenoise manifest-safe)
and points ``data-url`` at the Spectacular schema via ``{% url %}``.

Vendored file: Scalar ``@scalar/api-reference@1.55.3`` —
``dist/browser/standalone.js``

To refresh the file after upgrading the pin::

    mkdir -p blueflow/static/blueflow/js \\
      && curl -fsSL \\
      -o blueflow/static/blueflow/js/scalar-api-reference-standalone-1.55.3.js \\
      "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.55.3/dist/browser/standalone.js"

See https://scalar.com/products/api-references/
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

_PAGE_TITLE = "BlueFlow REST API"


def scalar_viewer(request: HttpRequest) -> HttpResponse:
    """Render the Scalar docs page against this project's OpenAPI schema."""
    return render(
        request,
        "blueflow/scalar_docs.html",
        {"page_title": _PAGE_TITLE},
    )
