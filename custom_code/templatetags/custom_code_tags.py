from plotly import offline
import plotly.graph_objs as go
from django import template
from django.conf import settings
from django.db.models.functions import Lower
from django.shortcuts import reverse
from guardian.shortcuts import get_objects_for_user, get_perms, get_groups_with_perms
from django.contrib.auth.models import User, Group
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django_comments.models import Comment
from django.contrib.contenttypes.models import ContentType

from tom_targets.models import Target, TargetExtra, TargetList
from tom_targets.forms import TargetVisibilityForm
from tom_observations import utils, facility
from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_observations.models import ObservationRecord, ObservationGroup

from astroplan import Observer, FixedTarget, AtNightConstraint, time_grid_from_range, moon_illumination
import datetime
import json
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import get_moon, get_sun, SkyCoord, AltAz
import numpy as np
import time
import matplotlib.pyplot as plt

from custom_code.models import ScienceTags, TargetTags, ReducedDatumExtra, Papers, InterestedPersons
from custom_code.forms import CustomDataProductUploadForm, PapersForm, PhotSchedulingForm, SpecSchedulingForm, ReferenceStatusForm
from urllib.parse import urlencode
from tom_observations.utils import get_sidereal_visibility
from custom_code.facilities.lco_facility import SnexPhotometricSequenceForm, SnexSpectroscopicSequenceForm
import logging

logger = logging.getLogger(__name__)

register = template.Library()

@register.inclusion_tag('custom_code/airmass_collapse.html')
def airmass_collapse(target):
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
    return {
        'target': target,
        'figure': visibility_graph
    }

@register.inclusion_tag('custom_code/airmass.html', takes_context=True)
def airmass_plot(context):
    #request = context['request']
    interval = 15 #min
    airmass_limit = 3.0
    plot_data = get_24hr_airmass(context['object'], interval, airmass_limit)
    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        yaxis=dict(range=[airmass_limit,1.0],gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        margin=dict(l=20,r=10,b=30,t=40),
        hovermode='closest',
        width=600,
        height=300,
        plot_bgcolor='white'
    )
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
    return {
        'target': context['object'],
        'figure': visibility_graph
    }

def get_24hr_airmass(target, interval, airmass_limit):

    plot_data = []
    
    start = Time(datetime.datetime.utcnow())
    end = Time(start.datetime + datetime.timedelta(days=1))
    time_range = time_grid_from_range(
        time_range = [start, end],
        time_resolution = interval*u.minute)
    time_plot = time_range.datetime
    
    fixed_target = FixedTarget(name = target.name, 
        coord = SkyCoord(
            target.ra,
            target.dec,
            unit = 'deg'
        )
    )

    #Hack to speed calculation up by factor of ~3
    sun_coords = get_sun(time_range[int(len(time_range)/2)])
    fixed_sun = FixedTarget(name = 'sun',
        coord = SkyCoord(
            sun_coords.ra,
            sun_coords.dec,
            unit = 'deg'
        )
    )

    #Colors to match SNEx1
    colors = {
        'Siding Spring': '#3366cc',
        'Sutherland': '#dc3912',
        'Teide': '#8c6239',
        'Cerro Tololo': '#ff9900',
        'McDonald': '#109618',
        'Haleakala': '#990099'
    }

    for observing_facility in facility.get_service_classes():

        if observing_facility != 'LCO':
            continue

        observing_facility_class = facility.get_service_class(observing_facility)
        sites = observing_facility_class().get_observing_sites()

        for site, site_details in sites.items():

            observer = Observer(
                longitude = site_details.get('longitude')*u.deg,
                latitude = site_details.get('latitude')*u.deg,
                elevation = site_details.get('elevation')*u.m
            )
            
            sun_alt = observer.altaz(time_range, fixed_sun).alt
            obj_airmass = observer.altaz(time_range, fixed_target).secz

            bad_indices = np.argwhere(
                (obj_airmass >= airmass_limit) |
                (obj_airmass <= 1) |
                (sun_alt > -18*u.deg)  #between astro twilights
            )

            obj_airmass = [np.nan if i in bad_indices else float(x)
                for i, x in enumerate(obj_airmass)]

            label = '({facility}) {site}'.format(
                facility = observing_facility, site = site
            )

            plot_data.append(
                go.Scatter(x=time_plot, y=obj_airmass, mode='lines', name=label, marker=dict(color=colors[site]))
            )

    return plot_data


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


def generic_lightcurve_plot(target, user):
    """
    Writing a generic function to return the data to plot
    for the different light curve applications SNEx2 uses
    """
    
    photometry_data = {}

    if settings.TARGET_PERMISSIONS_ONLY:
        datums = ReducedDatum.objects.filter(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0])
    else:
        datums = get_objects_for_user(user,
                                      'tom_dataproducts.view_reduceddatum',
                                      klass=ReducedDatum.objects.filter(
                                        target=target,
                                        data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]))

    for rd in datums:
    #for rd in ReducedDatum.objects.filter(target=target, data_type='photometry'):
        value = rd.value
        if not value:  # empty
            continue
        if isinstance(value, str):
            value = json.loads(value)
   
        photometry_data.setdefault(value.get('filter', ''), {})
        photometry_data[value.get('filter', '')].setdefault('time', []).append(rd.timestamp)
        photometry_data[value.get('filter', '')].setdefault('magnitude', []).append(value.get('magnitude',None))
        photometry_data[value.get('filter', '')].setdefault('error', []).append(value.get('error', None))        

    plot_data = [
        go.Scatter(
            x=filter_values['time'],
            y=filter_values['magnitude'], mode='markers',
            marker=dict(color=get_color(filter_name)),
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values['error'],
                visible=True,
                color=get_color(filter_name)
            )
        ) for filter_name, filter_values in photometry_data.items()] 

    return plot_data


