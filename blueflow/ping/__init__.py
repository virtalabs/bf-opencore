"""Ping integration."""

import logging
import re
import socket

import celery
import sh
from django.apps import apps
from django.utils import timezone

from blueflow.celery import celery_app
from blueflow.exceptions import IntegrationTaskError

# Configure logging.  Disable logging in sh module.
logger = celery.utils.log.get_task_logger(__name__)
logging.getLogger("sh").setLevel(logging.WARNING)


# TODO(legacy): review this when we are ready to setup the ping integration
# CONNECTOR_SPEC = {
#     "display_name": "Ping",
#     "description": "Ping an asset via ICMP ping.",
#     "kwargs": OrderedDict([
#         ("hostname", {
#             "default": None,
#             "type": str,
#             "help": "network host",
#         }),
#     ]),
#     'settings': OrderedDict(),
# }

PING_OPTS = [
    "-c 3",  # number of ping packets to send
]

# http://stackoverflow.com/questions/1418423/the-hostname-regex
# imperfect but good enough for input sanitization
PING_TARGET_RE = (
    r"^(?=.{1,255}$)[0-9A-Za-z](?:(?:[0-9A-Za-z]|-){0,"
    r"61}[0-9A-Za-z])?(?:\.[0-9A-Za-z](?:(?:[0-9A-Za-z]"
    r"|-){0,61}[0-9A-Za-z])?)*\.?$"
)


@celery_app.task(bind=True)
def main(ctx, hostname):
    """Call this function from the Python API."""
    # The sh module dynamically loads members, which causes pylint to freak out
    # pylint: disable=no-member

    host_or_ip_matcher = re.compile(PING_TARGET_RE)
    if not host_or_ip_matcher.match(hostname):
        raise IntegrationTaskError("Invalid target: '%s'" % hostname)

    # Try to resolve the hostname into an IP address so that we can create an
    # Asset for this host.  Caveats:
    #  - socket.gethostbyname() supports only IPv4
    #  - socket.gethostbyname() returns only the first IP address
    #  - socket.getaddrinfo() is apparently better behaved w/r/t name
    #    resolution order
    ipv4addr = None
    try:
        ipv4addr = socket.gethostbyname(hostname)
    except socket.gaierror as e:
        raise IntegrationTaskError("Cannot resolve hostname '%s'" % hostname) from e

    args = PING_OPTS
    args.append(hostname)

    ping_cmd = sh.Command("ping")
    ping_cmd = ping_cmd.bake(*args)
    try:
        output = ping_cmd()
    except sh.ErrorReturnCode as err:
        ctx.ct.print("Host '%s' is offline" % hostname)
        ctx.ct.print(err.stderr.decode("utf-8"))
        return err.exit_code

    stdout = output.stdout.decode("utf-8")
    stderr = output.stderr.decode("utf-8")
    if stdout:
        ctx.ct.print(stdout)
    if stderr:
        ctx.ct.print(stderr)
    ctx.ct.print("Host '%s' is online" % hostname)

    Asset = apps.get_model("blueflow", "Asset")
    asset, _ = Asset.objects.all().get_or_create(ip_address=ipv4addr)
    asset.last_pinged = timezone.now()
    asset.save()

    return 0
