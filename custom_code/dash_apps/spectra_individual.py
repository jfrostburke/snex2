import dash
from dash.dependencies import Input, Output, State
import dash_table
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import numpy as np
import json
from statistics import median

### Jamie's Dash spectra plotting, currently a WIP
### Jamie: "lots of help from https://community.plot.ly/t/django-and-dash-eads-method/7717"

from django_plotly_dash import DjangoDash
from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target, TargetExtra
from custom_code.templatetags.custom_code_tags import bin_spectra
from django.db.models import Q
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = DjangoDash(name='Spectra_Individual', id='spectrum_id')   # replaces dash.Dash

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
    dcc.Input(id='spectrum_id', type='hidden', value=0),
    dcc.Input(id='target_redshift', type='hidden', value=0),
    dcc.Input(id='min-flux', type='hidden', value=0),
    dcc.Input(id='max-flux', type='hidden', value=0),
    html.Div('Binning Factor: ', style={'color': 'black', 'fontSize': 18}),
    dcc.Input(id='bin-factor', type='number', value=5, size=2),
    dcc.Checklist(
        id='line-plotting-checklist',
        options=[{'label': 'Show line plotting interface', 'value': 'display'}],
        value='',
        style={'fontSize': 18}
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
    ),
    dcc.Checklist(
        id='compare-spectra-checklist',
        options=[{'label': 'Compare this spectrum to another object?', 'value': 'display'}],
        value='',
        style={'fontSize': 18}
    ),
    html.Div([
        dbc.Input(id='spectra-compare-input', type='text', placeholder='Search for target', value='', style={'display': 'none'}),
        html.Div(
            children=[ 
                dcc.Dropdown(
                    options=[{'label': target.name, 'value': target.name} for target in Target.objects.all()],
                    value='',
                    placeholder='Search for a target',
                    id='spectra-compare-dropdown',
                    style={'z-index': '10'}
                )
            ],
            id='spectra-compare-results',
            style={'display': 'none'}
        )
    ])
], style={'padding-bottom': '0px'})

@app.callback(
    Output('table-container-div', 'style'),
    [Input('line-plotting-checklist', 'value')])
def show_table(value, *args, **kwargs):
    if 'display' in value:
        return {'display': 'block'}
    else:
        return {'display': 'none'}

@app.callback(
    Output('spectra-compare-results', 'style'),
    [Input('compare-spectra-checklist', 'value')])
def show_compare(value, *args, **kwargs):
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
def checked_boxes(h_row, he_row, he_ii_row, o_row, o_ii_row, o_iii_row, na_row, mg_row, mg_ii_row, 
                  si_ii_row, s_ii_row, ca_ii_row, fe_ii_row, fe_iii_row, c_ii_row, 
                  galaxy_row, tellurics_row, sn_ia_row,
                  h_v, he_v, he_ii_v, o_v, o_ii_v, o_iii_v, na_v, mg_v, 
                  mg_ii_v, si_ii_v, s_ii_v, ca_ii_v, fe_ii_v, fe_iii_v, c_ii_v,
                  galaxy_v, tellurics_v, sn_ia_v,
                  h_z, he_z, he_ii_z, o_z, o_ii_z, o_iii_z, na_z, mg_z, 
                  mg_ii_z, si_ii_z, s_ii_z, ca_ii_z, fe_ii_z, fe_iii_z, c_ii_z,
                  galaxy_z, tellurics_z, sn_ia_z, *args, **kwargs):
    
    all_rows = [h_row, he_row, he_ii_row, o_row, o_ii_row, o_iii_row, na_row, mg_row, 
                mg_ii_row, si_ii_row, s_ii_row, ca_ii_row, fe_ii_row, fe_iii_row, c_ii_row,
                galaxy_row, tellurics_row, sn_ia_row]

    velocity_rows = [h_v, he_v, he_ii_v, o_v, o_ii_v, o_iii_v, na_v, mg_v, 
                  mg_ii_v, si_ii_v, s_ii_v, ca_ii_v, fe_ii_v, fe_iii_v, c_ii_v,
                  galaxy_v, tellurics_v, sn_ia_v]

    redshift_rows = [h_z, he_z, he_ii_z, o_z, o_ii_z, o_iii_z, na_z, mg_z, 
                  mg_ii_z, si_ii_z, s_ii_z, ca_ii_z, fe_ii_z, fe_iii_z, c_ii_z,
                  galaxy_z, tellurics_z, sn_ia_z]

    checked_rows = []
    count = 0
    for row in all_rows:
        if row:
            elem = list(elements.keys())[count]
            checked_rows.append(json.dumps({elem: {'redshift': redshift_rows[count],
                                        'velocity': velocity_rows[count]
                                    }
                                }))
        count += 1
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
     Input('spectrum_id', 'value'),
     Input('min-flux', 'value'),
     Input('max-flux', 'value'),
     Input('bin-factor', 'value'),
     Input('spectra-compare-dropdown', 'value'),
     State('table-editing-simple-output', 'figure')])