@register.inclusion_tag('custom_code/lightcurve.html', takes_context=True)
def lightcurve(context, target):
    
    plot_data = generic_lightcurve_plot(target, context['request'].user)         

    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        yaxis=dict(autorange='reversed',gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        margin=dict(l=30, r=10, b=100, t=40),
        hovermode='closest',
        plot_bgcolor='white'
        #height=500,
        #width=500
    )
    if plot_data:
      return {
          'target': target,
          'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False)
      }
    else:
        return {
            'target': target,
            'plot': 'No photometry for this target yet.'
        }


@register.inclusion_tag('custom_code/lightcurve_collapse.html')
def lightcurve_collapse(target, user):
    
    plot_data = generic_lightcurve_plot(target, user)     
    
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
        return {
            'target': target,
            'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False, config={'staticPlot': True}, include_plotlyjs='cdn')
        }
    else:
        return {
            'target': target,
            'plot': 'No photometry for this target yet.'
        }

@register.inclusion_tag('custom_code/moon.html')
def moon_vis(target):

    day_range = 30
    times = Time(
        [str(datetime.datetime.utcnow() + datetime.timedelta(days=delta))
            for delta in np.arange(0, day_range, 0.2)],
        format = 'iso', scale = 'utc'
    )
    
    obj_pos = SkyCoord(target.ra, target.dec, unit=u.deg)
    moon_pos = get_moon(times)

    separations = moon_pos.separation(obj_pos).deg
    phases = moon_illumination(times)

    distance_color = 'rgb(0, 0, 255)'
    phase_color = 'rgb(255, 0, 0)'
    plot_data = [
        go.Scatter(x=times.mjd-times[0].mjd, y=separations, 
            mode='lines',name='Moon distance (degrees)',
            line=dict(color=distance_color)
        ),
        go.Scatter(x=times.mjd-times[0].mjd, y=phases, 
            mode='lines', name='Moon phase', yaxis='y2',
            line=dict(color=phase_color))
    ]
    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3', showline=True, linecolor='#D3D3D3', mirror=True, title='Days from now'),
        yaxis=dict(range=[0.,180.],tick0=0.,dtick=45.,
            tickfont=dict(color=distance_color),
            gridcolor='#D3D3D3', showline=True, linecolor='#D3D3D3', mirror=True
        ),
        yaxis2=dict(range=[0., 1.], tick0=0., dtick=0.25, overlaying='y', side='right',
            tickfont=dict(color=phase_color),
            gridcolor='#D3D3D3', showline=True, linecolor='#D3D3D3', mirror=True),
        margin=dict(l=20,r=10,b=30,t=40),
        width=600,
        height=300,
        plot_bgcolor='white'
    )
    figure = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
   
    return {'plot': figure}


def bin_spectra(waves, fluxes, b):
    """
    Bins spectra given list of wavelengths, fluxes, and binning factor
    """
    binned_waves = []
    binned_flux = []
    newindex = 0
    for index in range(0, len(fluxes), b):
        if index + b - 1 <= len(fluxes) - 1:
            sumx = 0
            sumy = 0
            for binindex in range(index, index+b, 1):
                if binindex < len(fluxes):
                    sumx += waves[binindex]
                    sumy += fluxes[binindex]

            sumx = sumx / b
            sumy = sumy / b
        if sumx > 0:
            binned_waves.append(sumx)
            binned_flux.append(sumy)

    return binned_waves, binned_flux


