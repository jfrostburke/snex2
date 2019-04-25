from plotly import offline
import plotly.graph_objs as go
from django import template

from tom_targets.models import Target
from tom_targets.forms import TargetVisibilityForm
from tom_observations.utils import get_visibility
from tom_dataproducts.models import DataProduct, ReducedDatum, ObservationRecord

import datetime
import json
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import Angle, get_moon, SkyCoord
import ephem
import numpy as np

register = template.Library()

@register.inclusion_tag('custom_code/airmass.html', takes_context=True)
def airmass_plot(context):
    #request = context['request']
    start_time = datetime.datetime.now()
    end_time = datetime.datetime.now() + datetime.timedelta(days=1)
    airmass_limit = 3.0
    plan_form = TargetVisibilityForm({
        'start_time': start_time,
        'end_time': end_time,
        'airmass': airmass_limit
    })
    visibility_data = get_visibility(context['object'], start_time, end_time, 20, airmass_limit)
    plot_data = [
        go.Scatter(x=data[0], y=data[1], mode='lines', name=site, ) 
            for site, data in visibility_data.items() if 'LCO' in site
    ]
    layout = go.Layout(
        yaxis=dict(range=[airmass_limit,1.0]),
        margin=dict(l=20,r=10,b=30,t=40),
        hovermode='closest',
        width=600,
        height=300,
        autosize=True
    )
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
    return {
        'form': plan_form,
        'target': context['object'],
        'figure': visibility_graph
    }

@register.inclusion_tag('custom_code/lightcurve.html')
def lightcurve(target):
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
            marker=dict(color=colors[filter_translate[filter_name]]),
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values['error'],
                visible=True,
                color=colors[filter_translate[filter_name]]
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
    spectral_dataproducts = DataProduct.objects.filter(target=target, tag='spectroscopy')
    if dataproduct:
        spectral_dataproducts = DataProduct.objects.get(dataproduct=dataproduct)
    for data in spectral_dataproducts:
        datum = json.loads(ReducedDatum.objects.get(data_product=data).value)
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
        height=600,
        width=700,
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
