import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from dash.dependencies import Input, Output
import json
from django_plotly_dash import DjangoDash
from tom_dataproducts.models import ReducedDatum
from custom_code.models import ReducedDatumExtra

app = DjangoDash(name='Lightcurve')
telescopes = ['', 'LCO', 'Swift']
app.layout = html.Div([
    dcc.Graph(
        id='lightcurve-plot'
    ),
    dcc.Input(
        id='target_id',
        type='hidden',
        value=0
    ),
    dcc.Dropdown(
        id='telescopes-dropdown',
        options=[{'label': k, 'value': k} for k in telescopes],
        value=''
    ),
    html.Hr(),
    dcc.Dropdown(
        id='subtracted-dropdown',
        options=[{'label': 'Unsubtracted', 'value': 'Unsubtracted'},
                 {'label': 'Subtracted', 'value': 'Subtracted'}
        ],
        value='Unsubtracted',
        style={'display': 'none'}
    ), 
    html.Hr(),
    html.Div(
        id='display-selected-values')
])

@app.callback(
        Output('subtracted-dropdown', 'style'),
        [Input('telescopes-dropdown', 'value')])
def update_style(selected_telescope):
    if selected_telescope=='LCO':
        return {}
    else:
        return {'display': 'none'}

@app.callback(
        Output('display-selected-values', 'children'),
        [Input('telescopes-dropdown', 'value'),
         Input('subtracted-dropdown', 'value'),
         Input('target_id', 'value')])
def set_display_children(selected_telescope, selected_subtr, value):
       return u'Telescope {} with subtraction {} for id {}'.format(selected_telescope, selected_subtr, value) 


@app.callback(
        Output('lightcurve-plot', 'figure'),
        [Input('telescopes-dropdown', 'value'),
         Input('target_id', 'value')])
def update_graph(selected_telescope, value):
    def get_color(filter_name):
        filter_translate = {'U': 'U', 'B': 'B', 'V': 'V',
            'g': 'g', 'gp': 'g', 'r': 'r', 'rp': 'r', 'i': 'i', 'ip': 'i',
            'g_ZTF': 'g_ZTF', 'r_ZTF': 'r_ZTF', 'i_ZTF': 'i_ZTF', 'UVW2': 'UVW2', 'UVM2': 'UVM2',
            'UVW1': 'UVW1'}
        colors = {'U': 'rgb(59,0,113)',
            'B': 'rgb(0,87,255)',
            'V': 'rgb(120,255,0)',
            'g': 'rgb(0,204,255)',
            'r': 'rgb(255,124,0)',
            'i': 'rgb(144,0,43)',
            'g_ZTF': 'rgb(0,204,255)',
            'r_ZTF': 'rgb(255,124,0)',
            'i_ZTF': 'rgb(144,0,43)',
            'UVW2': '#FE0683',
            'UVM2': '#BF01BC',
            'UVW1': '#8B06FF',
            'other': 'rgb(0,0,0)'}
        try: color = colors[filter_translate[filter_name]]
        except: color = colors['other']
        return color
    
    target_id = value
    photometry_data = {}
    datumextras = ReducedDatumExtra.objects.filter(key='upload_extras', data_type='photometry')
    
    datums = []
    if not selected_telescope:
        datums.append(ReducedDatum.objects.filter(target_id=target_id, data_type='photometry'))
    
    else:
        dp_ids = []
        dataproduct_id_query = ReducedDatum.objects.filter(target_id=target_id, data_type='photometry').order_by().values('data_product_id').distinct()
        for j in dataproduct_id_query:
            dp_ids.append(j['data_product_id'])
        for de in datumextras:
            de_value = json.loads(de.value)
            if de_value.get('instrument', '') == selected_telescope and de_value.get('data_product_id', '') in dp_ids:
                dp_id = de_value.get('data_product_id', '')
                datums.append(ReducedDatum.objects.filter(target_id=target_id, data_type='photometry', data_product_id=dp_id))
        if selected_telescope == 'LCO':
            datums.append(ReducedDatum.objects.filter(target_id=target_id, data_type='photometry', data_product_id__isnull=True))
    
    if not datums:
        return 'No photometry yet'
    for data in datums:
        for rd in data:
            value = json.loads(rd.value)
            if not value:
                continue

            #data_product_id = rd.data_product_id
            photometry_data.setdefault(value.get('filter', ''), {})
            photometry_data[value.get('filter', '')].setdefault('time', []).append(rd.timestamp)
            photometry_data[value.get('filter', '')].setdefault('magnitude', []).append(value.get('magnitude',None))
            photometry_data[value.get('filter', '')].setdefault('error', []).append(value.get('error', None))
    plot_data = [
        go.Scatter(
            x=filter_values['time'],
            y=filter_values['magnitude'], mode='markers',
            marker=dict(color=get_color(filter_name)),
            name=filter_name,
            error_y=dict(
                type='data',
                array=filter_values['error'],
                visible=True,
                color=get_color(filter_name)
            )
        ) for filter_name, filter_values in photometry_data.items()]

    graph_data = {'data': plot_data}

    layout = go.Layout(
        xaxis=dict(gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        yaxis=dict(autorange='reversed',gridcolor='#D3D3D3',showline=True,linecolor='#D3D3D3',mirror=True),
        margin=dict(l=30, r=10, b=30, t=40),
        hovermode='closest',
        #height=200,
        #width=250,
        showlegend=True,
        plot_bgcolor='white'
    )

    graph_data['layout'] = layout

    return graph_data


