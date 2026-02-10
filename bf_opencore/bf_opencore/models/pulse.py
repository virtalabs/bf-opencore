"""BlueFlow Pulse models."""

from functools import reduce
import logging
from operator import and_, or_

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone
from simple_history.models import HistoricalRecords
from django.apps import apps
from bf_opencore.bf_opencore.utils import quarter_start, prev_quarter_start, NullUnlessChanged

logger = logging.getLogger(__name__)


class PulseFeedItemManager(models.Manager):
    """Custom manager to query for PulseFeedItem history."""

    def closed_list(self, start, end):
        """Return a list of 'closed' items, within a date range."""
        # PulseFeedItem.history is a manager so has all the members we need
        qset_a = (PulseFeedItem.history
                  .order_by('-history_date')
                  .filter(history_date__range=[start, end])
                  .annotate(status__changed=NullUnlessChanged('status')))
        return [pfih for pfih in qset_a
                if pfih.status__changed == PulseFeedItem.STATUS_CLOSED]

    def closed_quarterly(self, quarters):
        """Return list of lists of closed PulseFeedItems.

        One list per quarter.
        """
        quarters = int(quarters)
        if quarters < 1:
            logger.warning("Not returning data for < 1 quarters")
            return []
        if quarters > 1000:
            logger.warning("Refuse to get more than 250 years worth of data")
            quarters = 1000
        quarterly_list = []

        today = timezone.now()
        qtr_start = quarter_start(today)
        current_quarter_closed = self.closed_list(qtr_start, today)
        quarterly_list.append((qtr_start, current_quarter_closed))
        fetched = 1
        while fetched < quarters:
            prev_qtr_start = prev_quarter_start(qtr_start)
            quarterly_list.append(
                (prev_qtr_start, self.closed_list(prev_qtr_start, qtr_start)))
            fetched += 1
            qtr_start = prev_qtr_start
        return quarterly_list