@register.inclusion_tag('custom_code/spectra.html')
def spectra_plot(target, dataproduct=None):
    spectra = []
    spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy').order_by('-timestamp')
    if dataproduct:
        spectral_dataproducts = DataProduct.objects.get(dataproduct=dataproduct)
    for spectrum in spectral_dataproducts:
        datum = spectrum.value
        wavelength = []
        flux = []
        name = str(spectrum.timestamp).split(' ')[0]
        if datum.get('photon_flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('photon_flux')
        elif datum.get('flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('flux')
        else:
            for key, value in datum.items():
                wavelength.append(float(value['wavelength']))
                flux.append(float(value['flux']))

        binned_wavelength, binned_flux = bin_spectra(wavelength, flux, 5)
        spectra.append((binned_wavelength, binned_flux, name))
    plot_data = [
        go.Scatter(
            x=spectrum[0],
            y=spectrum[1],
            name=spectrum[2]
        ) for spectrum in spectra]
    layout = go.Layout(
        height=600,
        width=700,
        hovermode='closest',
        xaxis=dict(
            tickformat="d",
            title='Wavelength (angstroms)',
            gridcolor='#D3D3D3',
            showline=True,
            linecolor='#D3D3D3',
            mirror=True
        ),
        yaxis=dict(
            tickformat=".1eg",
            title='Flux',
            gridcolor='#D3D3D3',
            showline=True,
            linecolor='#D3D3D3',
            mirror=True
        ),
        plot_bgcolor='white'
    )
    if plot_data:
      return {
          'target': target,
          'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False)
      }
    else:
        return {
            'target': target,
            'plot': 'No spectra for this target yet.'
        }

@register.inclusion_tag('custom_code/spectra_collapse.html')
def spectra_collapse(target):
    spectra = []
    spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy').order_by('-timestamp')
    for spectrum in spectral_dataproducts:
        datum = spectrum.value
        wavelength = []
        flux = []
        if datum.get('photon_flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('photon_flux')
        elif datum.get('flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('flux')
        else:
            for key, value in datum.items():
                wavelength.append(float(value['wavelength']))
                flux.append(float(value['flux']))
        
        binned_wavelength, binned_flux = bin_spectra(wavelength, flux, 5)
        spectra.append((binned_wavelength, binned_flux))
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
      return {
          'target': target,
          'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False, config={'staticPlot': True}, include_plotlyjs='cdn')
      }
    else:
        return {
            'target': target,
            'plot': 'No spectra for this target yet.'
        }

@register.inclusion_tag('custom_code/aladin_collapse.html')
def aladin_collapse(target):
    return {'target': target}

@register.filter
def get_targetextra_id(target, keyword):
    try:
        targetextra = TargetExtra.objects.get(target_id=target.id, key=keyword)
        return targetextra.id
    except:
        return json.dumps(None)


@register.inclusion_tag('tom_targets/partials/target_data.html', takes_context=True)
def target_data_with_user(context, target):
    """
    Displays the data of a target.
    """
    user = context['request'].user
    extras = {k['name']: target.extra_fields.get(k['name'], '') for k in settings.EXTRA_FIELDS if not k.get('hidden')}
    return {
        'target': target,
        'extras': extras,
        'user': user
    }


@register.inclusion_tag('custom_code/classifications_dropdown.html')
def classifications_dropdown(target):
    classifications = [i for i in settings.TARGET_CLASSIFICATIONS]
    return {'target': target,
            'classifications': classifications}

@register.inclusion_tag('custom_code/science_tags_dropdown.html')
def science_tags_dropdown(target):
    tag_query = ScienceTags.objects.all().order_by(Lower('tag'))
    tags = [i.tag for i in tag_query]
    return{'target': target,
           'sciencetags': tags}

@register.filter
def get_target_tags(target):
    #try:
    target_tag_query = TargetTags.objects.filter(target_id=target.id)
    tags = ''
    for i in target_tag_query:
        tag_name = ScienceTags.objects.filter(id=i.tag_id).first().tag
        tags+=(str(tag_name) + ',')
    return json.dumps(tags)
    #except:
    #    return json.dumps(None)


@register.inclusion_tag('custom_code/custom_upload_dataproduct.html', takes_context=True)
def custom_upload_dataproduct(context, obj):
    user = context['user']
    initial = {}
    choices = {}
    if isinstance(obj, Target):
        initial['target'] = obj
        initial['referrer'] = reverse('tom_targets:detail', args=(obj.id,))
        initial['used_in'] = ('', '')

    elif isinstance(obj, ObservationRecord):
        initial['observation_record'] = obj
        initial['referrer'] = reverse('tom_observations:detail', args=(obj.id,))
        
    form = CustomDataProductUploadForm(initial=initial)
    if not settings.TARGET_PERMISSIONS_ONLY:
        if user.is_superuser:
            form.fields['groups'].queryset = Group.objects.all()
        else:
            form.fields['groups'].queryset = user.groups.all()
    return {'data_product_form': form}


@register.inclusion_tag('custom_code/submit_lco_observations.html')
def submit_lco_observations(target):
    phot_initial = {'target_id': target.id,
                    'facility': 'LCO',
                    'observation_type': 'IMAGING',
                    'name': target.name}
    spec_initial = {'target_id': target.id,
                    'facility': 'LCO',
                    'observation_type': 'SPECTRA',
                    'name': target.name}
    phot_form = SnexPhotometricSequenceForm(initial=phot_initial, auto_id='phot_%s')
    spec_form = SnexSpectroscopicSequenceForm(initial=spec_initial, auto_id='spec_%s')
    phot_form.helper.form_action = reverse('submit-lco-obs', kwargs={'facility': 'LCO'})
    spec_form.helper.form_action = reverse('submit-lco-obs', kwargs={'facility': 'LCO'})
    if not settings.TARGET_PERMISSIONS_ONLY:
        phot_form.fields['groups'].queryset = Group.objects.all()
        spec_form.fields['groups'].queryset = Group.objects.all()
    return {'object': target,
            'phot_form': phot_form,
            'spec_form': spec_form}

@register.inclusion_tag('custom_code/dash_lightcurve.html', takes_context=True)
def dash_lightcurve(context, target, width, height):
    request = context['request']
    
    # Get initial choices and values for some dash elements
    telescopes = ['LCO']
    reducer_groups = []
    papers_used_in = []
    final_reduction = False
    background_subtracted = False

    datumquery = ReducedDatum.objects.filter(target=target, data_type='photometry')
    for i in datumquery:
        datum_value = i.value
        if isinstance(datum_value, str):
            datum_value = json.loads(datum_value)
        if datum_value.get('background_subtracted', '') == True:
            background_subtracted = True
            break

    final_background_subtracted = False
    for de in ReducedDatumExtra.objects.filter(target=target, key='upload_extras', data_type='photometry'):
        de_value = json.loads(de.value)
        inst = de_value.get('instrument', '')
        used_in = de_value.get('used_in', '')
        group = de_value.get('reducer_group', '')

        if inst and inst not in telescopes:
            telescopes.append(inst)
        if used_in and used_in not in papers_used_in:
            try:
                paper_query = Papers.objects.get(id=used_in)
                paper_string = str(paper_query)
                papers_used_in.append(paper_string)
            except:
                paper_string = str(used_in)
                papers_used_in.append(paper_string)
        if group and group not in reducer_groups:
            reducer_groups.append(group)
   
        if de_value.get('final_reduction', '')==True:
            final_reduction = True
            final_reduction_datumid = de_value.get('data_product_id', '')

            datum = ReducedDatum.objects.filter(target=target, data_type='photometry', data_product_id=final_reduction_datumid)
            datum_value = datum.first().value
            if isinstance(datum_value, str):
                datum_value = json.loads(datum_value)
            if datum_value.get('background_subtracted', '') == True:
                final_background_subtracted = True
    
    reducer_group_options = [{'label': 'LCO', 'value': ''}]
    reducer_group_options.extend([{'label': k, 'value': k} for k in reducer_groups])
    reducer_groups.append('')
    
    paper_options = [{'label': '', 'value': ''}]
    paper_options.extend([{'label': k, 'value': k} for k in papers_used_in])

    dash_context = {'target_id': {'value': target.id},
                    'plot-width': {'value': width},
                    'plot-height': {'value': height},
                    'telescopes-checklist': {'options': [{'label': k, 'value': k} for k in telescopes]},
                    'reducer-group-checklist': {'options': reducer_group_options,
                                                'value': reducer_groups},
                    'papers-dropdown': {'options': paper_options}
    }

    if final_reduction:
        dash_context['final-reduction-checklist'] = {'value': 'Final'}
        dash_context['reduction-type-radio'] = {'value': 'manual'}

        if final_background_subtracted:
            dash_context['subtracted-radio'] = {'value': 'Subtracted'}
        else:
            dash_context['subtracted-radio'] = {'value': 'Unsubtracted'}
            dash_context['telescopes-checklist']['value'] = telescopes

    elif background_subtracted:
        dash_context['subtracted-radio'] = {'value': 'Subtracted'}

    else:
        dash_context['subtracted-radio'] = {'value': 'Unsubtracted'}


    return {'dash_context': dash_context,
            'request': request}


@register.inclusion_tag('custom_code/dash_spectra.html', takes_context=True)
def dash_spectra(context, target):
    request = context['request']

    try:
        z = TargetExtra.objects.filter(target_id=target.id, key='redshift').first().float_value
    except:
        z = 0

    ### Send the min and max flux values 
    target_id = target.id
    spectral_dataproducts = ReducedDatum.objects.filter(target_id=target_id, data_type='spectroscopy')
    if not spectral_dataproducts:
        return {'dash_context': {},
                'request': request
            }
    colormap = plt.cm.gist_rainbow
    colors = [colormap(i) for i in np.linspace(0, 0.99, len(spectral_dataproducts))]
    rgb_colors = ['rgb({r}, {g}, {b})'.format(
        r=int(color[0]*255),
        g=int(color[1]*255),
        b=int(color[2]*255),
    ) for color in colors]
    all_data = []
    max_flux = 0
    min_flux = 0
    for i in range(len(spectral_dataproducts)):
        spectrum = spectral_dataproducts[i]
        datum = spectrum.value
        wavelength = []
        flux = []
        name = str(spectrum.timestamp).split(' ')[0]
        if datum.get('photon_flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('photon_flux')
        elif datum.get('flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('flux')
        else:
            for key, value in datum.items():
                wavelength.append(value['wavelength'])
                flux.append(float(value['flux']))
        if max(flux) > max_flux: max_flux = max(flux)
        if min(flux) < min_flux: min_flux = min(flux)

    dash_context = {'target_id': {'value': target.id},
                    'target_redshift': {'value': z},
                    'min-flux': {'value': min_flux},
                    'max-flux': {'value': max_flux}
                }

    return {'dash_context': dash_context,
            'request': request}

@register.inclusion_tag('custom_code/dataproduct_update.html')
def dataproduct_update(dataproduct):
    group_query = Group.objects.all()
    groups = [i.name for i in group_query]
    return{'dataproduct': dataproduct,
           'groups': groups}

@register.filter
def get_dataproduct_groups(dataproduct):
    # Query all the groups with permission for this dataproduct
    group_query = Group.objects.all()
    groups = ''
    for i in group_query:
        if 'view_dataproduct' in get_perms(i, dataproduct):
            groups += str(i.name) + ','
    return json.dumps(groups)


@register.inclusion_tag('tom_observations/partials/observation_plan.html')
def custom_observation_plan(target, facility, length=1, interval=30, airmass_limit=3.0):
    """
    Displays form and renders plot for visibility calculation. Using this templatetag to render a plot requires that
    the context of the parent view have values for start_time, end_time, and airmass.
    """

    visibility_graph = ''
    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(days=length)

    visibility_data = get_sidereal_visibility(target, start_time, end_time, interval, airmass_limit)
    i = 0
    plot_data = []
    for site, data in visibility_data.items():
        plot_data.append(go.Scatter(x=data[0], y=data[1], mode='markers+lines', marker={'symbol': i}, name=site))
        i += 1
    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True,title='Date'),
        yaxis=dict(range=[airmass_limit,1.0],gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True,title='Airmass'),
        #xaxis={'title': 'Date'},
        #yaxis={'autorange': 'reversed', 'title': 'Airmass'},
        plot_bgcolor='white'
    )
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )

    return {
        'visibility_graph': visibility_graph
    }


@register.inclusion_tag('custom_code/observation_summary.html', takes_context=True)
def observation_summary(context, target=None, time='previous'):
    """
    A modification of the observation_list templatetag 
    to display a summary of the observation records
    for this object.
    """
    if target:
        if settings.TARGET_PERMISSIONS_ONLY:
            observations = target.observationrecord_set.all()
        else:
            observations = get_objects_for_user(
                                context['request'].user,
                                'tom_observations.view_observationrecord',
                                ).filter(target=target)
    else:
        observations = ObservationRecord.objects.all()

    observations = observations.annotate(start=KeyTextTransform('start', 'parameters'))
    observations = observations.order_by('start')

    ### Get all inactive cadences
    cadences = []
    for o in observations:
        obsgroup = o.observationgroup_set.first()
        if obsgroup is not None:
            cadence = obsgroup.dynamiccadence_set.first()
            if cadence is not None and time != 'ongoing':
                if cadence not in cadences and not cadence.active:
                    cadences.append(cadence)
            elif cadence is not None:
                if cadence not in cadences and cadence.active:
                    cadences.append(cadence)
    
    parameters = []
    for cadence in cadences:
        obsgroup = ObservationGroup.objects.get(id=cadence.observation_group_id)
        #Check if the request is pending, and if so skip it
        pending_obs = obsgroup.observation_records.all().filter(observation_id='template pending').first()
        if not pending_obs and time == 'pending':
            continue
        
        if time == 'pending':
            observation = pending_obs
        else:
            observation = obsgroup.observation_records.all().filter(observation_id='template').first()
        if not observation:
            observation = obsgroup.observation_records.all().order_by('-id').first()
            first_observation = obsgroup.observation_records.all().order_by('id').first()
            sequence_start = str(first_observation.parameters.get('start')).split('T')[0]
            requested_str = ''
        else:
            sequence_start = str(observation.parameters.get('sequence_start', '')).split('T')[0]
            requested_str = ', requested by {}'.format(str(observation.parameters.get('start_user', '')))

        parameter = observation.parameters

        # First do LCO observations
        if parameter.get('facility', '') == 'LCO':

            if parameter.get('cadence_strategy', ''):
                parameter_string = str(parameter.get('cadence_frequency', '')) + '-day ' + str(parameter.get('observation_type', '')).lower() + ' cadence of '
            else:
                parameter_string = 'Single ' + str(parameter.get('observation_type', '')).lower() + ' observation of '

            if parameter.get('observation_type', '') == 'IMAGING':
                filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
                for f in filters:
                    filter_parameters = parameter.get(f, '')
                    if filter_parameters:
                        if filter_parameters[0] != 0.0:
                            filter_string = f + ' (' + str(filter_parameters[0]) + 'x' + str(filter_parameters[1]) + '), '
                            parameter_string += filter_string 
            
            elif parameter.get('observation_type', '') == 'SPECTRA':
                parameter_string += str(parameter.get('exposure_time', ''))
                parameter_string += 's '


            parameter_string += 'with IPP ' + str(parameter.get('ipp_value', ''))
            parameter_string += ' and airmass < ' + str(parameter.get('max_airmass', ''))
            parameter_string += ' starting on ' + sequence_start #str(parameter.get('start')).split('T')[0]
            endtime = parameter.get('sequence_end', '')
            if not endtime:
                endtime = parameter.get('end', '')

            if time == 'previous' and endtime:
                parameter_string += ' and ending on ' + str(endtime).split('T')[0]
            parameter_string += requested_str

            ### Get any comments associated with this observation group
            content_type_id = ContentType.objects.get(model='observationgroup').id
            comments = Comment.objects.filter(object_pk=obsgroup.id, content_type_id=content_type_id).order_by('id')
            comment_list = ['{}: {}'.format(User.objects.get(username=comment.user_name).first_name, comment.comment) for comment in comments]

            parameters.append({'title': 'LCO Sequence',
                               'summary': parameter_string,
                               'comments': comment_list,
                               'observation': observation.id,
                               'group': obsgroup.id})

        # Now do Gemini observations
        elif parameter.get('facility', '') == 'Gemini':
            
            if 'SPECTRA' in parameter.get('observation_type', ''):
                parameter_string = 'Gemini spectrum of B exposure time ' + str(parameter.get('b_exptime', '')) + 's and R exposure time ' + str(parameter.get('r_exptime', '')) + 's with airmass <' + str(parameter.get('max_airmass', '')) + ', scheduled on ' + str(observation.created).split(' ')[0]

            else: # Gemini photometry
                parameter_string = 'Gemini photometry of g (' + str(parameter.get('g_exptime', '')) + 's), r (' + str(parameter.get('r_exptime', '')) + 's), i (' + str(parameter.get('i_exptime', '')) + 's), and z (' + str(parameter.get('z_exptime', '')) + 's), with airmass < ' + str(parameter.get('max_airmass', '')) + ', scheduled on ' + str(observation.created).split(' ')[0]

            parameters.append({'title': 'Gemini Sequence',
                               'summary': parameter_string,
                               'comments': [''], #No comment functionality for Gemini yet
                               'observation': observation.id,
                               'group': obsgroup.id})

    return {
        'observations': observations,
        'parameters': parameters,
        'time': time
    }


@register.inclusion_tag('custom_code/papers_list.html')
def papers_list(target):

    paper_query = Papers.objects.filter(target=target)
    papers = []
    for i in range(len(paper_query)):
        papers.append(paper_query[i])

    paper_form = PapersForm(initial={'target': target})
    
    return {'object': target,
            'papers': papers,
            'form': paper_form}


@register.filter
def smart_name_list(target):

    namelist = [target.name] + [alias.name for alias in target.aliases.all()]
    good_names = []
    for name in namelist:
        if ('SN ' in name or 'AT ' in name or 'ZTF' in name) and name not in good_names:
            good_names.append(name)
        elif 'sn ' in name[:4] or 'at ' in name[:4] or 'ztf' in name[:4]:
            new_name = name.replace(name[:3], name[:3].upper())
            if new_name not in good_names:
                good_names.append(new_name)
        elif ('sn' in name[:2] or 'at' in name[:2] or 'SN' in name[:2] or 'AT' in name[:2]) and name not in good_names and ('las' not in name[:5] and 'LAS' not in name):
            new_name = name[:2].upper() + ' ' + name[2:]
            if new_name not in good_names:
                good_names.append(new_name)
        elif ('atlas' in name[:5] or 'ATLAS' in name[:5]):
            new_name = name.replace(name[:5], name[:5].upper())
            if new_name not in good_names:
                good_names.append(new_name)
        elif 'dlt' in name[:4]:
            new_name = name.replace(name[:3], name[:3].upper())
            if new_name not in good_names:
                good_names.append(new_name)
        elif name not in good_names:
            good_names.append(name)
    
    return good_names
    

@register.inclusion_tag('custom_code/scheduling_list_with_form.html', takes_context=True)
def scheduling_list_with_form(context, observation):
    parameters = []
    facility = observation.facility
    
    # For now, we'll only worry about scheduling for LCO observations
    if facility != 'LCO':
        return {'observations': observation,
                'parameters': ''}
        
    observation_id = observation.id
    
    obsgroup = observation.observationgroup_set.first()
    template_observation = obsgroup.observation_records.all().filter(observation_id='template').first()
    if not template_observation:
        obsset = obsgroup.observation_records.all()
        obsset = obsset.annotate(start=KeyTextTransform('start', 'parameters'))
        obsset = obsset.order_by('start')
        start = str(obsset.first().parameters['start']).replace('T', ' ')
        requested_str = ''
    else:
        start = str(template_observation.parameters['sequence_start']).replace('T', ' ')
        requested_str = str(template_observation.parameters.get('start_user', ''))
    
    target = observation.target
    target_names = smart_name_list(observation.target)

    content_type_id = ContentType.objects.get(model='observationgroup').id
    comment = Comment.objects.filter(object_pk=obsgroup.id, content_type_id=content_type_id).order_by('id').first()
    if not comment:
        comment_str = ''
    else:
        comment_str = '{}: {}'.format(User.objects.get(username=comment.user_name).first_name, comment.comment)
    
    parameter = observation.parameters
    if parameter.get('observation_type', '') == 'IMAGING':

        observation_type = 'Phot'
        if '2M' in parameter.get('instrument_type', ''):
            instrument = 'Muscat'
        elif '1M' in parameter.get('instrument_type', ''):
            instrument = 'Sinistro'
        else:
            instrument = 'SBIG'

        cadence_frequency = parameter.get('cadence_frequency', '')
        #start = str(obsset.first().parameters['start']).replace('T', ' ')
        end = str(parameter.get('reminder', '')).replace('T', ' ')
        if not end:
            end = str(observation.modified).split('.')[0]

        observing_parameters = {
                   'instrument_type': parameter.get('instrument_type', ''),
                   'min_lunar_distance': parameter.get('min_lunar_distance', ''),
                   'proposal': parameter.get('proposal', ''),
                   'observation_type': parameter.get('observation_type', ''),
                   'observation_mode': parameter.get('observation_mode', ''),
                   'cadence_strategy': parameter.get('cadence_strategy', ''),
                   'cadence_frequency': cadence_frequency
            }

        if instrument == 'Muscat':
            observing_parameters['guider_mode'] = parameter.get('guider_mode', '')
            observing_parameters['exposure_mode'] = parameter.get('exposure_mode', '')
            for pos in ['diffuser_g_position', 'diffuser_r_position', 'diffuser_i_position', 'diffuser_z_position']:
                observing_parameters[pos] = parameter.get(pos, '')

        initial = {'name': target.name,
                   'observation_id': observation_id,
                   'target_id': target.id,
                   'facility': facility,
                   'observation_type': parameter.get('observation_type', ''),
                   'cadence_strategy': parameter.get('cadence_strategy', ''),
                   'observing_parameters': json.dumps(observing_parameters),
                   'cadence_frequency': cadence_frequency,
                   'ipp_value': parameter.get('ipp_value', ''),
                   'max_airmass': parameter.get('max_airmass', ''),
                   'reminder': 2*cadence_frequency
            }
        
        filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
        for f in filters:
            if parameter.get(f, '') and parameter.get(f, '')[0] != 0.0:
                initial[f] = parameter.get(f, '')

        form = PhotSchedulingForm(initial=initial)

        parameters.append({'observation_id': observation_id,
                           'obsgroup_id': obsgroup.id,
                           'target': target,
                           'names': target_names,
                           'facility': facility,
                           'proposal': parameter.get('proposal', ''),
                           'observation_type': observation_type,
                           'instrument': instrument,
                           'start': start + ' by ' + requested_str,
                           'comment': comment_str,
                           'reminder': end,
                           'user_id': context['request'].user.id
                        })
    
    else: # For spectra observations
        observation_type = 'Spec'
        instrument = 'Floyds'
        cadence_frequency = parameter.get('cadence_frequency', '')
        #start = str(obsset.first().parameters['start']).replace('T', ' ')
        end = str(parameter.get('reminder', '')).replace('T', ' ')
        if not end:
            end = str(observation.modified).split('.')[0]

        observing_parameters = {
                   'instrument_type': parameter.get('instrument_type', ''),
                   'min_lunar_distance': parameter.get('min_lunar_distance', ''),
                   'proposal': parameter.get('proposal', ''),
                   'observation_type': parameter.get('observation_type', ''),
                   'observation_mode': parameter.get('observation_mode', ''),
                   'cadence_strategy': parameter.get('cadence_strategy', ''),
                   'cadence_frequency': cadence_frequency,
                   'site': parameter.get('site', ''),
                   'exposure_count': parameter.get('exposure_count', ''),
                   'acquisition_radius': parameter.get('acquisition_radius', ''),
                   'guider_mode': parameter.get('guider_mode', ''),
                   'guider_exposure_time': parameter.get('guider_exposure_time', ''),
                   'filter': parameter.get('filter', '')
            }

        initial = {'name': target.name,
                   'observation_id': observation_id,
                   'target_id': target.id,
                   'facility': facility,
                   'observation_type': parameter.get('observation_type', ''),
                   'cadence_strategy': parameter.get('cadence_strategy', ''),
                   'observing_parameters': json.dumps(observing_parameters),
                   'cadence_frequency': cadence_frequency,
                   'ipp_value': parameter.get('ipp_value', ''),
                   'max_airmass': parameter.get('max_airmass', ''),
                   'reminder': 2*cadence_frequency,
                   'exposure_time': parameter.get('exposure_time', '')
            }
        form = SpecSchedulingForm(initial=initial)

        parameters.append({'observation_id': observation_id,
                           'obsgroup_id': obsgroup.id,
                           'target': target,
                           'names': target_names,
                           'facility': facility,
                           'proposal':  parameter.get('proposal', ''),
                           'observation_type': observation_type,
                           'instrument': instrument,
                           'start': start + ' by ' + requested_str,
                           'comment': comment_str,
                           'reminder': end,
                           'user_id': context['request'].user.id
                        })


    return {'observations': observation,
            'parameters': parameters,
            'form': form
    }


@register.filter
def order_by_reminder_expired(queryset, pagenumber):
    queryset = queryset.exclude(status='CANCELED')
    from django.core.paginator import Paginator
    queryset = queryset.annotate(reminder=KeyTextTransform('reminder', 'parameters'))
    now = datetime.datetime.now()
   
    queryset = queryset.filter(reminder__lt=datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S'))
    queryset = queryset.order_by('reminder')

    paginator = Paginator(queryset, 25)
    page_number = pagenumber.strip('page=')
    page_obj = paginator.get_page(page_number)
    return page_obj
    #return queryset


@register.filter
def order_by_reminder_upcoming(queryset, pagenumber):
    queryset = queryset.exclude(status='CANCELED')
    from django.core.paginator import Paginator
    queryset = queryset.annotate(reminder=KeyTextTransform('reminder', 'parameters'))
    now = datetime.datetime.now()
   
    queryset = queryset.filter(reminder__gt=datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S')) 
    queryset = queryset.order_by('reminder')

    paginator = Paginator(queryset, 25)
    page_number = pagenumber.strip('page=')
    page_obj = paginator.get_page(page_number)
    return page_obj
    #return queryset


@register.inclusion_tag('custom_code/dash_spectra_page.html', takes_context=True)
def dash_spectra_page(context, target):
    request = context['request']
    try:
        z = TargetExtra.objects.filter(target_id=target.id, key='redshift').first().float_value
    except:
        z = 0

    ### Send the min and max flux values
    target_id = target.id
    spectral_dataproducts = ReducedDatum.objects.filter(target_id=target_id, data_type='spectroscopy').order_by('timestamp')
    if not spectral_dataproducts:
        return {'dash_context': {},
                'request': request
            }
    
    plot_list = []
    for i in range(len(spectral_dataproducts)):
    
        max_flux = 0
        min_flux = 0
        
        spectrum = spectral_dataproducts[i]
        datum = spectrum.value
        wavelength = []
        flux = []
        name = str(spectrum.timestamp).split(' ')[0]
        if datum.get('photon_flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('photon_flux')
        elif datum.get('flux'):
            wavelength = datum.get('wavelength')
            flux = datum.get('flux')
        else:
            for key, value in datum.items():
                wavelength.append(value['wavelength'])
                flux.append(float(value['flux']))
        if max(flux) > max_flux: max_flux = max(flux)
        if min(flux) < min_flux: min_flux = min(flux)

        plot_list.append({'dash_context': {'spectrum_id': {'value': spectrum.id},
                                           'target_redshift': {'value': z},
                                           'min-flux': {'value': min_flux},
                                           'max-flux': {'value': max_flux}
                                        },
                          'time': str(spectrum.timestamp)
                        })

    return {'plot_list': plot_list,
            'request': request}

@register.filter
def strip_trailing_zeros(value):
    try:
        return str(float(value))
    except:
        return value

@register.filter
def get_best_name(target):

    def find_name(namelist, n):
        for name in namelist:
            if n in name[:2].upper() and 'LAS' not in name[:5].upper():
                return name[:2].upper() + ' ' + name[2:]
        return False

    namelist = [target.name] + [alias.name for alias in target.aliases.all()]
    bestname = find_name(namelist, 'SN')
    if not bestname:
        bestname = find_name(namelist, 'AT')
    if not bestname:
        bestname = namelist[0]
    
    return bestname


@register.inclusion_tag('custom_code/display_group_list.html')
def display_group_list(target):
    groups = Group.objects.all()
    return {'target': target,
            'groups': groups
        }

@register.filter
def target_known_to(target):
    groups = get_groups_with_perms(target)
    return groups


@register.inclusion_tag('custom_code/reference_status.html')
def reference_status(target):
    old_status_query = TargetExtra.objects.filter(target=target, key='reference')
    if not old_status_query:
        old_status = 'Undetermined'
    else:
        old_status = old_status_query.first().value

    reference_form = ReferenceStatusForm(initial={'target': target.id,
                                                  'status': old_status})
    
    return {'object': target,
            'form': reference_form}


@register.inclusion_tag('custom_code/interested_persons.html')
def interested_persons(target, user):
    interested_persons_query = InterestedPersons.objects.filter(target=target)
    interested_persons = [u.user.get_full_name() for u in interested_persons_query]
    try:
        current_user_name = user.get_full_name()
    except:
        current_user_name = user
      
    return {'target': target,
            'interested_persons': interested_persons,
            'user': current_user_name
        }


@register.filter
def upcoming_observing_runs(targetlist):
    upcoming_runs = []
    today = datetime.date.today()
    try:
        for obj in targetlist:
            name = obj.name
            observing_run_datestr = name.split('_')[1]
            year = int(observing_run_datestr[:4])
            month = int(observing_run_datestr[4:6])
            day = int(observing_run_datestr[6:])
            observing_run_date = datetime.date(year, month, day)
            if today <= observing_run_date:
                upcoming_runs.append(obj)

        return upcoming_runs
    except:
        return targetlist


@register.filter
def past_observing_runs(targetlist):
    past_runs = []
    today = datetime.date.today()
    try:
        for obj in targetlist:
            name = obj.name
            observing_run_datestr = name.split('_')[1]
            year = int(observing_run_datestr[:4])
            month = int(observing_run_datestr[4:6])
            day = int(observing_run_datestr[6:])
            observing_run_date = datetime.date(year, month, day)
            if today > observing_run_date:
                past_runs.append(obj)

        return past_runs
    except Exception as e:
        print(e)
        return targetlist


@register.filter
def get_other_observing_runs(targetlist):
    other_runs = []
    today = datetime.date.today()
    try:
        complement_targetlist = TargetList.objects.exclude(pk__in=targetlist.values_list('pk', flat=True))
        for obj in complement_targetlist:
            name = obj.name
            observing_run_datestr = name.split('_')[1]
            year = int(observing_run_datestr[:4])
            month = int(observing_run_datestr[4:6])
            day = int(observing_run_datestr[6:])
            observing_run_date = datetime.date(year, month, day)
            if today <= observing_run_date:
                other_runs.append(obj)

        return other_runs
    except:
        return []


@register.filter
def order_by_priority(targetlist):
    return targetlist.filter(targetextra__key='observing_run_priority').order_by('targetextra__value')


def get_lightcurve_params(target, key):
    query = TargetExtra.objects.filter(target=target, key=key).first()
    if query and query.value:
        value = json.loads(query.value)
        date = "{} ({})".format(value['date'], value['jd'])
        params = {'date': date,
                  'mag': str(value['mag']),
                  'filt': str(value['filt']),
                  'source': str(value['source'])
        }
    else:
        params = {}
    return params


@register.inclusion_tag('custom_code/target_details.html', takes_context=True)
def target_details(context, target):
    request = context['request']
    user = context['user']
    
    ### Get previously saved target information
    nondet_params = get_lightcurve_params(target, 'last_nondetection')
    det_params = get_lightcurve_params(target, 'first_detection')
    max_params = get_lightcurve_params(target, 'maximum')
    
    description_query = TargetExtra.objects.filter(target=target, key='target_description').first()
    if description_query:
        description = description_query.value
    else:
        description = ''
    
    return {'target': target,
            'request': request,
            'user': user,
            'last_nondetection': nondet_params,
            'first_detection': det_params,
            'maximum': max_params,
            'description': description}


@register.inclusion_tag('custom_code/lightcurve_collapse.html')
def lightcurve_fits(target, user, filt=False, days=None):
    
    plot_data = generic_lightcurve_plot(target, user)     
    photometry_data = {}

    if settings.TARGET_PERMISSIONS_ONLY:
        datums = ReducedDatum.objects.filter(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0])
    else:
        datums = get_objects_for_user(user,
                                      'tom_dataproducts.view_reduceddatum',
                                      klass=ReducedDatum.objects.filter(
                                        target=target,
                                        data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]))

    for rd in datums:
        value = rd.value
        if not value:  # empty
            continue
        if isinstance(value, str):
            value = json.loads(value)
   
        photometry_data.setdefault(value.get('filter', ''), {})
        photometry_data[value.get('filter', '')].setdefault('time', []).append(rd.timestamp)
        photometry_data[value.get('filter', '')].setdefault('magnitude', []).append(value.get('magnitude',None))
        photometry_data[value.get('filter', '')].setdefault('error', []).append(value.get('error', None))        

    plot_data = [
        go.Scatter(
            x=filter_values['time'],
            y=filter_values['magnitude'], mode='markers',
            marker=dict(color=get_color(filter_name)),
            name=filter_name,
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
        margin=dict(l=30, r=10, b=100, t=40),
        hovermode='closest',
        plot_bgcolor='white'
    )
    
    if not plot_data:
        return {
            'target': target,
            'plot': 'No photometry for this target yet.',
            'max': '',
            'mag': '',
            'filt': ''
        }
    
        ### Fit a parabola to the lightcurve to find the max
    if filt and filt in photometry_data.keys(): # User has specified a filter to fit
        photometry_to_fit = photometry_data[filt]
    
    elif filt and filt not in photometry_data.keys(): # No photometry for this filter
        return {
            'target': target,
            'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False),
            'max': '',
            'mag': '',
            'filt': ''
        }
    
    else:
        filtlist = list(photometry_data.keys())
        lens = []
        for f in filtlist:
            lens.append(len(photometry_data[f]['magnitude']))
        filt = filtlist[lens.index(max(lens))]
        photometry_to_fit = photometry_data[filt]

    start_date = min(photometry_to_fit['time'])
    start_jd = Time(start_date, scale='utc').jd
   
    times = photometry_to_fit['time']
    mags = []
    errs = []
    jds = []

    if not days:
        days_to_fit = 20
    else:
        days_to_fit = days

    for date in times:
        if Time(date, scale='utc').jd < start_jd + days_to_fit:
            jds.append(float(Time(date, scale='utc').jd))
            mags.append(photometry_to_fit['magnitude'][times.index(date)])
            errs.append(photometry_to_fit['error'][times.index(date)])
    try:
        A, B, C = np.polyfit(jds, mags, 2, w=1/(np.asarray(errs)))
        fit_jds = np.linspace(min(jds), max(jds), 100)
        quadratic_fit = A*fit_jds**2 + B*fit_jds + C

        plot_data.append(
            go.Scatter(
                x=Time(fit_jds, format='jd', scale='utc').isot,
                y=quadratic_fit, mode='lines',
                marker=dict(color='gray'),
                name='n=2 fit'
            )
        )

        max_mag = round(min(quadratic_fit), 2)
        max_jd = fit_jds[np.argmin(quadratic_fit)]
        max_date = Time(max_jd, format='jd', scale='utc').isot

        plot_data.append(
            go.Scatter(
                x=[max_date],
                y=[max_mag],
                mode='markers',
                marker=dict(color='gold', size=15, symbol='star', line=dict(color='black', width=2)),
                name='Maximum'
            )
        )
        maximum = round(abs(B/(2*A)), 2)
    except Exception as e:
        logger.info(e)
        logger.info('Quadratic light curve fit failed for target {}'.format(target.id))
        maximum = ''

    return {
        'target': target,
        'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False),
        'max': maximum,
        'mag': max_mag,
        'filt': filt
    }


@register.inclusion_tag('custom_code/lightcurve.html', takes_context=True)
def lightcurve_with_extras(context, target):
    
    plot_data = generic_lightcurve_plot(target, context['request'].user)         

    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        yaxis=dict(autorange='reversed',gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        margin=dict(l=30, r=10, b=100, t=40),
        hovermode='closest',
        plot_bgcolor='white'
        #height=500,
        #width=500
    )

    ## Check for last nondetection, first detection, and max in the database
    symbols = {'last_nondetection': 'arrow-down', 'first_detection': 'arrow-up', 'maximum': 'star'}
    names = {'last_nondetection': 'Last non-detection', 'first_detection': 'First detection', 'maximum': 'Maximum'}
    for key in ['last_nondetection', 'first_detection', 'maximum']:
        query = TargetExtra.objects.filter(target=target, key=key).first()
        if query and query.value:
            value = json.loads(query.value)
            jd = value.get('jd', None)
            if jd:
                plot_data.append(
                    go.Scatter(
                        x=[Time(float(jd), format='jd', scale='utc').isot],
                        y=[float(value['mag'])], mode='markers',
                        marker=dict(color=get_color(value['filt']), size=12, symbol=symbols[key]),
                        name=names[key]
                    )
                )

    if plot_data:
      return {
          'target': target,
          'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False)
      }
    else:
        return {
            'target': target,
            'plot': 'No photometry for this target yet.'
        }
