from django.contrib.auth.models import User, Group
from django import template
from plotly import offline
from plotly import graph_objs as go
import logging

logger = logging.getLogger(__name__)

register = template.Library()

@register.filter
def has_gw_permissions(user):
    gw_group = Group.objects.get(name='GWO4')

    if user in gw_group.user_set.all():
        return True
    return False


@register.inclusion_tag('tom_targets/partials/target_distribution.html')
def galaxy_distribution(galaxies):
    locations = galaxies.values_list('ra', 'dec', 'name')
    data = []
    for location in locations:
        data.append(
            dict(
                lon=[location[0]-0.25, location[0]-0.25, location[0]+0.25, location[0]+0.25, location[0]-0.25],
                lat=[location[1]-0.25, location[1]+0.25, location[1]+0.25, location[1]-0.25, location[1]-0.25],
                text=[location[2], location[2], location[2], location[2], location[2]],
                hoverinfo='lon+lat+text',
                mode='lines',
                type='scattergeo',
                line=dict(color='black', width=2)
            )
        )
    data.append(
        dict(
            lon=list(range(0, 360, 60))+[180]*4,
            lat=[0]*6+[-60, -30, 30, 60],
            text=list(range(0, 360, 60))+[-60, -30, 30, 60],
            hoverinfo='none',
            mode='text',
            type='scattergeo'
        )
    )
    layout = {
        'hovermode': 'closest',
        'showlegend': False,
        'geo': {
            'projection': {
                'type': 'mollweide',
            },
            'showcoastlines': False,
            'showland': False,
            'lonaxis': {
                'showgrid': True,
                'range': [0, 360],
            },
            'lataxis': {
                'showgrid': True,
                'range': [-90, 90],
            },
        },
    }
     
    figure = offline.plot(go.Figure(data=data, layout=layout), output_type='div', show_link=False)
    return {'figure': figure}
