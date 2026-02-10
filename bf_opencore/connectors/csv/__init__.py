
"""CSV connector.

Reads a CSV file and loads each row into the database.  Any column header
that matches an asset attribute will be loaded.  Other columns are ignored.
"""

from .__main__ import main, CONNECTOR_SPEC
