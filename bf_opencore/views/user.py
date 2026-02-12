"""ViewSet for users."""

import logging

from django.contrib.auth.models import User

from rest_framework import viewsets, serializers
from waffle.mixins import WaffleSwitchMixin

logger = logging.getLogger(__name__)


class UserSerializer(serializers.HyperlinkedModelSerializer):
    """Serialize users."""

    # Few public methods; that's just how serializers work

    url = serializers.HyperlinkedIdentityField(view_name="api:user-detail")

    class Meta:
        """Wire serializer to the User model."""

        model = User
        fields = ('id', 'url', 'email', 'first_name', 'last_name', 'username',
                  'is_superuser', 'is_staff', 'is_active', 'date_joined')


class UserViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """API endpoint that allows users to be viewed or edited."""

    waffle_switch = "core"

    queryset = User.objects.all()
    serializer_class = UserSerializer
