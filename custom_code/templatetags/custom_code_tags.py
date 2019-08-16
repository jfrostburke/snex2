from plotly import offline
import plotly.graph_objs as go
from django import template

from tom_targets.models import Target
from tom_targets.forms import TargetVisibilityForm
from tom_observations.utils import get_visibility
from tom_observations import utils, facility
from tom_dataproducts.models import DataProduct, ReducedDatum, ObservationRecord

import datetime
import json
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import Angle, get_moon, SkyCoord, AltAz
import ephem
import numpy as np

register = template.Library()

@register.inclusion_tag('custom_code/airmass_collapse.html')
def airmass_collapse(target):
    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(days=1)
    interval = 30 #min
    airmass_limit = 3.0
    plan_form = TargetVisibilityForm({
        'start_time': start_time,
        'end_time': end_time,
        'airmass': airmass_limit
    })

    obj = Target
    obj.ra = target.ra
    obj.dec = target.dec
    obj.epoch = 2000
    obj.type = 'SIDEREAL' 

    visibility_data = get_24hr_airmass(obj, start_time, interval, airmass_limit)
    plot_data = [
        go.Scatter(x=data[0], y=data[1], mode='lines', name=site, ) 
            for site, data in visibility_data.items() if 'LCO' in site
    ]
    layout = go.Layout(
        yaxis=dict(range=[airmass_limit,1.0]),
        margin=dict(l=20,r=10,b=30,t=40),
        hovermode='closest',
        width=250,
        height=200,
        showlegend=False
    )
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
    return {
        'form': plan_form,
        'target': target,
        'figure': visibility_graph
    }

@register.inclusion_tag('custom_code/airmass.html', takes_context=True)
def airmass_plot(context):
    #request = context['request']
    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(days=1)
    interval = 15 #min
    airmass_limit = 3.0
    plan_form = TargetVisibilityForm({
        'start_time': start_time,
        'end_time': end_time,
        'airmass': airmass_limit
    })
    visibility_data = get_24hr_airmass(context['object'], start_time, interval, airmass_limit)
    plot_data = [
        go.Scatter(x=data[0], y=data[1], mode='lines', name=site, ) 
            for site, data in visibility_data.items()
    ]
    layout = go.Layout(
        yaxis=dict(range=[airmass_limit,1.0]),
        margin=dict(l=20,r=10,b=30,t=40),
        hovermode='closest',
        width=600,
        height=300
    )
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
    return {
        'form': plan_form,
        'target': context['object'],
        'figure': visibility_graph
    }

def get_24hr_airmass(target, start_time, interval, airmass_limit):
    
    end_time = start_time + datetime.timedelta(days=1)

    visibility = {}
    sun = ephem.Sun()
    body = utils.get_pyephem_instance_for_type(target)
    
    for observing_facility in facility.get_service_classes():
        if observing_facility != 'LCO':
            continue
        observing_facility_class = facility.get_service_class(observing_facility)
        sites = observing_facility_class().get_observing_sites()
        for site, site_details in sites.items():

            positions = [[], []]
            observer = utils.observer_for_site(site_details)

            sun_up_times = get_up_times(observer,sun, start_time,end_time,interval)
            obj_up_times = get_up_times(observer,body,start_time,end_time,interval)
            
            good_times = sorted(list(obj_up_times - sun_up_times))

            for time in good_times:
                observer.date = time
                body.compute(observer)
                alt = Angle(str(body.alt), unit=u.degree)
                az = Angle(str(body.az), unit=u.degree)
                altaz = AltAz(alt=alt.to_string(unit=u.rad), az=az.to_string(unit=u.rad))
                airmass = altaz.secz
                positions[0].append(time)
                positions[1].append(
                    airmass.value if (airmass.value > 1 and airmass.value <= airmass_limit) else None
                )
            visibility['({0}) {1}'.format(observing_facility, site)] = positions
    
    return visibility

