"""test utilities."""

import os
import tempfile
from pathlib import Path


def path_nparent(path, n):
    """Return the n'th parent of path."""
    for _ in range(n):
        path = str(Path(path).parent)
    return path


BLUEFLOW_HOME = path_nparent(__file__, 5)


def write_tempfile(text, *, bom_utf8=False):
    """Write text (ostensibly, CSV) to a temp file and return the filename."""
    csvfd, filename = tempfile.mkstemp(suffix=".csv")
    # 'utf-8-sig' inserts/strips the BOM (0xef 0xbb 0xbf); discouraged in
    # general but tested here to verify robustness against files that carry it.
    # https://docs.python.org/3/library/codecs.html#encodings-and-unicode
    encoding = "utf-8-sig" if bom_utf8 else None
    with os.fdopen(csvfd, "w", encoding=encoding) as fh:
        fh.write(text)
    return filename
