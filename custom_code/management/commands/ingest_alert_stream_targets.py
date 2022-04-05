from django.core.management.base import BaseCommand
import logging
import json
from custom_code.models import BrokerTarget
from custom_code.brokers.queries.alerce_queries import BasicAlerceQuery
import urllib.request

logger = logging.getLogger(__name__)


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


class Command(BaseCommand):
    help = 'Ingests targets found by broker queries into SNEx2'

    def handle(self, *args, **options):
        ### Get the targets from the queries
        q = BasicAlerceQuery(1.0, 1)
        valid = q.validate_candidates(19.0, 2.0)
        targets_to_ingest = q.candidates

        for name in targets_to_ingest:
            coords = q.coords[name]
            ra = coords[0]
            dec = coords[1]

            z = ned_get_first_redshift(ra, dec, 1.0)
            if z:
                z_source = 'NED'
            else:
                z_source = ''

            stream_name = 'Basic Two Day Nondetections'
            det = json.dumps(q.det[name])
            nondet = json.dumps(q.nondet[name])
            status = 'New'

            newbrokertarget = BrokerTarget(
                    name=name,
                    ra=ra,
                    dec=dec,
                    redshift=z,
                    redshift_source=z_source,
                    stream_name=stream_name,
                    detections=det,
                    nondetections=nondet,
                    status=status
            )
            newbrokertarget.save()

    logger.info('Finished ingesting targets from automatic broker queries')
