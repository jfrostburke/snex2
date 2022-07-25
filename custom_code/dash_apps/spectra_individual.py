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
from django.templatetags.static import static
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = DjangoDash(name='Spectra_Individual', id='spectrum_id', add_bootstrap_links=True, suppress_callback_exceptions=True)   # replaces dash.Dash
app.css.append_css({'external_url': static('custom_code/css/dash.css')})

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

table_body_one =[html.Tbody([])]
table_body_two =[html.Tbody([])]

app.layout = html.Div([
    dcc.Graph(id='table-editing-simple-output',
              figure = {'layout' : {'height': 350,
                                    'margin': {'l': 60, 'b': 30, 'r': 60, 't': 10},
                                    'yaxis': {'type': 'linear'},
                                    'xaxis': {'showgrid': False},
                                    'legend': {'x': 0.85, 'y': 1.0},
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
        html.Form(
            autoComplete='off',
            children=[ 
                dcc.Dropdown(
                    options=[{'label': '', 'value': ''}],
                    value='',
                    placeholder='Search for a target',
                    id='spectra-compare-dropdown',
                    style={'z-index': '10'}
                )
            ],
            id='spectra-compare-results',
            style={'display': 'none'}
        )
    ]),
    dcc.Checklist(
        id='mask-lines-checklist',
        options=[{'label': 'Mask galaxy emission lines', 'value': 'mask'}],
        value='',
        style={'fontSize': 18}
    ),
], style={'padding-bottom': '0px'})


@app.callback(
    Output('spectra-compare-dropdown', 'options'),
    [Input('spectra-compare-dropdown', 'search_value'),
     State('spectra-compare-dropdown', 'value')])
def get_target_list(value, existing, *args, **kwargs):
    if existing:
        target_match_list = Target.objects.filter(name=existing)
        if not target_match_list.first():
            target_match_list = Target.objects.filter(aliases__name__icontains=existing)
            names = []
            for target in target_match_list:
                names += [{'label': n, 'value': n} for n in target.names if n==existing]
                return names
        else:
            return [{'label': target.name, 'value': target.name} for target in target_match_list]
    
    elif value:
        target_match_list = Target.objects.filter(Q(name__icontains=value) | Q(aliases__name__icontains=value)).distinct()
    else:
        target_match_list = Target.objects.none()
    names = [{'label': '', 'value': ''}]
    for target in target_match_list:
        names += [{'label': n, 'value': n} for n in target.names]
    return names


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


line_plotting_input = [Input('standalone-checkbox-'+elem.replace(' ', '-'), 'checked') for elem in elements]+[Input('standalone-checkbox-custom1', 'checked'), Input('standalone-checkbox-custom2', 'checked')]
line_plotting_input += [Input('v-'+elem.replace(' ', '-'), 'value') for elem in elements]+[Input('v-custom1', 'value'), Input('v-custom2', 'value')]
line_plotting_input += [Input('z-'+elem.replace(' ', '-'), 'value') for elem in elements]+[Input('z-custom1', 'value'), Input('z-custom2', 'value')]
line_plotting_input += [Input('lambda-custom1', 'value'), Input('lambda-custom2', 'value')]
@app.callback(
    Output('checked-rows', 'children'),
    line_plotting_input)
def checked_boxes(*args, **kwargs):
    all_rows = [item for item in line_plotting_input if 'standalone-checkbox' in item.component_id]
    
    checked_rows = []
    for i in range(len(all_rows)):
        if args[i] and i < len(all_rows) - 2:
            elem = list(elements.keys())[i]
            checked_rows.append(json.dumps({elem: {'waves': elements[elem]['waves'],
                                                   'redshift': args[i+2*len(all_rows)],
                                                   'velocity': args[i+len(all_rows)],
                                                   'color': elements[elem]['color']
                                                } 
                                            })
                                        )
        elif args[i] and i == len(all_rows) - 2:
            # Custom wavelength entry
            checked_rows.append(json.dumps({'custom1': {'waves': [args[-2]],
                                                        'redshift': args[i+2*len(all_rows)],
                                                        'velocity': args[i+len(all_rows)],
                                                        'color': '#c7b299'
                                                    }
                                            })
                                        )
        elif args[i] and i == len(all_rows) - 1:
            # Custom wavelength entry
            checked_rows.append(json.dumps({'custom2': {'waves': [args[-1]],
                                                        'redshift': args[i+2*len(all_rows)],
                                                        'velocity': args[i+len(all_rows)],
                                                        'color': '#837565'
                                                    }
                                            })
                                        )
    return checked_rows


@app.callback(
    Output('table-container-div', 'children'),
    [Input('target_redshift', 'value')])
def change_redshift(z, *args, **kwargs):
    elem_input_array = []
    for elem in list(elements.keys())[:10]:
        row = html.Tr([
            html.Td(
                dbc.Checkbox(id='standalone-checkbox-'+elem.replace(' ', '-')),
                style={"padding-left": "1rem"},
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
                    placeholder='v = 0 (km/s)',
                    #value=0
                ),
                colSpan=2,
            ),
        ], style={'padding': '0rem'})
        elem_input_array.append(row)
    table_body_one = [html.Tbody(elem_input_array)]
    
    elem_input_array = []
    for elem in list(elements.keys())[10:]:
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
                    placeholder='v = 0 (km/s)',
                    #value=0
                ),
                colSpan=2,
            ),
        ])
        elem_input_array.append(row)
    elem_input_array.append(
        html.Tr([
            html.Td(
                dbc.Checkbox(id='standalone-checkbox-custom1')
            ),
            html.Td(
                html.Div([
                    dbc.Badge(
                        '__',
                        color='#c7b299'
                    ),
                    dbc.Input(
                        id='lambda-custom1',
                        type='number',
                        min=0,
                        max=1e5,
                        step=0.1,
                        placeholder='Wavelength'
                    )
                ]),
                colSpan=2
            ),
            html.Td(
                dbc.Input(
                    id='z-custom1',
                    type='number',
                    min=0,
                    max=10,
                    step=0.00000001,
                    placeholder='z',
                    value=z
                )
            ),
            html.Td(
                dbc.Input(
                    id='v-custom1',
                    type='number',
                    placeholder='v = 0 (km/s)',
                )
            )
        ])
    )
    elem_input_array.append(
        html.Tr([
            html.Td(
                dbc.Checkbox(id='standalone-checkbox-custom2')
            ),
            html.Td(
                html.Div([
                    dbc.Badge(
                        '__',
                        color='#837565'
                    ),
                    dbc.Input(
                        id='lambda-custom2',
                        type='number',
                        min=0,
                        max=1e5,
                        step=0.1,
                        placeholder='Wavelength'
                    )
                ]),
                colSpan=2
            ),
            html.Td(
                dbc.Input(
                    id='z-custom2',
                    type='number',
                    min=0,
                    max=10,
                    step=0.00000001,
                    placeholder='z',
                    value=z
                )
            ),
            html.Td(
                dbc.Input(
                    id='v-custom2',
                    type='number',
                    placeholder='v = 0 (km/s)',
                )
            )
        ])
    )
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
     Input('mask-lines-checklist', 'value'),
     State('table-editing-simple-output', 'figure')])
