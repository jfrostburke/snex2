from django import template

from plotly import offline
import plotly.graph_objs as go

from tom_targets.models import Target
from tom_observations.models import ObservationRecord
from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_dataproducts.forms import DataProductUploadForm
from tom_observations.facility import get_service_class

register = template.Library()


@register.inclusion_tag('tom_dataproducts/partials/dataproduct_list_for_target.html')
def dataproduct_list_for_target(target):
    return {
        'products': target.dataproduct_set.all(),
        'target': target
    }


@register.inclusion_tag('tom_dataproducts/partials/saved_dataproduct_list_for_observation.html')
def dataproduct_list_for_observation_saved(observation_record):
    products = get_service_class(observation_record.facility)().all_data_products(observation_record)
    return {'products': products}


@register.inclusion_tag('tom_dataproducts/partials/unsaved_dataproduct_list_for_observation.html')
def dataproduct_list_for_observation_unsaved(observation_record):
    products = get_service_class(observation_record.facility)().all_data_products(observation_record)
    return {'products': products}


@register.inclusion_tag('tom_dataproducts/partials/dataproduct_list.html')
def dataproduct_list_all(saved, fields):
    products = DataProduct.objects.all().order_by('-created')
    return {'products': products}


@register.inclusion_tag('tom_dataproducts/partials/upload_dataproduct.html', takes_context=True)
def upload_dataproduct(context):
    model_instance = context.get('object', None)
    object_key = ''
    if type(model_instance) == Target:
        object_key = 'target'
    elif type(model_instance) == ObservationRecord:
        object_key = 'observation_record'
    form = context.get(
        'data_product_form',
        DataProductUploadForm(initial={object_key: model_instance})
    )
    user = context.get('user', None)
    return {
        'data_product_form': form,
        'user': user
    }


@register.inclusion_tag('tom_dataproducts/partials/reduced_data_lightcurve.html')
def reduced_data_lightcurve(target):
    time = []
    #filter_data = {'U': (), 'B': (), 'V': (), 'g': (), 'r': (), 'i': ()}
    filter_data = {}
    filter_translate = {'U': 'U', 'B': 'B', 'V': 'V',
        'g': 'g', 'gp': 'g', 'r': 'r', 'rp': 'r', 'i': 'i', 'ip': 'i'}
    colors = {'U': 'rgb(59,0,113)',
        'B': 'rgb(0,87,255)',
        'V': 'rgb(120,255,0)',
        'g': 'rgb(0,204,255)',
        'r': 'rgb(255,124,0)',
        'i': 'rgb(144,0,43)',
        'other': 'rgb(0,0,0)'}

    for rd in ReducedDatum.objects.filter(target=target, data_type='PHOTOMETRY'):
        if rd.label not in filter_translate.keys(): filt = 'other'
        else: filt = filter_translate[rd.label]
        filter_data.setdefault(filt, ([], [], []))
        filter_data[filt][0].append(rd.timestamp)
        filter_data[filt][1].append(rd.value)
        filter_data[filt][2].append(rd.error)
    filter_data = {k: filter_data[k] for k in 
        [key for key in colors.keys() if key in filter_data.keys()]}
    plot_data = [
        go.Scatter(
            x=filter_values[0],
            y=filter_values[1], mode='markers',
            marker=dict(color=colors[filter_name]),
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values[2],
                visible=True,
                color=colors[filter_name]
            )
        ) for filter_name, filter_values in filter_data.items()
    ]
    layout = go.Layout(
        yaxis=dict(autorange='reversed'),
        margin=dict(l=20, r=10, b=30, t=40),
        hovermode='closest'
        #height=500,
        #width=500
    )
    if len(plot_data) == 0:
        return {
            'target': target,
            'plot': "No photometry to display yet"
        }
    else:
        return {
            'target': target,
            'plot': offline.plot(go.Figure(data=plot_data, layout=layout), output_type='div', show_link=False)
        }
