import dash
from dash.dependencies import Input, Output, State
import dash_table
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import numpy as np
import json

### Jamie's Dash spectra plotting, currently a WIP
### Jamie: "lots of help from https://community.plot.ly/t/django-and-dash-eads-method/7717"

from django_plotly_dash import DjangoDash
from tom_dataproducts.models import ReducedDatum
from custom_code.templatetags.custom_code_tags import bin_spectra
import matplotlib.pyplot as plt

external_stylesheets = [dbc.themes.BOOTSTRAP]

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
    'Flash CNO': {'color': '#0064c8', 'waves': [4648, 5696, 5801, 4640, 4058, 4537, 5047, 7109, 7123, 4604, 4946, 3410, 5597, 3811, 3835]},
    'SN Ia': {'color': '#ff9500', 'waves': [3856, 5041, 5056, 5670, 6347, 6371, 5433, 5454, 5606, 5640, 5647, 6715, 3934, 3969, 7292, 7324, 8498, 8542, 8662]},
}
tooltips = [{
    'value': 'rest wavelengths: ' + str(elements[elem]['waves']),
    'type': 'text',
    'if': {'column_id': 'Element', 'row_index': list(elements).index(elem)}
} for elem in elements]

columns = [{'id': p, 'name': p} for p in params]
columns.append({'id': 'Element', 'name': 'Element', 'editable': False})
columns.insert(0, columns.pop())

elem_input_array = []
for elem in list(elements.keys())[:9]:
    row = html.Tr([
        html.Td(
            dbc.Checkbox(id='standalone-checkbox-'+elem.replace(' ', '-'))
        ),
        html.Td(
            elem
        ),
        html.Td(
           dbc.Badge(
               '  ',#elem,
               color=elements[elem]['color']
            )
        ),
        html.Td(
            dbc.Input(
                id='z-'+elem.replace(' ', '-'),
                value=0,
                type='number',
                min=0,
                max=10,
                step=0.0000001,
                placeholder='z'
            )
        ),
        html.Td(
            dbc.Input(
                id='v-'+elem.replace(' ', '-'),
                type='number',
                placeholder='Velocity (km/s)',
                value=0
            )
        )
    ])
    elem_input_array.append(row)
table_body_one =[html.Tbody(elem_input_array)]

elem_input_array = []
for elem in list(elements.keys())[9:]:
    row = html.Tr([
        html.Td(
            dbc.Checkbox(id='standalone-checkbox-'+elem.replace(' ', '-'))
        ),
        html.Td(
            elem
        ),
        html.Td(
           dbc.Badge(
               '__',#elem,
               color=elements[elem]['color']
            )
        ),
        html.Td(
            dbc.Input(
                id='z-'+elem.replace(' ', '-'),
                value=0,
                type='number',
                min=0,
                max=10,
                step=0.0000001,
                placeholder='z'
            )
        ),
        html.Td(
            dbc.Input(
                id='v-'+elem.replace(' ', '-'),
                type='number',
                placeholder='Velocity (km/s)',
                value=0
            )
        )
    ])
    elem_input_array.append(row)
table_body_two =[html.Tbody(elem_input_array)]

app.layout = html.Div([
    dcc.Graph(id='table-editing-simple-output',
              figure = {'layout' : {'height': 350,
                                    'margin': {'l': 60, 'b': 30, 'r': 60, 't': 10},
                                    'yaxis': {'type': 'linear'},
                                    'xaxis': {'showgrid': False}
                                    },
                        'data' : []#[go.Scatter({'x': [], 'y': []})]
                    }
    ),
    dcc.Input(id='target_id', type='hidden', value=0),
    dcc.Input(id='target_redshift', type='hidden', value=0),
    dcc.Input(id='min-flux', type='hidden', value=0),
    dcc.Input(id='max-flux', type='hidden', value=0),
    dcc.Checklist(
        id='line-plotting-checklist',
        options=[{'label': 'Show line plotting interface', 'value': 'display'}],
        value=''
    ),
    html.Div(
        children=[],
        id='checked-rows',
        style={'display': 'none'}
    ),
    html.Div(
        children=[
            dbc.Row([
                dbc.Table(
                    html.Tbody([
                        html.Tr([
                            html.Td(
                                dbc.Table(table_body_one, bordered=True),
                            ),
                            html.Td(
                                dbc.Table(table_body_two, bordered=True),
                            )
                        ]),
                    ])
                )
            ])
        ],
        id='table-container-div',
        style={'display': 'none'}
    )
])

@app.callback(
    Output('table-container-div', 'style'),
    [Input('line-plotting-checklist', 'value')])
def show_table(value, *args, **kwargs):
    if 'display' in value:
        return {'display': 'block'}
    else:
        return {'display': 'none'}

line_plotting_input = [Input('standalone-checkbox-'+elem.replace(' ', '-'), 'checked') for elem in elements]
line_plotting_input += [Input('v-'+elem.replace(' ', '-'), 'value') for elem in elements]
line_plotting_input += [Input('z-'+elem.replace(' ', '-'), 'value') for elem in elements]
@app.callback(
    Output('checked-rows', 'children'),
    line_plotting_input)
