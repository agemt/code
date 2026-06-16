import dash
from dash import html, dcc, callback, Input, Output, State, ALL, MATCH, no_update
import dash_bootstrap_components as dbc
import pandas as pd

from dash_helpers import build_card, build_graph

dash.register_page(__name__, path='/graphs', name='Graphing View')

layout = html.Div([
    dcc.RadioItems(
        id={'type': 'selector', 'index': 'size'},
        options={
            '4': 'Small',
            '6': 'Medium',
            '12': 'Large'
        },
        value=None,
        inline=True
    ),

    dcc.Loading(
        dbc.Row(id={'type': 'graph-cards', 'index': 'main'}, className="mb-5"),
        id="loading",
        type="default"
    )
])

@callback(
    Output({'type': 'graphcard', 'index': MATCH}, 'figure'),
    Input('active-ids-store', 'data'),
    Input('session-dataframe', 'data'),
    Input('session-config', 'data'),
    State({'type': 'graphcard', 'index': MATCH}, 'id'),
)
def update_individual_graphs(active_ids, stored_df, stored_config, graph_id_dict):
    if not stored_df:
        return no_update
        
    df = pd.DataFrame(stored_df)
    current_graph_config = None
    
    for g in stored_config.get('graphs', []):
        if g['id'] == graph_id_dict['index']:
            current_graph_config = g
            break

    if not current_graph_config:
        return no_update
        
    fig = build_graph(current_graph_config, activeIDs=active_ids, dfa=df)
    return fig

@callback(
    Output({'type': 'graph-cards', 'index': ALL}, 'children'),
    Output('size-store', 'data'),
    Input({'type': 'selector', 'index': ALL}, 'value'),
    Input('session-dataframe', 'data'),
    Input('session-config', 'data'),
    Input('size-store', 'data'),
    State('active-ids-store', 'data'),
    State('url', 'pathname')
)
def change_size(value_list, stored_df, stored_config, stored_size, active_ids, pathname):
    if not value_list:
        return [], no_update
        
    if pathname != '/graphs':
        return [], no_update
        
    value = value_list[0] if value_list else None
    if value is None and stored_size is not None:
        value = stored_size
    elif value is None:
        return [no_update], no_update
        
    height = int(value)*3 + 40
    df = pd.DataFrame(stored_df)
    cards = build_card(stored_config.get('graphs', []), int(value), f"{height}vh", df, activeIDs=active_ids)
    return [cards], value
