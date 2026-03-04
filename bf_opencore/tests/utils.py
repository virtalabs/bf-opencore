"""Test utils."""


class AttrDict(dict):
    """This is a class that lets you index a `dict` using attributes, not keys.

    I.e., you could do

    >>> myd = {'a': 3, 'b': 1}
    >>> assert myd.a == 3

    rather than

    >>> assert myd['a'] == 3

    NOTE: it is a dangerous class, but well suited for response data
    since it will almost always refer to a database row / Model entry,
    in which the fields will always be valid as attributes, in addition
    to dictionary keys.
    """

    def __init__(self, *args, **kwargs):
        """See class docstring."""
        super().__init__(*args, **kwargs)
        self.__dict__ = self