def checked_boxes(*args, **kwargs):
    
    all_rows = [item for item in line_plotting_input if 'standalone-checkbox' in item.component_id]
    velocity_rows = [item for item in line_plotting_input if 'v-' in item.component_id]
    redshift_rows = [item for item in line_plotting_input if 'z-' in item.component_id]
    
    checked_rows = []
    for i in range(len(all_rows)):
        if args[i]:
            elem = list(elements.keys())[i]
            checked_rows.append(json.dumps({elem: {'redshift': args[i+2*len(all_rows)],
                                                   'velocity': args[i+len(all_rows)]
                                                }
                                            })
                                        )
    return checked_rows

@app.callback(
    Output('table-container-div', 'children'),
    [Input('target_redshift', 'value')])
def change_redshift(z, *args, **kwargs):
    elem_input_array = []
    for elem in list(elements.keys())[:9]:
        row = html.Tr([
            html.Td(
                dbc.Checkbox(id='standalone-checkbox-'+elem.replace(' ', '-'))
            ),
            html.Td(
                elem
            ),
            html.Td(
               dbc.Badge(
                   '__',#elem,
                   color=elements[elem]['color']
                )
            ),
            html.Td(
                dbc.Input(
                    id='z-'+elem.replace(' ', '-'),
                    value=z,
                    type='number',
                    min=0,
                    max=10,
                    step=0.0000001,
                    placeholder='z'
                )
            ),
            html.Td(
                dbc.Input(
                    id='v-'+elem.replace(' ', '-'),
                    type='number',
                    placeholder='Velocity (km/s)',
                    value=0
                )
            )
        ])
        elem_input_array.append(row)
    table_body_one = [html.Tbody(elem_input_array)]
    
    elem_input_array = []
    for elem in list(elements.keys())[9:]:
        row = html.Tr([
            html.Td(
                dbc.Checkbox(id='standalone-checkbox-'+elem.replace(' ', '-'))
            ),
            html.Td(
                elem
            ),
            html.Td(
               dbc.Badge(
                   '__',#elem,
                   color=elements[elem]['color']
                )
            ),
            html.Td(
                dbc.Input(
                    id='z-'+elem.replace(' ', '-'),
                    value=z,
                    type='number',
                    min=0,
                    max=10,
                    step=0.0000001,
                    placeholder='z'
                )
            ),
            html.Td(
                dbc.Input(
                    id='v-'+elem.replace(' ', '-'),
                    type='number',
                    placeholder='Velocity (km/s)',
                    value=0
                )
            )
        ])
        elem_input_array.append(row)
    table_body_two = [html.Tbody(elem_input_array)]
    return [dbc.Row([
                dbc.Table(
                    html.Tbody([
                        html.Tr([
                            html.Td(
                                dbc.Table(table_body_one, bordered=True),
                            ),
                            html.Td(
                                dbc.Table(table_body_two, bordered=True),
                            )
                        ]),
                    ])
                )
            ])
        ]

@app.expanded_callback(
    Output('table-editing-simple-output', 'figure'),
    [Input('checked-rows', 'children'),
     Input('target_id', 'value'),
     Input('min-flux', 'value'),
     Input('max-flux', 'value'),
     State('table-editing-simple-output', 'figure')])
def display_output(selected_rows,
                   #selected_row_ids, columns, 
                   value, min_flux, max_flux, fig_data, *args, **kwargs):
    # Improvements:
    #   Fix dataproducts so they're correctly serialized
    #   Correctly display message when there are no spectra
    
    target_id = value
    if fig_data:
        graph_data = {'data': fig_data['data'],
                      'layout': fig_data['layout']}
    else:
        graph_data = {'data': [],
                      'layout': []}

    # If the page just loaded, plot all the spectra
    if not fig_data['data']:
        spectral_dataproducts = ReducedDatum.objects.filter(target_id=target_id, data_type='spectroscopy').order_by('timestamp')
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
                    wavelength.append(float(value['wavelength']))
                    flux.append(float(value['flux']))
            
            binned_wavelength, binned_flux = bin_spectra(wavelength, flux, 5)
            scatter_obj = go.Scatter(
                x=binned_wavelength,
                y=binned_flux,
                name=name,
                line_color=rgb_colors[i]
            )
            graph_data['data'].append(scatter_obj)

    for d in reversed(fig_data['data']):
        if d['name'] in elements:
            # Remove all the element lines that were plotted last time
            fig_data['data'].remove(d)
    
    for row in selected_rows:
        for elem, row_extras in json.loads(row).items():
            z = row_extras['redshift']
            if not z:
                z = 0
            v = row_extras['velocity']
            if not v:
                v = 0
            try:
                v_over_c = float(v/(3e5))
            except:
                v_over_c = 0
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
    return graph_data
