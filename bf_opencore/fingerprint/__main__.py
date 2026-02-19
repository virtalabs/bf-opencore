
"""Fingerprinting connector."""

from collections import OrderedDict
import logging
import click
import nmap
import celery
from django.apps import apps
from django.utils import timezone
from bf_opencore.exceptions import ConnectorTaskError
from bf_opencore.celery import celery_app
from bf_opencore.utils.hostname import hostname_ok, ip_address_ok


logger = celery.utils.log.get_task_logger(__name__)


CONNECTOR_SPEC = {
    "display_name": "Fingerprint",
    "description": """
Send traffic to an asset to guess what operating system it runs.

**WARNING:** this connector may send a significant amount of network traffic to
the target host.  This traffic is not entirely without risk; poorly configured
or poorly implemented networked devices may behave unpredictably as a result of
unexpected network traffic.

This connector uses [Nmap](https://nmap.org/) under the hood to perform OS
detection, which is documented in the [Nmap
book](https://nmap.org/book/osdetect.html).
    """,
    "kwargs": OrderedDict([
        ("hostname", {
            "default": None,
            "type": str,
            "help": "Hostname or IP address",
        }),
    ]),
    'settings': OrderedDict(),
}
DEFAULTS = {k: v["default"] for k, v in CONNECTOR_SPEC["kwargs"].items()}


@celery_app.task(bind=True)
def main(ctx, hostname):
    """Call this function from the Python API."""
    # The sh module dynamically loads members, which causes pylint to freak out
    # pylint: disable=no-member

    hostname = str(hostname)
    if not (ip_address_ok(hostname) or hostname_ok(hostname)):
        raise ConnectorTaskError('Bad hostname')

    # Build and run nmap command
    nm = nmap.PortScanner()
    nm.scan(hostname, sudo=True, arguments='-O')

    # Update the output field in the connectortask database table
    ctx.ct.print(nm.command_line())
    v_major, v_minor = nm.nmap_version()
    ctx.ct.print("Version %s.%s" % (v_major, v_minor))

    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    connector_task = ConnectorTask.objects.get(
        celery_task_id=ctx.request.id)
    # Update database
    Asset = apps.get_model('bf_opencore', 'Asset')
    Scan = apps.get_model('bf_opencore', 'Scan')
    last_pinged = timezone.now()
    for host in nm.all_hosts():
        asset, dummy = Asset.objects.get_or_create(ip_address=host)
        if 'tcp' in nm[host]:
            open_tcp_ports = list(nm[host]['tcp'].keys())
            ctx.ct.print(
                "%s: %s TCP ports open" % (host, open_tcp_ports))
            for port in open_tcp_ports:
                asset.open_ports_tcp_add(port)
        if 'osmatch' in nm[host]:
            os = nm[host]['osmatch'][0]['name']
            ctx.ct.print("%s: %s" % (host, os))
            asset.os = os
        asset.last_pinged = last_pinged
        asset.save()
        scan = Scan(
            asset=asset,
            connector_task=connector_task,
            num_vulnerabilities=0,
            date_scanned=last_pinged,
            num_plugins=0,
            provenance="Fingerprint ({})".format(nm.command_line()),
            external_url=None,
            )
        scan.save()


@click.command(context_settings={"help_option_names": ['-h', '--help']})
@click.argument("hostname", nargs=1)
def cli(hostname):
    """Command line interface."""
    logger.setLevel(logging.DEBUG)
    main.apply(kwargs={'hostname': hostname})


if __name__ == "__main__":
    cli()
