from django_filters.views import FilterView
from django.shortcuts import redirect #
from django.db.models import Q #
from django.http import HttpResponse

from custom_code.models import TNSTarget, ScienceTags, TargetTags
from custom_code.filters import TNSTargetFilter, CustomTargetFilter #
from tom_targets.models import TargetList

from tom_targets.models import Target, TargetExtra
from guardian.mixins import PermissionListMixin

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

def make_lnd(mag, filt, jd, jd_now):
    if not jd:
        return 'Archival'
    diff = jd_now - jd
    lnd = '{mag:.2f} ({filt}: {time:.2f})'.format(
        mag = mag,
        filt = filt,
        time = diff)
    return lnd

def make_magrecent(all_phot, jd_now):
    all_phot = json.loads(all_phot)
    recent_jd = max([all_phot[obs]['jd'] for obs in all_phot])
    recent_phot = [all_phot[obs] for obs in all_phot if
        all_phot[obs]['jd'] == recent_jd][0]
    mag = float(recent_phot['flux'])
    filt = recent_phot['filters']['name']
    diff = jd_now - float(recent_jd)
    mag_recent = '{mag:.2f} ({filt}: {time:.2f})'.format(
        mag = mag,
        filt = filt,
        time = diff)
    return mag_recent

class TNSTargets(FilterView):

    # Look at https://simpleisbetterthancomplex.com/tutorial/2016/11/28/how-to-filter-querysets-dynamically.html
    
    template_name = 'custom_code/tns_targets.html'
    model = TNSTarget
    paginate_by = 10
    context_object_name = 'tnstargets'
    strict = False
    filterset_class = TNSTargetFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jd_now = Time(datetime.utcnow()).jd
        TNS_URL = "https://wis-tns.weizmann.ac.il/object/"
        for target in context['object_list']:
            target.coords = make_coords(target.ra, target.dec)
            target.mag_lnd = make_lnd(target.lnd_maglim,
                target.lnd_filter, target.lnd_jd, jd_now)
            target.mag_recent = make_magrecent(target.all_phot, jd_now)
            target.link = TNS_URL + target.name
        return context

class TargetListView(PermissionListMixin, FilterView):
    """
    View for listing targets in the TOM. Only shows targets that the user is authorized to view.     Requires authorization.
    """
    template_name = 'tom_targets/target_list.html'
    paginate_by = 25
    strict = False
    model = Target
    filterset_class = CustomTargetFilter
    permission_required = 'tom_targets.view_target'

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of targets visible, the available ``TargetList`` objects if the user is a    uthenticated, and
        the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['target_count'] = context['paginator'].count
        # hide target grouping list if user not logged in
        context['groupings'] = (TargetList.objects.all()
                                if self.request.user.is_authenticated
                                else TargetList.objects.none())
        context['query_string'] = self.request.META['QUERY_STRING']
        return context

def target_redirect_view(request):
    
    search_entry = request.GET['name']
    
    target_search_coords = None
    for i in [',', ' ']:
        if i in search_entry:
            target_search_coords = search_entry.split(i)
            break 

    if target_search_coords is not None:
        ra = target_search_coords[0]
        dec = target_search_coords[1]
        radius = 1

        if ':' in ra and ':' in dec:
            ra_hms = ra.split(':')
            ra_hour = float(ra_hms[0])
            ra_min = float(ra_hms[1])
            ra_sec = float(ra_hms[2])

            dec_dms = dec.split(':')
            dec_deg = float(dec_dms[0])
            dec_min = float(dec_dms[1])
            dec_sec = float(dec_dms[2])

            # Convert to degree
            ra = (ra_hour*15) + (ra_min*15/60) + (ra_sec*15/3600)
            if dec_deg > 0:
                dec = dec_deg + (dec_min/60) + (dec_sec/3600)
            else:
                dec = dec_deg - (dec_min/60) - (dec_sec/3600)

        else:
            ra = float(ra)
            dec = float(dec)

        target_match_list = Target.objects.filter(ra__gte=ra-1, ra__lte=ra+1, dec__gte=dec-1, dec__lte=dec+1)

        if len(target_match_list) == 1:
            target_id = target_match_list[0].id
            return(redirect('/targets/{}/'.format(target_id)))
        
        else:
            return(redirect('/targets/?cone_search={ra}%2C{dec}%2C1'.format(ra=ra,dec=dec)))

    else:
        target_match_list = Target.objects.filter(Q(name__icontains=search_entry) | Q(aliases__name__icontains=search_entry))

        if len(target_match_list) == 1:
            target_id = target_match_list[0].id
            return(redirect('/targets/{}/'.format(target_id)))

        else: 
            return(redirect('/targets/?name={}'.format(search_entry)))


def add_tag_view(request):
    new_tag = request.GET.get('new_tag', None)
    username = request.user.username
    tag, _ = ScienceTags.objects.get_or_create(tag=new_tag, userid=username)
    response_data = {'success': 1}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


def save_target_tag_view(request):
    tag_names = json.loads(request.GET.get('tags', None))
    target_id = request.GET.get('targetid', None)
    TargetTags.objects.all().filter(target_id=target_id).delete()
    for i in range(len(tag_names)):
        tag_id = ScienceTags.objects.filter(tag=tag_names[i]).first().id
        target_tag, _ = TargetTags.objects.get_or_create(tag_id=tag_id, target_id=target_id)
    response_data = {'success': 1}
    return HttpResponse(json.dumps(response_data), content_type='application/json')

