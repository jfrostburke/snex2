from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = 'Changes proposal IDs for current ObservationRecords associated with active DynamicCadences (useful after semester changes or key projects end)'

    
    def add_arguments(self, parser):
        parser.add_argument('--oldid', help='The old ID to change')
        parser.add_argument('--newid', help='The new ID to change to')

    
    def handle(self, *args, **options):
        
        if not options['oldid'] or not options['newid']:

            logger.error('You need to provide both an old ID and a new ID')
            return None

        ### Get the recent ObservationRecords (that show up on the scheduling page)
        ### and change the proposal IDs
        obsrecordlist = [c.observation_group.observation_records.order_by('-created').first() for c in DynamicCadence.objects.filter(active=True)]

        record_ids_to_update = [o.id for o in obsrecordlist if o.parameters['proposal'] == options['oldid']]
        records_to_update = ObservationRecord.objects.filter(id__in=record_ids_to_update)

        for rec in records_to_update:
            rec.parameters['proposal'] = options['newid']
            rec.save()

        ### Do the same thing for the template records
        templatelist = [c.observation_group.observation_records.filter(observation_id='template').first() for c in DynamicCadence.objects.filter(active=True)]

        template_ids_to_update = [t.id for t in templatelist if t is not None and o.parameters['proposal'] == options['oldid']]
        templates_to_update = ObservationRecord.objects.filter(id__in=template_ids_to_update)

        for templ in templates_to_update:
            templ.parameters['proposal'] = options['newid']
            templ.save()

        logger.info('Finished updating current sequences from {} to {}'.format(options['oldid'], options['newid']))
