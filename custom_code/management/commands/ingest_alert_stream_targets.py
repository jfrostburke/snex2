from django.core.management.base import BaseCommand
import logging
import requests
import json
from tom_targets.templatetags.targets_extras import deg_to_sexigesimal
from custom_code.models import TNSTarget, BrokerTarget
from custom_code.brokers.queries.alerce_queries import BasicAlerceQuery
from custom_code.brokers.queries.lasair_iris_queries import LasairIrisQuery
import urllib.request
import os
from django.conf import settings

logger = logging.getLogger(__name__)


BASE_DIR = settings.BASE_DIR
with open(os.path.join(BASE_DIR, 'custom_code/brokers/queries/queries.json'), 'r') as f:
    QUERIES = json.load(f)


def ned_conesearch(ra, dec, rad):
    ### Conesearch of NED given RA and Dec, in degrees, and radius, in arcmin

    ned_url = 'http://ned.ipac.caltech.edu/cgi-bin/objsearch?search_type=Near+Position+Search&in_csys=Equatorial&in_equinox=J2000.0&lon={}d&lat={}d&radius={}&out_csys=Equatorial&out_equinox=J2000.0&of=ascii_bar'.format(ra, dec, rad)
    
    with urllib.request.urlopen(ned_url) as u:
        output = u.read().decode('utf-8')

    return output


def ned_get_first_redshift(ra, dec, rad):
    ### Return the first redshift for a NED source with the given
    ### cone search parameters

    results = ned_conesearch(ra, dec, rad)
    lines = results.split('\n')

    for line in lines:
        if '|' not in line:
            continue # Not at the results yet
        x = line.split('|')
        try:
            z = float(x[6]) # where the redshift should be, if it exists
            return z # Found the first redshift, so return it
        except:
            continue # No redshift for this row

    return False


def ingest_targets(q, stream_name):
    targets_to_ingest = q.candidates
    for name in targets_to_ingest:
        ### First, see if target is already in the database
        brokertargetquery = BrokerTarget.objects.filter(name=name)
        if brokertargetquery.first(): # Target exists
            continue
        coords = q.coords[name]
        ra = coords[0]
        dec = coords[1]

        try:
            z = q.redshifts[name]['z']
            z_source = q.redshifts[name]['source']
            if not z_source:
                z_source = ''
        except:
            logger.info('Looking up redshift from NED')
            z = False

        if not z:
            z = ned_get_first_redshift(ra, dec, 1.0)
            if z:
                z_source = 'NED'
            else:
                z_source = ''

        try:
            tns_name = q.tnsnames['name']
        except:
            tns_name = False

        try:
            sn_class = q.classes['name']
        except:
            search_url = "https://www.wis-tns.org/api/get/search"
            obj_url = "https://www.wis-tns.org/api/get/object"
            api_key = os.environ['TNS_APIKEY']
            tns_id = os.environ['TNS_APIID']

            json_list = {'ra': deg_to_sexigesimal(ra, 'hms'), 'dec': deg_to_sexigesimal(dec, 'dms'), 'radius': '5', 'units': 'arcsec', 'internal_name': name}
            obj_list = requests.post(search_url, headers={'User-Agent': 'tns_marker{"tns_id":'+str(tns_id)+', "type":"bot", "name":"SNEx_Bot1"}'}, data={'api_key': api_key, 'data': json.dumps(json_list)})
            obj_list = json.loads(obj_list.text)['data']['reply']
            if obj_list:
                tns_name = obj_list[0]['objname']

                class_json_list = {'objname': tns_name, 'photometry': 0, 'spectra': 0, 'classification': 1}
                obj_data = requests.post(obj_url, headers={'User-Agent': 'tns_marker{"tns_id":'+str(tns_id)+', "type":"bot", "name":"SNEx_Bot1"}'}, data={'api_key': api_key, 'data': json.dumps(class_json_list)})
                obj_data = json.loads(obj_data.text)['data']['reply']
                if obj_data:
                    sn_class = obj_data['object_type']['name']
                else:
                    sn_class = ''
            else:
                sn_class = ''
        
        if tns_name:
            tns_target = TNSTarget.objects.filter(name=tns_name).first()
            if not tns_target:
                tns_target = None
        else:
            tns_target = None

        det = json.dumps(q.det[name])
        nondet = json.dumps(q.nondet[name])

        newbrokertarget = BrokerTarget(
                name=name,
                ra=ra,
                dec=dec,
                redshift=z,
                redshift_source=z_source,
                classification=sn_class,
                tns_target=tns_target,
                stream_name=stream_name,
                detections=det,
                nondetections=nondet,
                status='New'
        )
        newbrokertarget.save()


class Command(BaseCommand):
    help = 'Ingests targets found by broker queries into SNEx2'

    def handle(self, *args, **options):
        ### Get the targets from the queries
        for query in QUERIES:
            if query['name'] == 'Basic Two Day Nondetections':
                q = BasicAlerceQuery(query['parameters']['days_ago'], query['parameters']['ndet'])
                valid = q.validate_candidates(19.0, 2.0)
            
            elif query['name'] == 'Young Blue SNe':
                q = LasairIrisQuery(query['parameters']['stream_name'], query['parameters']['ncandidates'], query['parameters']['days_ago'])
            
            ingest_targets(q, query['name'])

        logger.info('Finished ingesting targets from automatic broker queries')
