from django.core.management.base import BaseCommand
import requests
import json
import logging
from astropy.time import Time, TimezoneInfo
from tom_dataproducts.models import ReducedDatum, DataProduct
from tom_targets.models import Target
from custom_code.models import ReducedDatumExtra

logger = logging.getLogger(__name__)

class Command(BaseCommand):

    help = 'Imports ZTF photometry into SNEx2'

    def add_arguments(self, parser):
        parser.add_argument('--target_id', help='Ingest data for this target')

    def handle(self, *args, **options):

        def get_ztf_data(target):

            filters = {1: 'g_ZTF', 2: 'r_ZTF', 3: 'i_ZTF'}
            url = 'https://mars.lco.global/'
            
            ztf_name = next((name for name in target.names if 'ZTF' in name), None)
            if not ztf_name:
                return []
            
            request = {'queries':
                [
                    {'objectId': ztf_name}
                ]
            }
            try:
                r = requests.post(url, json=request)
                results = r.json()['results'][0]['results']
            
            except Exception as e:
                logger.info('Failed to get ZTF photometry for {}: {}'.format(ztf_name, e))
                return []

            dp, created = DataProduct.objects.get_or_create(
                target=target,
                observation_record=None,
                data_product_type='photometry',
                product_id='photometry_{}'.format(ztf_name)
            )
            dp.save() 
            data_product_id = int(dp.id)

            if not created:
                # Create ReducedDatumExtra to go along with these data 
                datum_extra_value = {
                    'data_product_id': data_product_id,
                    'instrument': 'ZTF',
                    'photometry_type': 'PSF'
                }
                rde = ReducedDatumExtra(
                    target=target,
                    data_type='photometry',
                    key='upload_extras',
                    value=json.dumps(datum_extra_value)
                )
                rde.save()

            for alert in results:
                if all([key in alert['candidate'] for key in ['jd', 'magpsf', 'fid', 'sigmapsf']]):
                    jd = Time(alert['candidate']['jd'], format='jd', scale='utc')
                    jd.to_datetime(timezone=TimezoneInfo())
                    value = {
                        'magnitude': alert['candidate']['magpsf'],
                        'filter': filters[alert['candidate']['fid']],
                        'error': alert['candidate']['sigmapsf']
                    }
                    rd, created = ReducedDatum.objects.get_or_create(
                        timestamp=jd.to_datetime(timezone=TimezoneInfo()),
                        value=value,
                        source_name=target.name,
                        source_location=alert['lco_id'],
                        data_type='photometry',
                        target=target,
                        data_product=dp)
                    rd.save()
            

            logger.info('Finished checking ZTF photometry for {}'.format(ztf_name))
            return [] 
        

        if options['target_id']:
            target = Target.objects.get(id=int(options['target_id']))
            get_ztf_data(target)
        
        else:
            target_query = Target.objects.all()
            for target in target_query:
                get_ztf_data(target)
