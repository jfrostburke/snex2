from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
import os
import json
import time
from astropy.time import Time
import requests
import logging
from custom_code.models import TNSTarget


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    
    help = 'Ingests TNS Targets into SNEx2'

    def handle(self, *args, **kwargs):

        ### Get list of recent candidates
        
        api_key = os.environ['TNS_APIKEY']
        tns_id = os.environ['TNS_APIID']
        days_ago = 0.042
        search_url = "https://www.wis-tns.org/api/get/search"
        obj_url = "https://www.wis-tns.org/api/get/object"

        date = str(datetime.utcnow() - timedelta(days=days_ago))
        json_list = {'public_timestamp': date}

        obj_list = requests.post(search_url, headers={'User-Agent': 'tns_marker{"tns_id":'+str(tns_id)+', "type":"bot", "name":"SNEx_Bot1"}'}, data={'api_key': api_key, 'data': json.dumps(json_list)})
        obj_list = json.loads(obj_list.text)['data']['reply']

        if not obj_list:
            logger.info('No TNS targets found, have a good day!')
            return []

        for obj in obj_list:
            
            is_target = TNSTarget.objects.filter(name=obj['objname']).first()
            if is_target:
                logger.info('{name} already ingested, skipping'.format(name=obj['objname']))
                continue

            json_list = {'objname': obj['objname'], 'photometry': 1, 'spectra': 0}
            obj_data = requests.post(obj_url, headers={'User-Agent': 'tns_marker{"tns_id":'+str(tns_id)+', "type":"bot", "name":"SNEx_Bot1"}'}, data={'api_key': api_key, 'data': json.dumps(json_list)})
            obj_data = json.loads(obj_data.text)['data']['reply']

            name = obj_data['objname']
            logger.info('Ingesting {name} . . .'.format(name=name))

            ### Get discovery time and time of last non-detection
            try:
                disc_jd = Time(obj_data['discoverydate'], format='iso', scale='utc').jd
            except:
                disc_jd = None

            try:
                disc_filt = obj_data['discmagfilter']['name']
            except:
                disc_filt = None

            phot_lnds = []
            for observation in obj_data['photometry']:
                if 'Last non detection' in observation['remarks']:
                    phot_lnds.append(observation)

            if phot_lnds:
                lnd = 0
                lnd_maglim = 0
                lnd_filt = 0
                for nondet in phot_lnds:
                    if nondet['jd'] > lnd and nondet['jd'] < disc_jd:
                        lnd = nondet['jd']
                        lnd_maglim = nondet['limflux']
                        lnd_filt = nondet['filters']['name']

            else:
                lnd = None
                lnd_maglim = None
                lnd_filt = None

            all_phot = {}
            counter = 0
            for phot in obj_data['photometry']:
                all_phot[str(counter)] = phot
                counter += 1
            all_phot = json.dumps(all_phot)

            ### Check if it's in TESS
            #NOTE: Currently not working

            #params = {
            #'ra': obj_data['radeg'],
            #'dec': obj_data['decdeg']
            #}
            #tess_url = "https://mast.stsci.edu/tesscut/api/v0.1/sector"

            #tess_response = requests.get(tess_url, params=params)
            #tess_response = tess_response.json()['results']
            #tess_response = sorted([x['sectorName'] for x in tess_response])
            #
            #if tess_response:
            #    tess_response = '{tess}'.format(tess=[str(x) for x in tess_response])
            #
            #else:
            #    tess_response = None
            ##print(tess_response)

            try:
                source_group = obj_data['reporting_group']['group_name']
            except:
                source_group = None

            try:
                classification = obj_data['object_type']['name']
            except:
                classification = None
            
            newtarget = TNSTarget(
                name=name,
                name_prefix=obj_data.get('name_prefix', None),
                ra=obj_data.get('radeg', None),
                dec=obj_data.get('decdeg', None),
                internal_name=obj_data.get('internal_name', None),
                source_group=source_group,
                lnd_jd=lnd,
                lnd_maglim=lnd_maglim,
                lnd_filter=lnd_filt,
                disc_jd=disc_jd,
                disc_mag=obj_data.get('discoverymag', None),
                disc_filter=disc_filt,
                all_phot=all_phot,
                redshift=obj_data.get('redshift', None),
                classification=classification
            )
            
            newtarget.save()
            
            time.sleep(10) # To avoid maxing out the number of TNS calls within rolling 60s window

        return []

