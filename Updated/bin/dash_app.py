import dash
from dash import Dash, html, dcc, callback, Input, Output, no_update
import dash_bootstrap_components as dbc
import os
import pandas as pd

from dash_helpers import get_data

app = Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)

global config, dataframe
config, dataframe = get_data()

def serve_layout():
    global config, dataframe
    
    return html.Div([
        dcc.Store(id='session-config', data=config),
        dcc.Store(id='session-dataframe', data=dataframe.to_dict('records') if not dataframe.empty else []),
        dcc.Store(id='size-store', storage_type='local'),
        # Used to pass active IDs between table page and graphs page
        dcc.Store(id='active-ids-store', data=None),

        dbc.Container([
            html.H2(f"CFM56-5B Trending - {len(dataframe.get('sequential_id', []))} entries, {len(config.get('graphs', []))} graphs", style={'marginLeft': 20, 'marginTop': 20, 'marginBottom': 20}),
            dash.page_container,
            dcc.Location(id='url', refresh=False)
        ], fluid=True)
    ])

app.layout = serve_layout

@app.callback(
    Input('url', 'pathname'),
    prevent_initial_call=False
)
def detect_reload(pathname):
    global config, dataframe
    config, dataframe = get_data()

if __name__ == '__main__':
    prod = os.environ.get('prod') == 'true'
    app.run(debug=not prod, port=8050)
