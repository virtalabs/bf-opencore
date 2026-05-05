"""test utilities."""

import os
import tempfile
from pathlib import Path


def path_nparent(path, n):
    """Return the n'th parent of path."""
    p = Path(path)
    for _ in range(n):
        p = p.parent
    return p


BLUEFLOW_HOME = path_nparent(__file__, 5)


def write_tempfile(text, *, bom_utf8=False):
    """Write text (ostensibly, CSV) to a temp file and return the filename."""
    csvfd, filename = tempfile.mkstemp(suffix=".csv")
    # The 'utf-8-sig' special encoding inserts the byte order mark
    # '0xef, 0xbb, 0xdf' at the beginning of the file (or strips it
    # off, if it's there when reading.)
    # NOTE: in general it is *discouraged* to use this BOM.  We use
    # it here only to test that we're robust against it if it is in
    # a file we come across.
    #
    # https://docs.python.org/3/library/codecs.html#encodings-and-unicode
    encoding = "utf-8-sig" if bom_utf8 else None
    os.close(csvfd)
    with Path(filename).open("w", encoding=encoding) as fh:
        fh.write(text)
    return filename