def get_up_times(observer,target,start_time,end_time,interval):
    """
    Returns up_times: a set of times, from start_time to end_time
    at interval, where target is up
    """

    observer.date = start_time

    try:
        next_rise = utils.ephem_to_datetime(observer.next_rising(target))
        next_set = utils.ephem_to_datetime(observer.next_setting(target))
    except ephem.AlwaysUpError:
        next_rise = start_time
        next_set = end_time

    up_times = []

    for delta in range(0,24*60,interval):
        curr_time = start_time + datetime.timedelta(minutes=delta)

        if next_set > next_rise:
            if curr_time > next_rise and curr_time < next_set:
                up_times.append(curr_time)
        elif next_set < next_rise:
            if curr_time > next_rise or curr_time < next_set:
                up_times.append(curr_time)

    return set(up_times)

@register.inclusion_tag('custom_code/lightcurve.html')
def lightcurve(target):
    def get_color(filter_name):
        filter_translate = {'U': 'U', 'B': 'B', 'V': 'V',
            'g': 'g', 'gp': 'g', 'r': 'r', 'rp': 'r', 'i': 'i', 'ip': 'i',
            'g_ZTF': 'g_ZTF', 'r_ZTF': 'r_ZTF', 'i_ZTF': 'i_ZTF'}
        colors = {'U': 'rgb(59,0,113)',
            'B': 'rgb(0,87,255)',
            'V': 'rgb(120,255,0)',
            'g': 'rgb(0,204,255)',
            'r': 'rgb(255,124,0)',
            'i': 'rgb(144,0,43)',
            'g_ZTF': 'rgb(0,204,255)',
            'r_ZTF': 'rgb(255,124,0)',
            'i_ZTF': 'rgb(144,0,43)',
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
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values['error'],
                visible=True,
                color=get_color(filter_name)
            )
        ) for filter_name, filter_values in photometry_data.items()]
    layout = go.Layout(
        yaxis=dict(autorange='reversed'),
        margin=dict(l=30, r=10, b=30, t=40),
        hovermode='closest'
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

@register.inclusion_tag('custom_code/moon.html')
def moon_vis(target):

    def get_phase(moon, time):
        moon.compute(time)
        return moon.phase

    day_range = 30
    times = Time(
        [str(datetime.datetime.utcnow() + datetime.timedelta(days=delta))
            for delta in np.arange(0, day_range, 0.2)],
        format = 'iso', scale = 'utc'
    )
    
    obj_pos = SkyCoord(target.ra, target.dec, unit=u.deg)
    moon_pos = get_moon(times)
    separations = moon_pos.separation(obj_pos).deg
    
    moon = ephem.Moon()
    phases = [get_phase(moon, time.iso)/100.0 for time in times]

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
        xaxis=dict(title='Days from now'),
        yaxis=dict(range=[0.,180.],tick0=0.,dtick=45.,
            tickfont=dict(color=distance_color)
        ),
        yaxis2=dict(range=[0., 1.], tick0=0., dtick=0.25, overlaying='y', side='right',
            tickfont=dict(color=phase_color)),
        margin=dict(l=20,r=10,b=30,t=40),
        #hovermode='compare',
        width=600,
        height=300,
        autosize=True
    )
    figure = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
   
    return {'plot': figure}

@register.inclusion_tag('custom_code/spectra.html')
def spectra_plot(target, dataproduct=None):
    spectra = []
    spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy')
    if dataproduct:
        spectral_dataproducts = DataProduct.objects.get(dataproduct=dataproduct)
    for spectrum in spectral_dataproducts:
        datum = json.loads(spectrum.value)
        wavelength = []
        flux = []
        name = str(spectrum.timestamp).split(' ')[0]
        for key, value in datum.items():
            wavelength.append(value['wavelength'])
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
            title='Wavelength (angstroms)'
        ),
        yaxis=dict(
            tickformat=".1eg",
            title='Flux'
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
            'plot': 'No spectra for this target yet.'
        }

@register.inclusion_tag('custom_code/aladin_collapse.html')
def aladin_collapse(target):
    return {'target': target}