def display_output(selected_rows,
                   #selected_row_ids, columns, 
                   value, min_flux, max_flux, bin_factor, compare_target, mask_value, fig_data, *args, **kwargs):
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
                binned_wavelength, binned_flux = bin_spectra(shifted_wavelength, median_flux, int(bin_factor))
                
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

        if 'mask' in mask_value:
            object_z_query = TargetExtra.objects.filter(target_id=spectrum.target_id,key='redshift').first()
            if not object_z_query:
                object_z = 0
            else:
                object_z = float(object_z_query.value)

            pfit = np.poly1d(np.polyfit(wavelength, flux, 4))
            for galaxy_wave in elements['Galaxy']['waves']:
                mask = [abs(l-galaxy_wave*(1+object_z)) < 10 for l in wavelength]
                flux = np.ma.masked_array(flux, mask)
                median_flux = np.ma.median(np.ma.masked_array(pfit(wavelength), np.logical_not(mask)))
                flux = flux.filled(fill_value=median_flux)
            name += ' (galaxy lines masked)'

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
        graph_data['layout']['xaxis']['range'] = [min(binned_wavelength), max(binned_wavelength)]
        graph_data['layout']['xaxis']['autorange'] = False
        graph_data['layout']['yaxis']['range'] = [min(binned_flux), max(binned_flux)]
        graph_data['layout']['yaxis']['autorange'] = False
    
    for row in selected_rows:
        (elem, row_extras), = json.loads(row).items()
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
        lambda_rest = row_extras['waves']
        if not lambda_rest[0]:
            continue
        x = []
        y = []
        
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

        try:
            color = row_extras['color']
        except:
            color = 'black'

        graph_data['data'].append(
            go.Scatter(
                x=x,
                y=y,
                name=elem,
                mode='lines',
                line={'color': color},
            )
        )
    return graph_data
