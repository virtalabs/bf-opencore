"""Disable all signals.

Lifted from https://gist.github.com/shibocuhk/fd0e3f5e2360c64bc9ce2efb254744f7
"""

from collections import defaultdict
from django.db.models.signals import pre_init, post_init, pre_save, \
    post_save, pre_delete, post_delete, pre_migrate, post_migrate


class DisableSignals():
    """Context manager that will disable all (or specified) signals.

    Example usage:
    with DisableSignals():
        user.save()  # will not call any signals

    with DisableSignals([post_save]):
        user.save()  # will not call any receivers for post_save signal

    NOTE: argument is given as a list of signals, even though there may
    be only one.
    """

    def __init__(self, disabled_signals=None):  # noqa=D107
        self.stashed_signals = defaultdict(list)
        self.disabled_signals = disabled_signals or [
            pre_init, post_init,
            pre_save, post_save,
            pre_delete, post_delete,
            pre_migrate, post_migrate,
        ]

    def __enter__(self):  # noqa=D105
        for signal in self.disabled_signals:
            self.disconnect(signal)

    def __exit__(self, exc_type, exc_val, exc_tb):  # noqa=D105
        for signal in list(self.stashed_signals.keys()):
            self.reconnect(signal)

    def disconnect(self, signal):
        """Put aside receivers for the given signal."""
        self.stashed_signals[signal] = signal.receivers
        signal.receivers = []

    def reconnect(self, signal):
        """Put receivers back in."""
        signal.receivers = self.stashed_signals.get(signal, [])
        del self.stashed_signals[signal]
