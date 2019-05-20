from django_filters.views import FilterView

from custom_code.models import TNSTarget
from custom_code.filters import TNSTargetFilter

from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.time import Time
from datetime import datetime
from datetime import timedelta
import json

# Create your views here.

def make_coords(ra, dec):
    coords = SkyCoord(ra, dec, unit=u.deg)
    coords = coords.to_string('hmsdms',sep=':',precision=1,alwayssign=True)
    return coords

def make_lnd(mag, filt, jd):
    if not jd:
        return 'Archival'
    jd_now = Time(datetime.utcnow()).jd
    diff = jd_now - jd
    lnd = '{mag:.2f} ({filt}: {time:.2f} days ago)'.format(
        mag = mag,
        filt = filt,
        time = diff)
    return lnd

def make_magrecent(all_phot):
    all_phot = all_phot.replace("'","\"")
    #print(all_phot)
    """
    #Not working right now - fix json ingestion
    all_phot = json.loads(all_phot)
    recent_phot = [obs for obs in all_phot if obs['jd'] ==
        max([x['jd'] for x in all_phot])][0]
    """
    return 'filler'

class TNSTargets(FilterView):

    # Look at https://simpleisbetterthancomplex.com/tutorial/2016/11/28/how-to-filter-querysets-dynamically.html
    
    template_name = 'custom_code/tns_targets.html'
    model = TNSTarget
    filterset_class = TNSTargetFilter


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for target in context['object_list']:
            target.coords = make_coords(target.ra, target.dec)
            target.mag_lnd = make_lnd(target.lnd_maglim,
                target.lnd_filter, target.lnd_jd)
            target.mag_recent = make_magrecent(target.all_phot)
        return context
