import dash
from dash import dcc, html, Input, Output, State, ALL, MATCH, callback_context
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import json
import os

# The application uses Dash for the web app, Plotly for chart rendering,
# and Dash AG Grid for the interactive table. Pandas reads the Excel file
# and prepares the data, while NumPy helps with numeric arrays and type handling.

# Read project settings from the config file. This file controls most
# application behavior so that layout, graph definitions, and the data source
# can change without editing the Python code.
with open('config.json', 'r') as f:
    config = json.load(f)

# The Excel data source is declared in config.json with a file path and
# optionally a sheet name. The file path can be absolute or relative.
data_source = config.get('data_source', {})
file_path = data_source.get('file_path')
sheet_name = data_source.get('sheet_name', 0)
if not file_path:
    raise ValueError("config.json must include data_source.file_path pointing to the Excel workbook")
excel_path = file_path if os.path.isabs(file_path) else os.path.join(os.path.dirname(__file__), file_path)

# Load the data from the specified Excel sheet into a Pandas DataFrame.
df = pd.read_excel(excel_path, sheet_name=sheet_name)

# Round numeric values to a reasonable number of decimal places so the table
# and charts are easier to read.
numeric_cols = df.select_dtypes(include=[np.number]).columns
df[numeric_cols] = df[numeric_cols].round(3)

# Create an 'id' column if the data source did not already provide one.
# This ID is used to connect the table and graph interactions.
if 'id' not in df.columns:
    df['id'] = df.index.astype(str)

# ==============================================================================
# STEP 2: DATA CATEGORIZATION
# ============================================================================== 

# Some downstream code depends on having a Category column so the graphs can
# draw one trace per category. If the Excel sheet does not include Category,
# we create a default category for every row.
if 'Category' not in df.columns:
    df['Category'] = 'Default'

# ==============================================================================
# STEP 3: REUSABLE UI FUNCTIONS
# ============================================================================== 

# ==============================================================================

def create_figure(graph_cfg, active_ids=None):
    x_col = graph_cfg['x']
    y_col = graph_cfg['y']
    title = graph_cfg.get('title', f"{y_col} vs {x_col}")
    hover_col = graph_cfg.get('hover_data', 'Sample_Name') 
    
    # Start with an empty Plotly figure object. This is the container
    # for curves, markers, and layout settings.
    fig = go.Figure()
    
    # 1. Plot Scatter Points
    # We draw one scatter trace per Category so the legend and coloring stay
    # organized. Each category can have its own marker style defined in JSON.
    for cat in df['Category'].unique():
        cat_df = df[df['Category'] == cat]
        
        style = config.get('category_styles', {}).get(
            cat, {"color": "gray", "symbol": "circle", "size": 8} 
        )
        
        opacity = [1 if active_ids is None or str(i) in active_ids else 0.45 for i in cat_df['id']] if active_ids is not None else 1

        custom_data_arr = np.stack((cat_df['id'].astype(str), cat_df[hover_col].astype(str)), axis=-1)
        # customdata is a hidden array attached to each point. It lets us
        # carry the row ID and hover value back through click events.

        fig.add_trace(go.Scatter(
            x=cat_df[x_col], y=cat_df[y_col], mode='markers',
            name=cat, customdata=custom_data_arr,
            hovertemplate=(
                f"<b>{hover_col}</b>: %{{customdata[1]}}<br>" 
                f"<b>{x_col}</b>: %{{x}}<br>"
                f"<b>{y_col}</b>: %{{y}}<extra></extra>"
            ),
            marker=dict(
                color=style['color'], symbol=style['symbol'], 
                size=style['size'], opacity=opacity,
                line=dict(width=1, color='white') 
            )
        ))


    # 3. Apply layout and style settings for this figure.
    # The layout controls axis labels, drag behavior, grid lines, and more.
    layout_args = {
        'title': title,
        'xaxis_title': x_col,
        'yaxis_title': y_col,
        'uirevision': 'constant',
        'dragmode': 'pan',
        'margin': dict(l=40, r=40, t=60, b=40),
        'clickmode': 'event+select',
        'showlegend': False,
        'xaxis': {
            'showgrid': True,
            'gridcolor': 'rgba(200,200,200,0.25)',
            'gridwidth': 1,
            'zeroline': False,
            'showline': True,
            'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside',
            'ticklen': 5
        },
        'yaxis': {
            'showgrid': True,
            'gridcolor': 'rgba(200,200,200,0.25)',
            'gridwidth': 1,
            'zeroline': False,
            'showline': True,
            'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside',
            'ticklen': 5
        }
    }

    # Apply per-graph default axis ranges when configured in graph settings
    # If the graph configuration defines a default axis range, we apply it.
    # This is useful when you want the chart to open with a consistent zoom level.
    if 'x_range' in graph_cfg:
        layout_args['xaxis_range'] = graph_cfg['x_range']
    if 'y_range' in graph_cfg:
        layout_args['yaxis_range'] = graph_cfg['y_range']

    fig.update_layout(**layout_args)
    return fig

