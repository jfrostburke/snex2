from django import template
from dateutil.parser import parse

from plotly import offline
import plotly.graph_objs as go

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
    layout = go.Layout(yaxis=dict(range=[airmass,1.0]))
    visibility_graph = offline.plot(
        go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False
    )
    return {
        'form': plan_form,
        'target': context['object'],
        'visibility_graph': visibility_graph
    }
