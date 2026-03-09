"""test utilities."""

import os


def path_nparent(path, n):
    """Return the n'th parent of path."""
    for _ in range(n):
        path = os.path.dirname(path)
    return path


BLUEFLOW_HOME = path_nparent(__file__, 5)


def write_tempfile(text, bom_utf8=False):
    """Write text (ostensibly, CSV) to a temp file and return the filename."""
    csvfd, filename = tempfile.mkstemp(suffix=".csv")
    if bom_utf8:
        # The 'utf-8-sig' special encoding inserts the byte order mark
        # '0xef, 0xbb, 0xdf' at the beginning of the file (or strips it
        # off, if it's there when reading.)
        # NOTE: in general it is *discouraged* to use this BOM.  We use
        # it here only to test that we're robust against it if it is in
        # a file we come across.
        #
        # https://docs.python.org/3/library/codecs.html#encodings-and-unicode
        encoding = "utf-8-sig"
    else:
        encoding = None
    with open(csvfd, "w", encoding=encoding) as fh:
        fh.write(text)
    return filename