# ==============================================================================
# STEP 4: LAYOUT ASSEMBLY
# ==============================================================================

# Create the Dash application object. This is the central object that ties
# together the layout and callback functions.
app = dash.Dash(__name__)

DEFAULT_WRAPPER_STYLE = {
    'gridColumn': 'span 1',
    'backgroundColor': '#f9f9f9',
    'border': '1px solid #ddd',
    'borderRadius': '8px',
    'padding': '10px',
    'transition': 'all 0.3s ease',
    'height': '350px',
    'position': 'relative',
    'minWidth': '0',
    'boxSizing': 'border-box'
}
MAX_WRAPPER_STYLE = {**DEFAULT_WRAPPER_STYLE, 'gridColumn': 'span 3', 'height': '90vh', 'zIndex': 1000}

graph_ids = [g['id'] for g in config['graphs']]

graph_wrappers = []
# We create one graph wrapper per configured graph. Each wrapper contains
# the maximize button and a Plotly chart instance.
for g in config['graphs']:
    wrapper = html.Div(
        id={'type': 'graph-wrapper', 'index': g['id']}, 
        style=DEFAULT_WRAPPER_STYLE.copy(),
        children=[
            dcc.Store(id={'type': 'max-state', 'index': g['id']}, data=False),
            html.Div(
                html.Button("⛶ Maximize", id={'type': 'max-btn', 'index': g['id']}),
                style={'textAlign': 'right', 'marginBottom': '-10px', 'position': 'relative', 'zIndex': 10}
            ),
            dcc.Graph(
                id={'type': 'dynamic-graph', 'index': g['id']},
                figure=create_figure(g), 
                config={
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                    'modeBarButtonsToAdd': ['pan2d']
                },
                style={'height': '100%', 'width': '100%'}
            )
        ]
    )
    graph_wrappers.append(wrapper)

# Define the table columns based on the data frame.
# We skip internal helper columns like 'id' and 'Category' from the table display.
column_defs = []
for col in df.columns:
    if col in ['id', 'Category']: continue 
    col_def = {'field': col, 'sortable': True, 'filter': True}
    if col == 'Sample_Name':
        col_def.update({
            'pinned': 'left',
            'lockPinned': True,
            'lockPosition': True,
            'suppressMovable': True,
            'floatingFilter': True,
            'filter': 'agTextColumnFilter'
        })
    elif col in config['table_config']['locked_pinned_columns']:
        col_def.update({'pinned': 'left', 'lockPinned': True})
    elif col in config['table_config']['default_pinned_columns']:
        col_def['pinned'] = 'left'
    column_defs.append(col_def)

# Force Sample_Name to remain the leftmost column in the table.
# This improves usability because the primary identifier is always visible.
sample_name_col = next((c for c in column_defs if c['field'] == 'Sample_Name'), None)
if sample_name_col:
    column_defs = [sample_name_col] + [c for c in column_defs if c['field'] != 'Sample_Name']

# Build the page layout. Layout is a declarative description of the page
# structure: title, buttons, graphs, and the data table.
app.layout = html.Div([
    html.H2("Data Correlation Dashboard"),
    html.Div([
        html.Button("Reset View", id='reset-view-btn', n_clicks=0, style={'marginRight': '10px'}),
        html.Button("Deselect", id='deselect-btn', n_clicks=0)
    ], style={'marginBottom': '20px'}),
    html.Div(graph_wrappers, style={'display': 'grid', 'gridTemplateColumns': 'repeat(3, minmax(0, 1fr))', 'gap': '15px', 'marginBottom': '30px'}),
    dag.AgGrid(
        id='data-table', rowData=df.to_dict('records'), columnDefs=column_defs, getRowId="params.data.id",
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={"animateRows": True},
        style={"height": "400px", "width": "100%"}
    )
], style={'padding': '20px'})


