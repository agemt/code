import dash
from dash import html, Input, Output, callback, no_update
import pandas as pd
from dash_helpers import build_grid

dash.register_page(__name__, path='/', name='Table View')

layout = html.Div([
    html.Div(id='grid-container', style={'height': 400}, className="ag-theme-quartz")
])

@callback(
    Output('grid-container', 'children'),
    Input('session-dataframe', 'data'),
    Input('session-config', 'data'),
)
def render_grid(stored_df, config):
    if not stored_df:
        return html.Div("No data available.")
    df = pd.DataFrame(stored_df)
    return build_grid(config, df)

@callback(
    Output('active-ids-store', 'data'),
    Input('data-grid', 'virtualRowData'),
    prevent_initial_call=True
)
def sync_filtered_data(virtual_data):
    if not virtual_data:
        return no_update
    filtered_ids = [row.get('sequential_id') for row in virtual_data if row.get('sequential_id') is not None]
    return filtered_ids
