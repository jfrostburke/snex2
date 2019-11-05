import dash
from dash.dependencies import Input, Output
import dash_table
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import numpy as np

#lots of help from https://community.plot.ly/t/django-and-dash-eads-method/7717

from django_plotly_dash import DjangoDash

app = DjangoDash(name='Spectra', id='color')   # replaces dash.Dash

"""
app.layout = html.Div([
    dcc.Graph(id='table-editing-simple-output'),
])

wave = [1000,2000,3000,4000,5000]
flux = [1,2,1,2,1]

@app.expanded_callback(
    Output('table-editing-simple-output', 'figure'),
    [Input('table-editing-simple', 'data')])
def display_output(**kwargs):
    graph_data = {'data':
        [
            go.Scatter(
                x=wave,
                y=flux,
                name='spectrum'
            )
        ]
    }
    graph_data['layout'] = go.Layout(
        xaxis={'title': 'Wave', 'type': 'linear'},
        yaxis={'title': 'Flux', 'type': 'linear'},
        height=450,
        hovermode='closest'
    )
    #import pdb; pdb.set_trace()
    print(graph_data)
    return graph_data

app.layout = html.Div([
    dcc.RadioItems(
        id='dropdown-color',
        options=[{'label': c, 'value': c.lower()} for c in ['Red', 'Green', 'Blue']],
        value='red'
    ),
    html.Div(id='output-color'),
    dcc.RadioItems(
        id='dropdown-size',
        options=[{'label': i, 'value': j} for i, j in [('L','large'), ('M','medium'), ('S','small')]],
        value='medium'
    ),
    html.Div(id='output-size')

])

@app.callback(
    dash.dependencies.Output('output-color', 'children'),
    [dash.dependencies.Input('dropdown-color', 'value')])
def callback_color(dropdown_value):
    return "The selected color is %s." % dropdown_value

@app.callback(
    dash.dependencies.Output('output-size', 'children'),
    [dash.dependencies.Input('dropdown-color', 'value'),
     dash.dependencies.Input('dropdown-size', 'value')])
def callback_size(dropdown_color, dropdown_size):
    return "The chosen T-shirt is a %s %s one." %(dropdown_size,
                                                  dropdown_color)

"""


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

# TODO: fix this spaghetti right here
wave = [1000,2000,3000,4000,5000]
flux = [1,2,1,2,1]

@app.expanded_callback(
    Output('table-editing-simple-output', 'figure'),
    [Input('table-editing-simple', 'data'),
     Input('table-editing-simple', 'selected_rows'),
     Input('table-editing-simple', 'columns')])
def display_output(rows, selected_row_ids, columns, *args, **kwargs):
    print(args)
    print(kwargs)
    graph_data = {'data':
        [
            go.Scatter(
                x=wave,
                y=flux,
                name='spectrum'
            )
        ]
    }
    
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
            y.append(min(flux)*0.95)
            y.append(max(flux)*1.05)
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
        'height': 225,
        'margin': {'l': 20, 'b': 30, 'r': 10, 't': 10},
        'yaxis': {'type': 'linear'},
        'xaxis': {'showgrid': False}
    }
    return graph_data


