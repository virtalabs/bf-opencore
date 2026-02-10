"""Exceptions relevant to BlueFlow operation."""


class BlueFlowError(Exception):
    """Generic base exception class for BlueFlow errors."""


class TMSConnectorError(BlueFlowError):
    """Base exception for TMS connector errors."""


class AIMSConnectorError(BlueFlowError):
    """Base exception for AIMS connector errors."""


class ConnectorTaskError(BlueFlowError):
    """Thrown by connector tasks."""


class TMSAssetError(TMSConnectorError, ConnectorTaskError):
    """Thrown by the TMS connector.

    Circumstances include: TMS server-side failure when connecting to the TMS
    API, malformed data received from TMS, misconfiguration such as incorrect
    credentials.
    """


class AIMSAssetError(AIMSConnectorError, ConnectorTaskError):
    """Thrown by the AIMS connector.

    Circumstances include: AIMS server-side failure when connecting to the AIMS
    API, malformed data received from AIMS, misconfiguration such as incorrect
    credentials.
    """


class MalformedFileError(BlueFlowError, ValueError):
    """Thrown when importing a malformed file."""


class ConnectorConfigError(BlueFlowError):
    """Thrown by connector users.

    This happens if we try to use an insufficiently configured connector.
    """


class ConnectorRemoteError(BlueFlowError):
    """Thrown by connector users.

    This happens if we're not successful in connecting to remote server.
    """


class ConnectorOSError(BlueFlowError):
    """Thrown if connector causes OSError."""
