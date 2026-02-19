"""Exceptions relevant to BlueFlow operation."""


class BlueFlowError(Exception):
    """Generic base exception class for BlueFlow errors."""

class IntegrationTaskError(BlueFlowError):
    """Thrown by integration tasks."""


class MalformedFileError(BlueFlowError, ValueError):
    """Thrown when importing a malformed file."""


class IntegrationConfigError(BlueFlowError):
    """Thrown by integration users.

    This happens if we try to use an insufficiently configured integration.
    """


class IntegrationRemoteError(BlueFlowError):
    """Thrown by integration users.

    This happens if we're not successful in connecting to remote server.
    """


class IntegrationOSError(BlueFlowError):
    """Thrown if integration causes OSError."""
