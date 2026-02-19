"""Portscan integration"""

import logging
import re
import celery
import sh
from django.apps import apps
from django.utils import timezone
from simple_history import utils as hist_utils
from bf_opencore.exceptions import IntegrationTaskError
from bf_opencore.celery import celery_app
from bf_opencore.utils.hostname import hostname_ok, ip_address_ok


# Configure logging.  Disable logging in sh module.
logger = celery.utils.log.get_task_logger(__name__)
logging.getLogger('sh').setLevel(logging.WARNING)


# TODO: review this when we are ready to setup the portscan integration
# CONNECTOR_SPEC = {
#     "display_name": "Port Scan",
#     "description": """
# Scan an asset for open TCP ports.
# 
# This connector's behavior is equivalent to running `nmap -v -sS <target>` to
# execute a TCP SYN scan of the target.
#     """,
#     "kwargs": OrderedDict([
#         ("hostname", {
#             "default": None,
#             "type": str,
#             "help": "Hostname or IP address",
#         }),
#     ]),
#     'settings': OrderedDict(),
# }
# DEFAULTS = {k: v["default"] for k, v in CONNECTOR_SPEC["kwargs"].items()}


@celery_app.task(bind=True)
def main(ctx, hostname):
    """Call this function from the Python API."""
    # pylint: disable=too-many-locals

    raise NotImplementedError("Connectors have been removed")
    hostname = str(hostname)
    if not (ip_address_ok(hostname) or hostname_ok(hostname)):
        raise IntegrationTaskError('Bad hostname')

    # Build nmap command
    command = ('nmap', '-v', '-sS', hostname)

    # Run nmap command
    # pylint: disable=too-many-function-args
    output = sh.sudo(*command)
    # ctx.ct.print('Portscan command: {}'.format(' '.join(command)))

    # Parse output
    # Match lines that look like this:
    # Discovered open port 22/tcp on 127.0.0.1
    pattern = re.compile(r"Discovered open port (\d+)/([^\s]+) on ([0-9\.]+)")
    matches = pattern.findall(output.stdout.decode('utf-8'))
    last_scanned = timezone.now()
    scanned_assets = {}
    new_ports = 0
    Asset = apps.get_model('bf_opencore', 'Asset')
    for match in matches:
        (port, protocol, ip) = match
        if protocol != 'tcp':
            continue
        asset, _ = Asset.objects.get_or_create(ip_address=ip)
        logger.info('Will add port %s to asset %s', port, asset.id)
        if int(port) not in asset.open_ports_tcp:
            new_ports += 1
        scanned_assets.setdefault(asset, []).append(int(port))

    if scanned_assets:
        ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
        connector_task = ConnectorTask.objects.get(
            celery_task_id=ctx.request.id)
    Scan = apps.get_model('bf_opencore', 'Scan')
    for asset, ports in scanned_assets.items():
        asset.open_ports_tcp_add(ports)
        asset.last_scanned = last_scanned
        asset.save()
        hist_utils.update_change_reason(asset, 'Nmap port scan')
        scan = Scan(
            asset=asset,
            connector_task=connector_task,
            date_scanned=last_scanned,
            num_vulnerabilities=0,
            num_plugins=0,
            provenance="Portscan ({})".format(' '.join(command)),
            external_url=None,
            )
        scan.save()

    if new_ports:
        Alert = apps.get_model('bf_opencore', 'Alert')
        Alert.objects.create(
            text=f'Found {new_ports} new open ports',
            connectortask=connector_task)

    stdout = output.stdout.decode('utf-8')
    stderr = output.stderr.decode('utf-8')
    if stdout:
        ctx.ct.print(stdout)
    if stderr:
        ctx.ct.print(stderr)

    # Return nmap's return value
    return output.exit_code
