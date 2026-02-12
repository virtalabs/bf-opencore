"""DRF view for interacting with (external) Nessus."""

import logging

from rest_framework import viewsets, serializers, permissions, status
from rest_framework.response import Response
from waffle.mixins import WaffleSwitchMixin

from bf_opencore import exceptions

try:
    from connectors.nessusimport.nessus_api import NessusConnection
except ImportError:
    NessusConnection = None


logger = logging.getLogger(__name__)


class NessusBrowseSerializer(serializers.Serializer):
    """Serialize a response from Nessus."""

    nessus_response = serializers.JSONField(read_only=True)

    def create(self, validated_data):
        """Dummy."""
        raise serializers.ValidationError("Cannot create.")

    def update(self, instance, validated_data):
        """Dummy."""
        raise serializers.ValidationError("Cannot update.")


class NessusBrowseViewSet(WaffleSwitchMixin, viewsets.ViewSet):
    """Interact with Nessus.

    This API will be used to interact with Nessus, browse 'scans' and
    historical scans.
    """

    waffle_switch = "core"

    serializer = NessusBrowseSerializer
    # NOTE: if we want to use a "permission" (e.g., "edit connector" or
    #   "edit connectortask" for this we have to implement something
    #   custom.  The regular permissions are closely tied to a
    #   model... which we don't have.
    #
    #   More specifically: Since this ViewSet doesn't have a proper
    #   queryset/associated model, it's not possible to check for
    #   permissions the automatic/Django way -- even checking the
    #   permissions causes an error.  We solve this by removing the
    #   standard DjangoModelPermissions class and sticking with the
    #   simple IsAuthenticated class.
    permission_classes = (permissions.IsAuthenticated,)

    def list(self, request):
        """Send request to Nessus, return data.

        This is a 'list' so that it shows up in the DRF API.

        Pass instructions as query parameters (we need only 2 cases --
        we don't need 'details' as we had originally documented):

         - *List of scans*
             (https://cloud.tenable.com/api#/resources/scans/list)

           Nessus API  "scans list" `GET /scans`

           BlueFlow API `GET /nessusbrowse/?action=scans`

        - *History for one particular scan*
             (https://cloud.tenable.com/api#/resources/scans/details),

           Nessus API ["scans details"] `GET /scans/{scan_id}`

           BlueFlow API `GET /nessusbrowse/?action=history&scan_id={scan_id}`

        (For completeness: 'scan details' uses the same Nessus API, but
        you'd provide the history ID as a query parameter,
        `GET /scans/{scan_id}&history_id={history_id}`.)
        """
        if NessusConnection is None:
            return Response(
                {"detail": "Connectors not available."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # history = request.query_params.get('history')
        try:
            action = request.query_params['action']
        except KeyError:
            raise serializers.ValidationError(
                "No 'action' in query params '{}', don't know what to do"
                "".format(request.query_params))
        try:
            nc = NessusConnection()
        except exceptions.ConnectorConfigError as err:
            response = {'detail': 'Bad configuration: {}'.format(err)}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        response = {'nessus_response': None}
        if action == 'scans':
            # Get list of scans
            try:
                scans = nc.scans()
            except exceptions.ConnectorRemoteError as err:
                raise serializers.ValidationError(err)
            response['nessus_response'] = {'scans': scans}
        elif action == 'history':
            try:
                scan_id = request.query_params['scan_id']
            except KeyError:
                raise serializers.ValidationError(
                    "No 'scan_id' in query params '{}', cannot get history"
                    "".format(request.query_params))
            try:
                scan_id = int(scan_id)
            except ValueError:
                raise serializers.ValidationError(
                    "Invalid parameter scan_id='{}'".format(scan_id))
            try:
                history = nc.history(scan_id)
            except exceptions.ConnectorRemoteError as err:
                raise serializers.ValidationError(err)
            response['nessus_response'] = {'history': history}
        elif action == 'details':
            # response['nessus_response'] = {'details': 'not yet implemented'}
            raise serializers.ValidationError("details: not yet implemented")
        else:
            raise serializers.ValidationError(
                "No response for query params '{}'"
                "".format(request.query_params))
        return Response(response)