class PulseFeedItem(models.Model):
    """Represents an item from the Pulse feed.

    Feed items here are essentially mirrored from the Pulse feed by the
    Pulse connector.

    Queries we expect:
     - Get the full list of feed items
     - Get feed items updated since a certain date
     - Get feed items pertinent to a specific manufacturer
     - Get feed items pertinent to a specific manufacturer & model
     - Autocomplete feed items by title
    """

    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in-progress'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_CLOSED, 'Closed'),
    )

    external_pulse_id = models.IntegerField(unique=True, null=False,
                                            editable=False)
    date_last_updated = models.DateTimeField(null=False, editable=False)
    title = models.TextField(null=False, editable=False)

    # fields used to track status of a feed item: have we dealt with this? who
    # dealt with it, when, and what did they say about it?
    status = models.CharField(
        max_length=32,
        null=False,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    notes = models.TextField(null=True, blank=True)

    # crappy caches of affected manufacturers & models.  since these are just
    #  flat lists (as opposed to big piles of logic we can AND & OR),
    # they aren't quite as expressive as the 'affected' field of the JSON
    # feed blob.  see search_query().
    affected_manufs = ArrayField(models.TextField(blank=True, null=True),
                                 null=True, editable=False)
    affected_models = ArrayField(models.TextField(blank=True, null=True),
                                 null=True, editable=False)

    # raw JSON data from alerts (disk is cheap)
    json = models.JSONField(blank=True, null=True, editable=False)

    history = HistoricalRecords()
    objects = PulseFeedItemManager()

    def __str__(self):  # noqa
        return "<PFI {}:{} {} '{}'>".format(self.id,
                                            self.external_pulse_id,
                                            self.date_last_updated,
                                            self.title)

    def _search_query(self):
        """Return an asset search query as a Django query (Q) object.

        Result can be passed to Asset.objects.filter().

        @returns: a Django query (Q) object suitable for passing to
            Asset.objects.filter(), or None if self.json is None or
            malformed.
        """
        if self.json is None:
            return None

        try:
            affected = self.json['data']['affected']
            if not affected:
                return None
        except KeyError:
            return None

        # at this point there's at least one condition to match on, or else
        # we would have already returned None

        # now we'll iterate over the list of matching conditions.  most feed
        # items will have one set of matching conditions (e.g., "manufacturer
        #  is FooCorp and model is XYZ5000"), but multiple conditions are
        # possible (e.g., "manufacturer is FooCorp and model is XYZ5000,
        # or manufacturer is AcquiredFooCorp and model is XYZ50000") and
        # these are to be logically ORed.
        disjuncts = []

        for compound_condition in affected:
            # to end up with a single condition, we logically AND the
            # matching conditions (e.g., "manufacturer is FooCorp" and "model
            #  is XYZ5000").  each of these conditions is actually a
            # disjunction, so we can reasonably end up with "manufacturer is
            # FooCorp and model is either XYZ5000 or XYZ6000".
            conjuncts = []

            cond_manufs = compound_condition.get('manufacturer')
            if cond_manufs:
                conjuncts.append(
                    reduce(or_, [models.Q(manufacturer__iregex=m)
                                 for m in cond_manufs]))

            cond_models = compound_condition.get('model')
            if cond_models:
                conjuncts.append(
                    reduce(or_, [models.Q(model__iregex=m)
                                 for m in cond_models]))

            # match on affected app_sw_version, which is, like manufacturer and
            # model, a set of matching criteria:
            #   ['lt', '8.0.1']  # version "less than" (per postgres) 8.0.1
            #   ['gte', '8.1.3'] # version "greater than or equal to" 8.1.3
            #   '8.0.2'          # version equal 8.0.2
            # the matching w/ comparators is clunky because it depends on
            # Postgres to compare strings like '8.0.2' and '8.1.3',
            # which happens lexically but not in a way that necessarily
            # respects semantic versioning (so '8.0.2' > '10.1.3').
            cond_sw_versions = compound_condition.get('app_sw_version')
            if cond_sw_versions:
                conds = []
                for ver in cond_sw_versions:
                    if isinstance(ver, str):
                        conds.append(models.Q(app_sw_version=ver))
                    elif isinstance(ver, list) and len(ver) == 2:
                        cmp, val = ver
                        if cmp in ('lte', 'lt', 'gte', 'gt'):
                            conds.append(models.Q(**{
                                'app_sw_version__{}'.format(cmp): val,
                            }))
                        else:
                            logger.warning('Invalid app_sw_version comparator '
                                           '%s; skipping app_sw_version '
                                           'comparison.', cmp)
                    else:
                        logger.warning('Invalid app_sw_version condition %s',
                                       ver)

                if conds:
                    # also match on null app_sw_version b/c we don't know
                    conds.append(models.Q(app_sw_version__isnull=True))
                    conds.append(models.Q(app_sw_version=''))
                    conjuncts.append(reduce(or_, conds))

            # match exactly on operating system
            cond_oses = compound_condition.get('os')
            if cond_oses:
                # OS matches one of these OS regexes, or is null
                os_conds = [models.Q(os__iregex=o) for o in cond_oses]
                os_conds.append(models.Q(os__isnull=True))
                conjuncts.append(reduce(or_, os_conds))

            if conjuncts:
                disjuncts.append(reduce(and_, conjuncts))

        return reduce(or_, disjuncts) if disjuncts else None

    def asset_qset(self):
        """Get a set of assets tied to this PulseFeedItem's Vulnerability.

        If this PulseFeedItem isn't of type "vulnerability", degenerates to
        asset_search_qset(), which uses this PulseFeedItem's search criteria
        (such as "manufacturer is FooCorp") to search for affected assets.
        """
        if self.json['type'] != 'vulnerability':
            return self.asset_search_qset()

        # assemble a query for assets via this PulseFeedItem's vulnerabilities
        Asset = apps.get_model('bf_opencore', 'Asset')
        vulns = Asset.objects.none()

        for vuln in self.vulnerabilities.all():
            vulns |= Asset.objects.filter(
                asset_vulnerabilities__vulnerability=vuln,
                asset_vulnerabilities__date_remediated__isnull=True,
                asset_vulnerabilities__date_ignored__isnull=True)
        return vulns

    def asset_search_qset(self):
        """Get a set of assets by this PulseFeedItem's matching criteria."""
        Asset = apps.get_model('bf_opencore', 'Asset')
        return Asset.objects.filter(self._search_query())

    def reload_from_json(self):
        """Reload several data fields from self.json."""
        try:
            self.title = self.json['title']
        except KeyError:
            logger.warning('Missing title in Pulse feed item')

        try:
            affected = self.json['data']['affected']
        except KeyError:
            logger.warning('Missing "affected" stanza in Pulse feed item')
        else:
            manufs = set()
            affmodels = set()
            for aff in affected:
                if 'manufacturer' in aff:
                    manufs.update(aff['manufacturer'])
                if 'model' in aff:
                    affmodels.update(aff['model'])
            if manufs:
                self.affected_manufs = list(manufs)
            if affmodels:
                self.affected_models = list(affmodels)

    @property
    def last_notes_editor(self):
        """Who last edited this object's notes field."""
        most_recent = self.history.latest()
        if most_recent is None:
            return None
        return most_recent.history_user.username

    @property
    def last_notes_date(self):
        """When was this object's notes field last edited."""
        most_recent = self.history.latest()
        if most_recent is None:
            return None
        return most_recent.history_date.isoformat()
