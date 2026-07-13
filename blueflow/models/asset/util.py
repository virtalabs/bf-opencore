import datetime


def validate_tcp_port_range(_: list[int]) -> None:
    """Retained as an import target for historical migrations only."""


def default_timestamp() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)
