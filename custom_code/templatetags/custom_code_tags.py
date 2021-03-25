from plotly import offline
import plotly.graph_objs as go
from django import template
from django.conf import settings
from django.db.models.functions import Lower
from django.shortcuts import reverse
from guardian.shortcuts import get_objects_for_user, get_perms
from django.contrib.auth.models import User, Group
from django.contrib.postgres.fields.jsonb import KeyTextTransform

from tom_targets.models import Target, TargetExtra
from tom_targets.forms import TargetVisibilityForm
from tom_observations import utils, facility
from tom_dataproducts.models import DataProduct, ReducedDatum, ObservationRecord

from astroplan import Observer, FixedTarget, AtNightConstraint, time_grid_from_range, moon_illumination
import datetime
import json
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import get_moon, get_sun, SkyCoord, AltAz
import numpy as np
import time

from custom_code.models import ScienceTags, TargetTags, ReducedDatumExtra, Papers
from custom_code.forms import CustomDataProductUploadForm, PapersForm, PhotSchedulingForm, SpecSchedulingForm
from urllib.parse import urlencode
from tom_observations.utils import get_sidereal_visibility
from custom_code.facilities.lco_facility import SnexPhotometricSequenceForm, SnexSpectroscopicSequenceForm

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


@register.inclusion_tag('custom_code/lightcurve.html', takes_context=True)
def lightcurve(context, target):
         
    photometry_data = {}

    if settings.TARGET_PERMISSIONS_ONLY:
        datums = ReducedDatum.objects.filter(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0])
    else:
        datums = get_objects_for_user(context['request'].user,
                                      'tom_dataproducts.view_reduceddatum',
                                      klass=ReducedDatum.objects.filter(
                                        target=target,
                                        data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]))

    for rd in datums:
    #for rd in ReducedDatum.objects.filter(target=target, data_type='photometry'):
        value = rd.value
        if not value:  # empty
            continue
   
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
         
    photometry_data = {}
    if settings.TARGET_PERMISSIONS_ONLY:
        datums = ReducedDatum.objects.filter(target=target, data_type=settings.DATA_PRODUCT_TYPES['photometry'][0])
    else:
        datums = get_objects_for_user(user,
                                      'tom_dataproducts.view_reduceddatum',
                                      klass=ReducedDatum.objects.filter(
                                        target=target,
                                        data_type=settings.DATA_PRODUCT_TYPES['photometry'][0]))
    #for rd in ReducedDatum.objects.filter(target=target, data_type='photometry'): 
    for rd in datums:
        value = rd.value
        photometry_data.setdefault(value.get('filter', ''), {})
        photometry_data[value.get('filter', '')].setdefault('time', []).append(rd.timestamp)
        photometry_data[value.get('filter', '')].setdefault('magnitude', []).append(value.get('magnitude',None))
        photometry_data[value.get('filter', '')].setdefault('error', []).append(value.get('error', None))
    plot_data = [
        go.Scatter(
            x=filter_values['time'],
            y=filter_values['magnitude'], mode='markers',
            marker=dict(color=get_color(filter_name)),
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
        spectra.append((wavelength, flux, name))
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
    phot_form.helper.form_action = reverse('tom_observations:create', kwargs={'facility': 'LCO'})
    spec_form.helper.form_action = reverse('tom_observations:create', kwargs={'facility': 'LCO'})
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
def observation_summary(context, target=None):
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
        observations = ObservationRecord.objects.all().order_by('-created')

    parameters = []
    for observation in observations:

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
            parameter_string += ' starting on ' + str(observation.created).split(' ')[0]
            if parameter.get('end', ''):
                parameter_string += ' and ending on ' + str(observation.modified).split(' ')[0]

            parameters.append({'title': 'LCO Sequence',
                               'summary': parameter_string,
                               'observation': observation.id})

        # Now do Gemini observations
        elif parameter.get('facility', '') == 'Gemini':
            
            if 'SPECTRA' in parameter.get('observation_type', ''):
                parameter_string = 'Gemini spectrum of B exposure time ' + parameter.get('b_exptime', '') + 's and R exposure time ' + parameter.get('r_exptime', '') + 's with airmass <' + str(parameter.get('max_airmass', '')) + ', scheduled on ' + str(observation.created).split(' ')[0]

            else: # Gemini photometry
                parameter_string = 'Gemini photometry of g (' + parameter.get('g_exptime', '') + 's), r (' + parameter.get('r_exptime', '') + 's), i (' + parameter.get('i_exptime', '') + 's), and z (' + parameter.get('z_exptime', '') + 's), with airmass < ' + str(parameter.get('max_airmass', '')) + ', scheduled on ' + str(observation.created).split(' ')[0]

            parameters.append({'title': 'Gemini Sequence',
                               'summary': parameter_string,
                               'observation': observation.id})

    return {
        'observations': observations,
        'parameters': parameters
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

    
@register.inclusion_tag('custom_code/scheduling_list_with_form.html', takes_context=True)
def scheduling_list_with_form(context, observation):
    parameters = []
    facility = observation.facility
    
    # For now, we'll only worry about scheduling for LCO observations
    if facility != 'LCO':
        return {'observations': observation,
                'parameters': ''}
        
    observation_id = observation.id
    target = observation.target
    target_names = observation.target.names

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
        start = str(observation.created).split('.')[0]
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
                           'target': target,
                           'facility': facility,
                           'observation_type': observation_type,
                           'instrument': instrument,
                           'start': start,
                           'reminder': end,
                           'user_id': context['request'].user.id
                        })
    
    else: # For spectra observations
        observation_type = 'Spec'
        instrument = 'Floyds'
        cadence_frequency = parameter.get('cadence_frequency', '')
        start = str(observation.created).split('.')[0]
        if parameter.get('end', ''):
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
                           'target': target,
                           'facility': facility,
                           'observation_type': observation_type,
                           'instrument': instrument,
                           'start': start,
                           'end': end,
                           'user_id': context['request'].user.id
                        })


    return {'observations': observation,
            'parameters': parameters,
            'form': form
    }


@register.filter
def order_by_reminder(queryset, time):
    queryset = queryset.exclude(status='CANCELED')
    queryset = queryset.annotate(reminder=KeyTextTransform('reminder', 'parameters'))
    now = datetime.datetime.now()
    
    if time == 'expired':
        queryset = queryset.filter(reminder__lt=datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S'))
    elif time == 'upcoming':
        queryset = queryset.filter(reminder__gt=datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S'))
    
    queryset = queryset.order_by('reminder')
    return queryset


@register.inclusion_tag('custom_code/spectra_page.html')
def spectra_page(target, dataproduct=None):
    spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy').order_by('-timestamp')
    if dataproduct:
        spectral_dataproducts = DataProduct.objects.get(dataproduct=dataproduct)
    plot_list = []
    for spectrum in spectral_dataproducts:
        spectra = []
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
        spectra.append((wavelength, flux, name))
    
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
            plot_list.append({
                'spectrum_id': spectrum.id,
                'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False)})
    return {'target': target,
            'plot_list': plot_list
        }
