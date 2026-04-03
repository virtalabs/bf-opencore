"""Test CSV integration."""





class TestCTX:
    """Dummy class for testing.

    Sometimes we want to test 'process_csv' directly, and it needs a
    context with some methods.
    """

    # pylint: disable=too-few-public-methods

    class TestConnectorTask:
        """See parent class docstring."""

        display_name = "TestConnectorTask"

        def inc_progress(self):
            pass

        def error(self, *args, **kwargs):
            pass

        def print(self, *args, **kwargs):
            pass

    ct = TestConnectorTask()
