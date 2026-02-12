"""ViewSet for conector tasks."""

import logging
from collections import OrderedDict
import django_filters
from rest_framework import mixins, viewsets, serializers
from waffle.mixins import WaffleSwitchMixin
from bf_opencore.models import Connector


logger = logging.getLogger(__name__)


class ConnectorSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes Connector objects.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="api:connector-detail")
    page_url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:connector")

    class Meta:  # noqa
        model = Connector

        # Fields defined in the schema that are read-only
        read_only_fields = (
            'id',
            'celery_task_name',
            'risk_factor_params',
        )

        # Fields defined in the schema that are writeable
        connector_fields = (
            'settings',
            'enabled',
        )

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            'url',
            'page_url',
            'display_name',
            'description',
            'hidden',
            'kwargs',
            'settings_spec',
        )

        fields = connector_fields + read_only_fields + computed_fields

    def __init__(self, *args, **kwargs):
        """Override __init__ in order to modify the fields."""
        super(ConnectorSerializer, self).__init__(*args, **kwargs)
        request = kwargs['context']['request']
        if request is None:
            # Not a normal request, so it has no "user".
            # This happens e.g. when accessing /api/docs/
            return
        if not request.user.has_perm('blueflow.view_connector_settings'):
            settings_field = self.fields.pop('settings', None)
            if settings_field is None:
                logger.error("No settings field, cannot remove")

    def validate(self, attrs):
        """Verify settings are consistent with CONNECTOR_SPEC.

        NOTE: this has a side effect: If there's an entry in a
              connector.settings that is not in the
              connector.settings_spec, it *will be removed* from the
              settings.  I think this is OK.
        """
        connector = self.instance
        settings = attrs.get('settings', dict)
        errors = OrderedDict()

        # Check types
        validated_settings = {}
        for setting, spec in connector.settings_spec_internal_value.items():
            if setting in settings:
                setting_type = spec['type']
                setting_value = settings[setting]
                errmsg = "'{}': bad type, must be '{}'".format(
                    setting_value, setting_type.__name__)
                try:
                    validated_value = setting_type(setting_value)
                except ValueError:
                    logger.warning("Setting '%s': %s", setting, errmsg)
                    errors[setting] = [errmsg]
                else:
                    validated_settings[setting] = validated_value
            else:
                logger.warning("Setting '%s': Did not receive a value, "
                               "using the current value '%s'",
                               setting, connector.settings[setting])
                validated_settings[setting] = connector.settings[setting]

        if errors:
            raise serializers.ValidationError(errors)

        ignored_settings = settings.keys() - validated_settings.keys()
        if ignored_settings:
            logger.warning("Ignoring incoming setting(s): %s",
                           {k: v for k, v in settings.items()
                            if k in ignored_settings})

        attrs['settings'] = validated_settings
        return attrs


class ConnectorFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:  # noqa
        model = Connector

        fields = {
            'id': ['exact'],
            'celery_task_name': ['exact'],
        }


class ConnectorViewSet(WaffleSwitchMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Connectors have limited methods via the API.

    They may be listed/retrieved (GET) and also updated (PATCH, PUT),
    but they may not be created (POST) nor destroyed (DELETE).
    """

    waffle_switch = "core"

    # Thus we can't use the regular ModelViewSet -- instead we inherit
    # from ReadOnlyModelViewSet but add the UpdateModel mixin.

    # Connector model does have objects...
    queryset = Connector.objects.all()
    serializer_class = ConnectorSerializer

    filterset_class = ConnectorFilter