# ==============================================================================
# STEP 5: CALLBACKS
# ==============================================================================

# This callback tracks whether each graph is in maximized mode.
# It stores per-graph state in hidden dcc.Store components.
@app.callback(
    Output({'type': 'max-state', 'index': ALL}, 'data'),
    Input({'type': 'max-btn', 'index': ALL}, 'n_clicks'),
    Input('reset-view-btn', 'n_clicks'),
    State({'type': 'max-state', 'index': ALL}, 'data'),
    prevent_initial_call=True
)
def update_max_states(max_btn_clicks, reset_clicks, current_states):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update
    # callback_context tells us which input caused the current callback.
    # This is important when a callback has multiple Inputs.
    trigger = ctx.triggered[0]['prop_id']
    if 'reset-view-btn' in trigger:
        return [False] * len(graph_ids)
    if not current_states:
        current_states = [False] * len(graph_ids)
    try:
        triggered_id = json.loads(trigger.split('.')[0])
        clicked_idx = triggered_id['index']
    except Exception:
        return [False] * len(graph_ids)
    return [not state if idx == clicked_idx else False for idx, state in zip(graph_ids, current_states)]

@app.callback(
    Output({'type': 'graph-wrapper', 'index': ALL}, 'style'),
    Output({'type': 'max-btn', 'index': ALL}, 'children'),
    Input({'type': 'max-state', 'index': ALL}, 'data'),
)
def apply_maximize_state(max_states):
    styles = []
    labels = []
    for state in max_states:
        if state:
            style = MAX_WRAPPER_STYLE.copy()
            style['gridColumn'] = '1 / -1'
            style['width'] = '100%'
            styles.append(style)
            labels.append("🗕 Minimize")
        else:
            styles.append(DEFAULT_WRAPPER_STYLE.copy())
            labels.append("⛶ Maximize")
    return styles, labels

# This callback turns graph clicks and table clicks into table filtering.
# Clicking a point or a Sample_Name cell filters the table to that row.
# Clicking Deselect clears the filter and shows all rows again.
@app.callback(
    Output('data-table', 'filterModel'),
    Input({'type': 'dynamic-graph', 'index': ALL}, 'clickData'),
    Input('data-table', 'cellClicked'),
    Input('deselect-btn', 'n_clicks'),
    prevent_initial_call=True
)
def update_filter_model(click_data_list, cell_click, deselect_clicks):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update
    trigger = ctx.triggered[0]['prop_id']
    if 'deselect-btn' in trigger:
        return {}
    if 'data-table' in trigger and '.cellClicked' in trigger:
        if not cell_click or cell_click.get('colId') != 'Sample_Name':
            return dash.no_update
        clicked_name = cell_click.get('value')
        if clicked_name is None:
            return dash.no_update
        return {
            'Sample_Name': {
                'filterType': 'text',
                'type': 'equals',
                'filter': clicked_name
            }
        }
    if 'dynamic-graph' in trigger and click_data_list:
        for click_data in click_data_list:
            if click_data and 'points' in click_data:
                clicked_id = str(click_data['points'][0]['customdata'][0])
                clicked_name = df.loc[df['id'] == clicked_id, 'Sample_Name'].squeeze()
                return {
                    'Sample_Name': {
                        'filterType': 'text',
                        'type': 'equals',
                        'filter': clicked_name
                    }
                }
    return {}

# This callback updates all graphs whenever the table's filtered rows change.
# Table filtering is the primary way we synchronize selected data across
# the table and the graphs. The graphs use the current visible rows to
# decide which points should remain fully opaque.
@app.callback(
    Output({'type': 'dynamic-graph', 'index': ALL}, 'figure'),
    Input('data-table', 'virtualRowData'),
)
def sync_graphs_to_table(virtual_rows):
    if virtual_rows is None:
        active_ids = None
    else:
        active_ids = None if len(virtual_rows) == len(df) else [str(row['id']) for row in virtual_rows]
    return [create_figure(g, active_ids) for g in config['graphs']]

if __name__ == '__main__':
    app.run(debug=True)