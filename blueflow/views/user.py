"""ViewSet for users."""

import logging

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from waffle.mixins import WaffleSwitchMixin

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    # Few public methods; that's just how serializers work

    class Meta:
        """Wire serializer to the User model."""

        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "username",
            "is_superuser",
            "is_staff",
            "is_active",
            "date_joined",
        )


@extend_schema(exclude=True)
class UserViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """API endpoint that allows users to be viewed or edited."""

    waffle_switch = "core"

    queryset = User.objects.all()
    serializer_class = UserSerializer
