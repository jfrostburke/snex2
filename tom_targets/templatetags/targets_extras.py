from django import template
from dateutil.parser import parse
from plotly import offline
import plotly.graph_objs as go
from astropy import units as u
from astropy.coordinates import Angle, get_moon, SkyCoord
from astropy.time import Time
import numpy as np
import ephem

from tom_targets.models import Target
from tom_targets.forms import TargetVisibilityForm
from tom_observations.utils import get_visibility

import datetime

register = template.Library()


@register.inclusion_tag('tom_targets/partials/recent_targets.html')
def recent_targets(limit=10):
    return {'targets': Target.objects.all().order_by('-created')[:limit]}


@register.inclusion_tag('tom_targets/partials/target_feature.html')
def target_feature(target):
    return {'target': target}


@register.inclusion_tag('tom_targets/partials/target_lightcurve.html')
def target_lightcurve(target):
    return {'target': target}


@register.inclusion_tag('tom_targets/partials/target_data.html')
def target_data(target):
    return {'target': target}


@register.inclusion_tag('tom_targets/partials/target_plan.html', takes_context=True)
def target_plan(context):
    #request = context['request']
    start_time = datetime.datetime.now()
    end_time = datetime.datetime.now() + datetime.timedelta(days=1)
    airmass = 3.0
    plan_form = TargetVisibilityForm({
        'start_time': start_time,
        'end_time': end_time,
        'airmass': airmass
    })
    visibility_graph = ''
    visibility_data = get_visibility(context['object'], start_time, end_time, 15, airmass)
    plot_data = [
        go.Scatter(x=data[0], y=data[1], mode='lines', name=site, ) for site, data in visibility_data.items()
    ]
    layout = go.Layout(
        yaxis=dict(range=[airmass,1.0]),
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
        'visibility_graph': visibility_graph
    }

@register.inclusion_tag('tom_targets/partials/target_reference.html')
def target_reference(target):
    return {'target': target}

@register.inclusion_tag('tom_targets/partials/target_distribution.html')
def target_distribution(targets):
    locations = targets.filter(type=Target.SIDEREAL).values_list('ra', 'dec', 'name')
    data = [
        dict(
            lon=[l[0] for l in locations],
            lat=[l[1] for l in locations],
            text=[l[2] for l in locations],
            hoverinfo='lon+lat+text',
            mode='markers',
            type='scattergeo'
        ),
        dict(
            lon=list(range(0, 360, 60))+[180]*4,
            lat=[0]*6+[-60, -30, 30, 60],
            text=list(range(0, 360, 60))+[-60, -30, 30, 60],
            hoverinfo='none',
            mode='text',
            type='scattergeo'
        )
    ]
    layout = {
        'title': 'Target Distribution (sidereal)',
        'hovermode': 'closest',
        'showlegend': False,
        'geo': {
            'projection': {
                'type': 'mollweide',
            },
            'showcoastlines': False,
            'lonaxis': {
                'showgrid': True,
                'range': [0, 360],
            },
            'lataxis': {
                'showgrid': True,
                'range': [-90, 90],
            },
        }
    }
    figure = offline.plot(go.Figure(data=data, layout=layout), output_type='div', show_link=False)
    return {'figure': figure}


@register.filter
def deg_to_sexigesimal(value, fmt):
    a = Angle(value, unit=u.degree)
    if fmt == 'hms':
        return '{0:02.0f}:{1:02.0f}:{2:05.3f}'.format(a.hms.h, a.hms.m, a.hms.s)
    elif fmt == 'dms':
        rep = a.signed_dms
        sign = '-' if rep.sign < 0 else '+'
        return '{0}{1:02.0f}:{2:02.0f}:{3:05.3f}'.format(sign, rep.d, rep.m, rep.s)
    else:
        return 'fmt must be "hms" or "dms"'


@register.inclusion_tag('tom_targets/partials/aladin.html')
def aladin(target):
    return {'target': target}

@register.inclusion_tag('tom_targets/partials/moon_plot.html')
def moon_plot(target):

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
    plot_data = [
        go.Scatter(x=times.mjd-times[0].mjd, y=separations, mode='lines', name='Moon distance (degrees)'),
        go.Scatter(x=times.mjd-times[0].mjd, y=phases, mode='lines', name='Moon phase', yaxis='y2')
    ]
    layout = go.Layout(
        yaxis=dict(range=[0.,180.]),
        yaxis2=dict(range=[0., 1.], tickfont=dict(color='rgb(255,0,0)'), overlaying='y', side='right'),
        margin=dict(l=20,r=10,b=30,t=40),
        hovermode='closest',
        width=600,
        height=300,
        autosize=True
    )
    figure = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
   
    return {'figure': figure}
