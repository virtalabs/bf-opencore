from django_extensions.db import models as django_extensions


class System(django_extensions.TimeStampedModel):
    """System is the parent to all assets and asset like things.

    It's primary role it to provide a centralized query for both
    internal and external assets and asset like things.
    """
