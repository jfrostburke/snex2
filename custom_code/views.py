from django_filters.views import FilterView
from django.shortcuts import redirect, render
from django.db.models import Q #
from django.http import HttpResponse, JsonResponse

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

from plotly import offline
import plotly.graph_objs as go
from tom_dataproducts.models import ReducedDatum
from django.utils.safestring import mark_safe
from custom_code.templatetags.custom_code_tags import get_24hr_airmass

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


def targetlist_collapse_view(request):

    target_id = request.GET.get('target_id', None)
    target = Target.objects.get(id=target_id)

    def lightcurve_collapse_view(target):
        def get_color(filter_name):
            filter_translate = {'U': 'U', 'B': 'B', 'V': 'V',
                'g': 'g', 'gp': 'g', 'r': 'r', 'rp': 'r', 'i': 'i', 'ip': 'i',
                'g_ZTF': 'g_ZTF', 'r_ZTF': 'r_ZTF', 'i_ZTF': 'i_ZTF', 'UVW2': 'UVW2', 'UVM2': 'UVM2',
                'UVW1': 'UVW1'}
            colors = {'U': 'rgb(59,0,113)',
                'B': 'rgb(0,87,255)',
                'V': 'rgb(120,255,0)',
                'g': 'rgb(0,204,255)',
                'r': 'rgb(255,124,0)',
                'i': 'rgb(144,0,43)',
                'g_ZTF': 'rgb(0,204,255)',
                'r_ZTF': 'rgb(255,124,0)',
                'i_ZTF': 'rgb(144,0,43)',
                'UVW2': '#FE0683',
                'UVM2': '#BF01BC',
                'UVW1': '#8B06FF',
                'other': 'rgb(0,0,0)'}
            try: color = colors[filter_translate[filter_name]]
            except: color = colors['other']
            return color
    
        photometry_data = {}
        for rd in ReducedDatum.objects.filter(target=target, data_type='photometry'):
            value = json.loads(rd.value)
            photometry_data.setdefault(value.get('filter', ''), {})
            photometry_data[value.get('filter', '')].setdefault('time', []).append(rd.timestamp)
            photometry_data[value.get('filter', '')].setdefault('magnitude', []).append(value.get('magnitude',None))
            photometry_data[value.get('filter', '')].setdefault('error', []).append(value.get('error', None))
        plot_data = [
            go.Scatter(
                x=filter_values['time'],
                y=filter_values['magnitude'], mode='markers',
                marker=dict(color=get_color(filter_name)),
                #name=filter_name,
                error_y=dict(
                    type='data',
                    array=filter_values['error'],
                    visible=True,
                    color=get_color(filter_name)
                )
            ) for filter_name, filter_values in photometry_data.items()]
        layout = go.Layout(
            xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
            yaxis=dict(autorange='reversed',gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
            margin=dict(l=30, r=10, b=30, t=40),
            hovermode='closest',
            height=200,
            width=250,
            showlegend=False,
            plot_bgcolor='white'
        )
        if plot_data:
            return offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False, config={'staticPlot': True}, include_plotlyjs=False) 
        else:
            return 'No photometry for this target yet.'

    def spectra_collapse_view(target):
        spectra = []
        spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy')
        for spectrum in spectral_dataproducts:
            datum = json.loads(spectrum.value)
            wavelength = []
            flux = []
            for key, value in datum.items():
                wavelength.append(value['wavelength'])
                flux.append(float(value['flux']))
            spectra.append((wavelength, flux))
        plot_data = [
            go.Scatter(
                x=spectrum[0],
                y=spectrum[1]
            ) for spectrum in spectra]
        layout = go.Layout(
            height=200,
            width=250,
            margin=dict(l=30, r=10, b=30, t=40),
            showlegend=False,
            xaxis=dict(
                gridcolor='#D3D3D3',
                showline=True,
                linecolor='#D3D3D3',
                mirror=True
            ),
            yaxis=dict(
                showticklabels=False,
                gridcolor='#D3D3D3',
                showline=True,
                linecolor='#D3D3D3',
                mirror=True
            ),
            plot_bgcolor='white'
        )
        if plot_data:
            return offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False, config={'staticPlot': True}, include_plotlyjs='cdn')
        else:
            return 'No spectra for this target yet.'

    def airmass_collapse_view(target):
        interval = 30 #min
        airmass_limit = 3.0

        obj = Target
        obj.ra = target.ra
        obj.dec = target.dec
        obj.epoch = 2000
        obj.type = 'SIDEREAL'

        plot_data = get_24hr_airmass(obj, interval, airmass_limit)
        layout = go.Layout(
            xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
            yaxis=dict(range=[airmass_limit,1.0],gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
            margin=dict(l=20,r=10,b=30,t=40),
            hovermode='closest',
            width=250,
            height=200,
            showlegend=False,
            plot_bgcolor='white'
        )
        visibility_graph = offline.plot(
                go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False, config={'staticPlot': True}, include_plotlyjs='cdn'
        )
        return visibility_graph

    lightcurve_plot = lightcurve_collapse_view(target)
    spectra_plot = spectra_collapse_view(target)
    airmass_plot = airmass_collapse_view(target)

    context = {
        'lightcurve_plot': lightcurve_plot,
        'spectra_plot': spectra_plot,
        'airmass_plot': airmass_plot
    }

    return HttpResponse(json.dumps(context), content_type='application/json')
