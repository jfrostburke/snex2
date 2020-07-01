import dash
from dash.dependencies import Input, Output
import dash_table
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import numpy as np
import json

# lots of help from https://community.plot.ly/t/django-and-dash-eads-method/7717

from django_plotly_dash import DjangoDash
from tom_dataproducts.models import ReducedDatum
import matplotlib.pyplot as plt

app = DjangoDash(name='Spectra', id='target_id')   # replaces dash.Dash

params = [
    'Redshift', 'Velocity (km/s)'
]

elements = {
    'H': {'color': '#ff0000', 'waves': [3970, 4102, 4341, 4861, 6563]},
    'He': {'color': '#002157', 'waves': [4472, 5876, 6678, 7065]},
    'He II': {'color': '#003b99', 'waves': [3203, 4686]},
    'O': {'color': '#007236', 'waves': [7774, 7775, 8447, 9266]},
    'O II': {'color': '#00a64d', 'waves': [3727]},
    'O III': {'color': '#00bf59', 'waves': [4959, 5007]},
    'Na': {'color': '#aba000', 'waves': [5890, 5896, 8183, 8195]},
    'Mg': {'color': '#8c6239', 'waves': [2780, 2852, 3829, 3832, 3838, 4571, 5167, 5173, 5184]},
    'Mg II': {'color': '#bf874e', 'waves': [2791, 2796, 2803, 4481]},
    'Si II': {'color': '#5674b9', 'waves': [3856, 5041, 5056, 5670, 6347, 6371]},
    'S II': {'color': '#a38409', 'waves': [5433, 5454, 5606, 5640, 5647, 6715]},
    'Ca II': {'color': '#005050', 'waves': [3934, 3969, 7292, 7324, 8498, 8542, 8662]},
    'Fe II': {'color': '#f26c4f', 'waves': [5018, 5169]},
    'Fe III': {'color': '#f9917b', 'waves': [4397, 4421, 4432, 5129, 5158]},
    'C II': {'color': '#303030', 'waves': [4267, 4745, 6580, 7234]},
    'Galaxy': {'color': '#000000', 'waves': [4341, 4861, 6563, 6548, 6583, 6300, 3727, 4959, 5007, 2798, 6717, 6731]},
    'Tellurics': {'color': '#b7b7b7', 'waves': [6867, 6884, 7594, 7621]},
}
tooltips = [{
    'value': 'rest wavelengths: ' + str(elements[elem]['waves']),
    'type': 'text',
    'if': {'column_id': 'Element', 'row_index': list(elements).index(elem)}
} for elem in elements]

columns = [{'id': p, 'name': p} for p in params]
columns.append({'id': 'Element', 'name': 'Element', 'editable': False})
columns.insert(0, columns.pop())

app.layout = html.Div([
    dcc.Graph(id='table-editing-simple-output'),
    dcc.Input(id='target_id', type='hidden', value='filler text'),
    #dcc.Input(id='target_id', type='hidden', value=6),
    dash_table.DataTable(
        id='table-editing-simple',
        columns=(columns),
        data=[
            {'Element': elem, 'Redshift': 0, 'Velocity (km/s)': 0} for elem in elements
        ],
        editable=True,
        row_selectable='multi',
        selected_rows=[],
        tooltip_conditional=tooltips,
    )
])

@app.expanded_callback(
    Output('table-editing-simple-output', 'figure'),
    [Input('table-editing-simple', 'data'),
     Input('table-editing-simple', 'selected_rows'),
     Input('table-editing-simple', 'columns'),
     Input('target_id', 'value')])
def display_output(rows, selected_row_ids, columns, value, *args, **kwargs):
    # Improvements:
    #   Slow: redraws all spectra each time
    #   Fix dataproducts so they're correctly serialized
    #   Correctly display message when there are no spectra
    # TODO: extend view to give extra context, currently looks like in modified local base code
    #  context['dash_context'] = {'target_id': {'value': self.get_object().id}}
    target_id = value
    spectral_dataproducts = ReducedDatum.objects.filter(target_id=target_id, data_type='spectroscopy')
    if not spectral_dataproducts:
        return 'No spectra yet'
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
        datum = json.loads(spectrum.value)
        wavelength = []
        flux = []
        name = str(spectrum.timestamp).split(' ')[0]
        for key, value in datum.items():
            wavelength.append(value['wavelength'])
            flux.append(float(value['flux']))
        if max(flux) > max_flux: max_flux = max(flux)
        if min(flux) < min_flux: min_flux = min(flux)
        scatter_obj = go.Scatter(
            x=wavelength,
            y=flux,
            name=name,
            line_color=rgb_colors[i]
        )
        all_data.append(scatter_obj)

    graph_data = {'data': all_data}
    
    for row_id in selected_row_ids:
        row = rows[row_id]
        elem = row['Element']
        try:
            z = float(row['Redshift'])
            v_over_c = (float(row['Velocity (km/s)']))/(3e5)
        except:
            continue
        x = []
        y = []
        
        lambda_rest = elements[elem]['waves']
        for lambduh in lambda_rest:

            lambda_observed = lambduh*((1+z)-v_over_c)
    
            x.append(lambda_observed)
            x.append(lambda_observed)
            x.append(None)
            y.append(min_flux*0.95)
            y.append(max_flux*1.05)
            y.append(None)

        graph_data['data'].append(
            go.Scatter(
                x=x,
                y=y,
                name=elem,
                mode='lines',
                line=dict(color=elements[elem]['color'])
            )
        )
    graph_data['layout'] = {
        'height': 350,
        'margin': {'l': 20, 'b': 30, 'r': 10, 't': 10},
        'yaxis': {'type': 'linear'},
        'xaxis': {'showgrid': False}
    }
    return graph_data