def display_output(selected_rows,
                   #selected_row_ids, columns, 
                   value, min_flux, max_flux, bin_factor, compare_target, fig_data, *args, **kwargs):
    # Improvements:
    #   Fix dataproducts so they're correctly serialized
    #   Correctly display message when there are no spectra
    spectrum_id = value
    graph_data = {'data': fig_data['data'],#[],
                  'layout': fig_data['layout']}

    if compare_target:
        compared = False
        # Check if comparison spectra are already plotted
        for d in reversed(graph_data['data']):
            if '---' in d['name']:
                compared = True
                break
        
        if not compared:
            # Plot this spectrum and the spectrum for the selected target, normalized to the median
            graph_data['data'] = []
            
            min_flux = 0
            max_flux = 0

            spectrum = ReducedDatum.objects.get(id=spectrum_id)
       
            object_z_query = TargetExtra.objects.filter(target_id=spectrum.target_id,key='redshift').first()
            if not object_z_query:
                object_z = 0
            else:
                object_z = float(object_z_query.value)

            if not spectrum:
                return 'No spectra yet'
                
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
                    
            median_flux = [f / median(flux) for f in flux]
            if max(median_flux) > max_flux: max_flux = max(median_flux)

            if not bin_factor:
                bin_factor = 1
            binned_wavelength, binned_flux = bin_spectra(wavelength, median_flux, int(bin_factor))
            
            scatter_obj = go.Scatter(
                x=binned_wavelength,
                y=binned_flux,
                name='This Target',
                line_color='black'
            )
            graph_data['data'] = [scatter_obj]

            target = Target.objects.filter(Q(name__icontains=compare_target) | Q(aliases__name__icontains=compare_target)).first()
            
            compare_z_query = TargetExtra.objects.filter(target_id=target.id,key='redshift').first()
            if not compare_z_query:
                compare_z = 0
            else:
                compare_z = float(compare_z_query.value)

            spectral_dataproducts = ReducedDatum.objects.filter(target=target, data_type='spectroscopy').order_by('-timestamp')
            for spectrum in spectral_dataproducts:
                datum = spectrum.value
                wavelength = []
                flux = []
                name = target.name + ' --- ' +  str(spectrum.timestamp).split(' ')[0]
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
                shifted_wavelength = [w * (1+object_z) / (1+compare_z) for w in wavelength]
                median_flux = [f / median(flux) for f in flux]
                if max(median_flux) > max_flux: max_flux = max(median_flux)
                
                if not bin_factor:
                    bin_factor = 1
                binned_wavelength, binned_flux = bin_spectra(wavelength, median_flux, int(bin_factor))
                
                scatter_obj = go.Scatter(
                    x=binned_wavelength,
                    y=binned_flux,
                    name=name
                )
                graph_data['data'].append(scatter_obj)
            return graph_data
        
    # Remove all the element lines so we can replot the selected ones later
    for d in reversed(graph_data['data']):
        if d['name'] in elements.keys():
            graph_data['data'].remove(d)
    
    # If the page just loaded, plot all the spectra
    if not graph_data['data']:
        logger.info('Plotting dash spectrum for dataproduct %s', spectrum_id)
        spectrum = ReducedDatum.objects.get(id=spectrum_id)
 
        if not spectrum:
            return 'No spectra yet'
            
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
        
        if not bin_factor:
            bin_factor = 1
        binned_wavelength, binned_flux = bin_spectra(wavelength, flux, int(bin_factor))
        scatter_obj = go.Scatter(
            x=binned_wavelength,
            y=binned_flux,
            name=name,
            line_color='black'
        )
        graph_data['data'].append(scatter_obj)
        return graph_data

    if not compare_target:
        # Replot the spectrum with correct binning
        for d in reversed(graph_data['data']):
            if d['name'] not in elements.keys():
                graph_data['data'].remove(d)

        spectrum = ReducedDatum.objects.get(id=spectrum_id)

        if not spectrum:
            return 'No spectra yet'

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

        if not bin_factor:
            bin_factor = 1
        binned_wavelength, binned_flux = bin_spectra(wavelength, flux, int(bin_factor))
        scatter_obj = go.Scatter(
            x=binned_wavelength,
            y=binned_flux,
            name=name,
            line_color='black'
        )
        graph_data['data'].append(scatter_obj)
    
    for row in selected_rows:
        for elem, row_extras in json.loads(row).items():
            z = row_extras['redshift']
            v = row_extras['velocity']
            try:
                v_over_c = float(v/(3e5))
            except:
                v_over_c = 0
        x = []
        y = []
        
        lambda_rest = elements[elem]['waves']
        if compare_target:
            max_flux = max([max(d['y']) for d in graph_data['data'] if d['name'] not in elements.keys()])
            min_flux = min([min(d['y']) for d in graph_data['data'] if d['name'] not in elements.keys()])
        for lambduh in lambda_rest:

            lambda_observed = lambduh*((1+z)-v_over_c)
    
            x.append(lambda_observed)
            x.append(lambda_observed)
            x.append(None)
            y.append(min_flux)
            y.append(max_flux)
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
