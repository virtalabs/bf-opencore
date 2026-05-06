"""Search autocomplete for asset fields."""

import logging

from django.core.exceptions import FieldError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from blueflow.models import Asset

logger = logging.getLogger(__name__)


class AutocompleteAssetFieldViewSet(ViewSet):
    """Autocomplete a single Asset field."""

    # NOTE: Since this ViewSet doesn't have a proper queryset/associated
    #   model, it's not possible to check for permissions the
    #   automatic/Django way -- even checking the permissions causes an
    #   error.  We solve this by removing the standard
    #   DjangoModelPermissions class and sticking with the simple
    #   IsAuthenticated class.
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def list(request, *args, **kwargs):
        """Get all distinct values for a single Asset field."""
        params = request.GET.copy()

        # name of an Asset field to fetch all values of
        field = params.pop("field", None)
        if field is None:
            return Response([], status=status.HTTP_400_BAD_REQUEST)

        # QueryDict.pop() returns a list; we just want one item
        field = field[0]

        # what's left in request parameters: constraints.  for example, if
        # field is 'model', we'll be fetching all the distinct values for
        # Asset.model, but in fact we want to fetch all the distinct values for
        # Asset.model where Asset.manufacturer has a certain value.
        constraints = params.dict()

        isnull_p = f"{field}__isnull"
        try:
            vals = (
                Asset.objects.values(field)
                .distinct()
                .exclude(**{isnull_p: True})
                .order_by(field)
            )
            if constraints:
                vals = vals.filter(**constraints)
            return Response([str(val[field]) for val in vals])
        except FieldError:
            # raised for a bad field name or constraint field name
            return Response([], status=status.HTTP_400_BAD_REQUEST)
