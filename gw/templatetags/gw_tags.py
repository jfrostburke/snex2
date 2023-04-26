from django.contrib.auth.models import User, Group
from django import template
from plotly import offline
from plotly import graph_objs as go
from astropy.io import fits
from astropy.visualization import ZScaleInterval
from astropy.wcs import WCS
from astropy.wcs.utils import pixel_to_skycoord, skycoord_to_pixel
from astropy.coordinates import SkyCoord
import numpy as np
import sep
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


@register.inclusion_tag('gw/plot_triplets.html', takes_context=True)
def plot_triplets(context, triplet, galaxy, display_type):

    plot_context = {}

    fig = go.Figure().set_subplots(1,3)
    
    for i, filetype in enumerate(['original', 'template', 'diff']):
        hdu = fits.open(triplet[filetype]['filename'])
        img = hdu[0].data
        wcs = WCS(hdu[0].header)
        hdu.close()

        if display_type == 'list':
            ###TODO: Change this:
            galaxy_coord = SkyCoord(228.691875, 31.223633, unit='deg')#galaxy.ra, galaxy.dec, unit='deg')
            #galaxy_pix_ra, galaxy_pix_dec = skycoord_to_pixel(galaxy_coord, wcs)
            img_coord_lower = SkyCoord(228.691875-0.9/60, 31.223633-0.9/60, unit='deg')
            img_coord_upper = SkyCoord(228.691875+0.9/60, 31.223633+0.9/60, unit='deg')

            img_pixel_upper_ra, img_pixel_lower_dec = skycoord_to_pixel(img_coord_lower, wcs)
            img_pixel_lower_ra, img_pixel_upper_dec = skycoord_to_pixel(img_coord_upper, wcs)
            img = img[int(img_pixel_lower_ra):int(img_pixel_upper_ra), int(img_pixel_lower_dec):int(img_pixel_upper_dec)]

        else:

            img_coord_lower = pixel_to_skycoord(0, 0, wcs)
            img_coord_upper = pixel_to_skycoord(len(img[0,:]), len(img[:,0]), wcs)
        
        x_coords = np.linspace(img_coord_lower.ra.degree, img_coord_upper.ra.degree, len(img[:,0]))
        y_coords = np.linspace(img_coord_lower.dec.degree, img_coord_upper.dec.degree, len(img[0,:]))
        
        zmin,zmax = [int(el) for el in ZScaleInterval().get_limits(img)]

        fig.add_trace(go.Heatmap(x=x_coords, y=y_coords, z=img, zmin=zmin, zmax=zmax, showscale=False), row=1, col=i+1)

        source_coords = []
        if filetype == 'diff' and display_type == 'individual':
            ### Get sky coordinates of sources
            for source in triplet['sources']:
                source_coord = pixel_to_skycoord(source['x'], source['y'], wcs)
                source_coords.append([source_coord.ra.degree, source_coord.dec.degree])
 
    fig.update_xaxes(matches='x')
    fig.update_yaxes(matches='y')

    if display_type == 'list':
        width = 900
        height = 300

    else:
        width = 1500
        height = 500

    fig.update_layout(
        autosize=False,
        width=width,
        height=height,
        margin=dict(
            l=0,
            r=0,
            b=0,
            t=0
        ),
        xaxis=dict(autorange='reversed'),
        shapes=[
            dict(type='circle', xref='x3', yref='y3',
                 x0=source[0]-5.0/3600, y0=source[1]-5.0/3600,
                 x1=source[0]+5.0/3600, y1=source[1]+5.0/3600,
                 line_color='white'
            ) 
        for source in source_coords]
    )

    figure = offline.plot(fig, output_type='div', show_link=False)
    plot_context['subplots'] = figure

    return plot_context

