import dash
# Core Dash components:
# dcc (Dash Core Components) for interactive elements like Graphs and Stores.
# html for standard HTML tags (Div, Button, H2).
# Input, Output, State for defining callback logic.
# ALL, MATCH for "pattern-matching callbacks" (handling multiple dynamic components).
# callback_context to figure out WHICH button triggered a callback.
from dash import dcc, html, Input, Output, State, ALL, MATCH, callback_context

# dash_ag_grid is a highly customizable, high-performance data table component
import dash_ag_grid as dag

# Plotly Graph Objects to build charts piece-by-piece (traces, layouts)
import plotly.graph_objects as go

# Pandas for data manipulation and Numpy for math/random data generation
import pandas as pd
import numpy as np
import json

# ==============================================================================
# STEP 1: CONFIGURATION & DATA LOADING
# ==============================================================================

# Load external configuration. This allows you to change graph layouts, colors,
# and limits without touching the Python code. 
with open('config.json', 'r') as f:
    config = json.load(f)

# Set a random seed so the "random" data is exactly the same every time you run the app.
# This makes debugging much easier.
np.random.seed(42)

# Create a synthetic dataset with 50 rows.
df = pd.DataFrame({
    'Sample_Name': [f'Item_{i}' for i in range(50)],
    'Date': pd.date_range(start='1/1/2026', periods=50),
    'Temperature': np.random.uniform(20.123, 100.987, 50),
    'Pressure': np.random.uniform(1.123, 5.987, 50),
    'Speed': np.random.uniform(100.123, 500.987, 50),
    'Vibration': np.random.uniform(0.012, 0.987, 50)
})

# Add an artificial linear trend to the last 10 points (index 40 to 49).
# We do this so our linear regression calculation later actually has a visible, 
# meaningful line to draw, rather than a flat line through pure noise.
df.loc[40:49, 'Temperature'] = np.linspace(20, 50, 10)
df.loc[40:49, 'Pressure'] = np.linspace(1, 3, 10) + np.random.normal(0, 0.2, 10)

# Clean up the numbers: round all numeric columns to 3 decimal places for visual neatness.
numeric_cols = df.select_dtypes(include=[np.number]).columns
df[numeric_cols] = df[numeric_cols].round(3)

# CRITICAL STEP: Create an explicit 'id' column as a string. 
# Dash AG Grid and Plotly cross-filtering rely heavily on unique string IDs to know
# exactly which row/point you clicked on.
df['id'] = df.index.astype(str)

# ==============================================================================
# STEP 2: DATA CATEGORIZATION
# ==============================================================================

# Assign categories to the data. This allows us to style specific points differently
# (e.g., make the 'Baseline' points a different shape/color in the scatter plot).
df['Category'] = 'Regular'
if len(df) > 0: df.loc[0, 'Category'] = 'First'
if len(df) > 1: df.loc[1, 'Category'] = 'Second'
if len(df) >= 10: df.loc[df.index[-10:], 'Category'] = 'Baseline (10 Oldest)'


# ==============================================================================
# STEP 3: REUSABLE UI FUNCTIONS 
# ==============================================================================

def create_figure(graph_cfg, active_ids=None):
    """
    Generates a Plotly scatter figure based on a configuration dictionary.
    
    Parameters:
    - graph_cfg: Dict from config.json telling us what x and y columns to use.
    - active_ids: List of string IDs that are currently "selected". If None, all are active.
    """
    x_col = graph_cfg['x']
    y_col = graph_cfg['y']
    title = graph_cfg.get('title', f"{y_col} vs {x_col}")
    hover_col = graph_cfg.get('hover_data', 'Sample_Name') 
    
    # Initialize an empty Plotly figure
    fig = go.Figure()
    
    # --- 1. Plot Scatter Points by Category ---
    # We loop through each category so we can apply different styles (colors, symbols)
    # to each group based on the config.json settings.
    for cat in df['Category'].unique():
        cat_df = df[df['Category'] == cat] # Filter to just this category
        
        # Get the style dictionary for this category, default to gray circle if missing.
        style = config.get('category_styles', {}).get(
            cat, {"color": "gray", "symbol": "circle", "size": 8} 
        )
        
        # Determine opacity: If there is a selection (active_ids isn't None), 
        # dim (0.45) all points whose ID is NOT in the active_ids list.
        if active_ids is not None:
            opacity = [1 if str(i) in active_ids else 0.45 for i in cat_df['id']]
        else:
            opacity = 1

        # CRITICAL TRICK: customdata
        # customdata allows us to attach hidden data to the graph points. 
        # We attach the 'id' (for callbacks to know what we clicked) and the hover_col name.
        # np.stack binds these two arrays into columns.
        custom_data_arr = np.stack((cat_df['id'].astype(str), cat_df[hover_col].astype(str)), axis=-1)

        # Add the scatter trace (a layer on the plot)
        fig.add_trace(go.Scatter(
            x=cat_df[x_col], y=cat_df[y_col], mode='markers',
            name=cat, 
            customdata=custom_data_arr, # Attach the hidden data
            # Format the hover tooltip using HTML and the customdata we just attached.
            hovertemplate=(
                f"<b>{hover_col}</b>: %{{customdata[1]}}<br>" 
                f"<b>{x_col}</b>: %{{x}}<br>"
                f"<b>{y_col}</b>: %{{y}}<extra></extra>" # <extra></extra> hides the ugly secondary box
            ),
            marker=dict(
                color=style['color'], symbol=style['symbol'], 
                size=style['size'], opacity=opacity,
                line=dict(width=1, color='white') 
            )
        ))

    # --- 2. Linear Correlation & Limits Logic ---
    # We want to draw a trendline ONLY based on the "Baseline (10 Oldest)" data points.
    b_config = config.get('baseline_config', {})
    show_center = b_config.get('show_center_line', False)
    center_style = b_config.get('center_style', {'color': 'gray', 'dash': 'dash', 'width': 1})
    limit_style = b_config.get('limit_style', {'color': 'red', 'dash': 'dot', 'width': 2})

    # Filter out empty values so the math doesn't crash
    baseline_df = df[df['Category'] == 'Baseline (10 Oldest)'].dropna(subset=[x_col, y_col])
    
    # Ensure we have enough valid numerical data to draw a line
    if len(baseline_df) > 1 and pd.api.types.is_numeric_dtype(baseline_df[x_col]) and pd.api.types.is_numeric_dtype(baseline_df[y_col]):
        x_base = baseline_df[x_col].astype(float).values
        y_base = baseline_df[y_col].astype(float).values
        
        # Calculate least squares regression (Equation of a line: y = mx + b)
        # m = slope, b = y-intercept. "1" means degree 1 (linear).
        m, b = np.polyfit(x_base, y_base, 1)
        
        # Calculate residuals (the difference between actual Y values and predicted Y values on the line)
        residuals = y_base - (m * x_base + b)
        std_res = np.std(residuals) # Standard deviation of those differences
        
        # We want the lines to stretch across the whole graph, not just where the baseline data is.
        # So we get the absolute min and max of the X axis across the WHOLE dataset.
        x_min, x_max = df[x_col].min(), df[x_col].max()
        x_line = np.array([x_min, x_max])
        
        # Calculate the Y values at the absolute X min/max to draw the lines
        y_center = m * x_line + b
        y_upper = y_center + (2 * std_res) # Upper limit (Center + 2 standard deviations)
        y_lower = y_center - (2 * std_res) # Lower limit (Center - 2 standard deviations)
        
        # Draw the Upper Limit line
        fig.add_trace(go.Scatter(
            x=x_line, y=y_upper, mode='lines', line=limit_style, 
            name='+2 Std Dev Limit', hoverinfo='skip', showlegend=False
        ))
        
        # Draw the Lower Limit line
        fig.add_trace(go.Scatter(
            x=x_line, y=y_lower, mode='lines', line=limit_style, 
            name='-2 Std Dev Limit', hoverinfo='skip', showlegend=False
        ))
        
        # Draw Center Line (if the config says so)
        if show_center:
            fig.add_trace(go.Scatter(
                x=x_line, y=y_center, mode='lines', line=center_style, 
                name='Baseline Trend', hoverinfo='skip', showlegend=False
            ))

    # --- 3. Apply Layout ---
    # Apply standard UI formatting (grids, margins, titles)
    layout_args = {
        'title': title,
        'xaxis_title': x_col,
        'yaxis_title': y_col,
        'uirevision': 'constant', # Keeps the graph zoomed in when data updates, preventing jarring resets
        'margin': dict(l=40, r=40, t=60, b=40),
        'clickmode': 'event+select',
        'showlegend': False,
        'xaxis': {
            'showgrid': True, 'gridcolor': 'rgba(200,200,200,0.25)', 'gridwidth': 1,
            'zeroline': False, 'showline': True, 'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside', 'ticklen': 5
        },
        'yaxis': {
            'showgrid': True, 'gridcolor': 'rgba(200,200,200,0.25)', 'gridwidth': 1,
            'zeroline': False, 'showline': True, 'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside', 'ticklen': 5
        }
    }

    # Apply manual zoom ranges if provided in config
    if 'x_range' in graph_cfg: layout_args['xaxis_range'] = graph_cfg['x_range']
    if 'y_range' in graph_cfg: layout_args['yaxis_range'] = graph_cfg['y_range']

    fig.update_layout(**layout_args)
    return fig


# ==============================================================================
# STEP 4: LAYOUT ASSEMBLY
# ==============================================================================

app = dash.Dash(__name__)

# CSS Styles for our graph containers. 
# We use CSS Grid. "span 1" means take up one column block.
DEFAULT_WRAPPER_STYLE = {
    'gridColumn': 'span 1', 'backgroundColor': '#f9f9f9', 'border': '1px solid #ddd',
    'borderRadius': '8px', 'padding': '10px', 'transition': 'all 0.3s ease',
    'height': '350px', 'position': 'relative', 'minWidth': '0', 'boxSizing': 'border-box'
}
# When maximized, we change the style to "span 3" (take up the whole row) and increase height.
MAX_WRAPPER_STYLE = {**DEFAULT_WRAPPER_STYLE, 'gridColumn': 'span 3', 'height': '90vh', 'zIndex': 1000}

# Extract all the unique graph IDs from the config file
graph_ids = [g['id'] for g in config['graphs']]

# Loop through the config and build the HTML/Dash components for each graph dynamically
graph_wrappers = []
for g in config['graphs']:
    
    # We use dictionaries for IDs: id={'type': 'some-type', 'index': unique_id}
    # This is called "Pattern-Matching Callbacks". It allows a single callback
    # function to handle ALL buttons or ALL graphs at once, rather than writing
    # 5 different callbacks for 5 different graphs.
    wrapper = html.Div(
        id={'type': 'graph-wrapper', 'index': g['id']}, 
        style=DEFAULT_WRAPPER_STYLE.copy(),
        children=[
            # dcc.Store is invisible memory in the browser. 
            # We use this to remember if THIS specific graph is currently maximized (True/False).
            dcc.Store(id={'type': 'max-state', 'index': g['id']}, data=False),
            html.Div(
                html.Button("⛶ Maximize", id={'type': 'max-btn', 'index': g['id']}),
                style={'textAlign': 'right', 'marginBottom': '-10px', 'position': 'relative', 'zIndex': 10}
            ),
            # The actual graph component
            dcc.Graph(
                id={'type': 'dynamic-graph', 'index': g['id']},
                figure=create_figure(g), 
                config={
                    'displaylogo': False, # Hide the plotly logo
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d'] # Remove distracting tools
                },
                style={'height': '100%', 'width': '100%'}
            )
        ]
    )
    graph_wrappers.append(wrapper)

# --- Define AG Grid Columns ---
column_defs = []
for col in df.columns:
    if col in ['id', 'Category']: continue # Hide backend columns from the user interface
    
    col_def = {'field': col, 'sortable': True, 'filter': True}
    
    # Special rules for the Sample_Name column: freeze it to the left side
    if col == 'Sample_Name':
        col_def.update({
            'pinned': 'left', 'lockPinned': True, 'lockPosition': True,
            'suppressMovable': True, 'floatingFilter': True, 'filter': 'agTextColumnFilter'
        })
    # Apply rules from config for other columns
    elif col in config['table_config']['locked_pinned_columns']:
        col_def.update({'pinned': 'left', 'lockPinned': True})
    elif col in config['table_config']['default_pinned_columns']:
        col_def['pinned'] = 'left'
    column_defs.append(col_def)

# Ensure Sample_Name is strictly the first column in the array
sample_name_col = next((c for c in column_defs if c['field'] == 'Sample_Name'), None)
if sample_name_col:
    column_defs = [sample_name_col] + [c for c in column_defs if c['field'] != 'Sample_Name']

# Assemble the final visual layout of the page
app.layout = html.Div([
    html.H2("Data Correlation Dashboard"),
    html.Div([
        html.Button("Reset View", id='reset-view-btn', n_clicks=0, style={'marginRight': '10px'}),
        html.Button("Deselect", id='deselect-btn', n_clicks=0)
    ], style={'marginBottom': '20px'}),
    
    # A single, global invisible memory store that holds the ID of whatever data point is currently selected.
    dcc.Store(id='selected-data-store', data=[]),
    
    # Insert the graph wrappers we generated above into a CSS Grid (3 columns wide)
    html.Div(graph_wrappers, style={'display': 'grid', 'gridTemplateColumns': 'repeat(3, minmax(0, 1fr))', 'gap': '15px', 'marginBottom': '30px'}),
    
    # Insert the AG Grid
    dag.AgGrid(
        id='data-table', rowData=df.to_dict('records'), columnDefs=column_defs, 
        getRowId="params.data.id", # Crucial: tells AG grid which column acts as the unique ID
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={"rowSelection": {"mode": "singleRow"}, "animateRows": True},
        style={"height": "400px", "width": "100%"}
    )
], style={'padding': '20px'})


# ==============================================================================
# STEP 5: CALLBACKS
# ==============================================================================

# Callback 1: Toggle the Maximize State Store
@app.callback(
    # ALL means this callback outputs to every single max-state store on the page
    Output({'type': 'max-state', 'index': ALL}, 'data'), 
    # ALL means if ANY of the max buttons are clicked, this callback runs
    Input({'type': 'max-btn', 'index': ALL}, 'n_clicks'), 
    Input('reset-view-btn', 'n_clicks'),
    # State pulls in data without triggering the callback itself
    State({'type': 'max-state', 'index': ALL}, 'data'),
    prevent_initial_call=True
)
def update_max_states(max_btn_clicks, reset_clicks, current_states):
    # callback_context (ctx) is how we know WHICH of the inputs actually fired the callback.
    ctx = callback_context
    if not ctx.triggered: return dash.no_update
    
    # Get the ID of the component that triggered the callback
    trigger = ctx.triggered[0]['prop_id']
    
    # If the user clicked the global "Reset View" button, turn all max-states to False
    if 'reset-view-btn' in trigger:
        return [False] * len(graph_ids)
        
    if not current_states:
        current_states = [False] * len(graph_ids)
        
    try:
        # The trigger for pattern-matching IDs is a JSON string. We must parse it back to a dict.
        # Example trigger string: '{"index":"graph1","type":"max-btn"}.n_clicks'
        triggered_id = json.loads(trigger.split('.')[0])
        clicked_idx = triggered_id['index']
    except Exception:
        return [False] * len(graph_ids)
        
    # Return a new list of booleans: Flip the state of the one that was clicked, keep others False.
    return [not state if idx == clicked_idx else False for idx, state in zip(graph_ids, current_states)]

# Callback 2: Apply the CSS based on Maximize State
@app.callback(
    Output({'type': 'graph-wrapper', 'index': ALL}, 'style'),
    Output({'type': 'max-btn', 'index': ALL}, 'children'),
    Input({'type': 'max-state', 'index': ALL}, 'data'),
)
def apply_maximize_state(max_states):
    # Whenever the invisible max-state stores change, this runs to actually update the CSS
    styles = []
    labels = []
    for state in max_states:
        if state:
            style = MAX_WRAPPER_STYLE.copy()
            style['gridColumn'] = '1 / -1' # Force it to take up the entire row width
            style['width'] = '100%'
            styles.append(style)
            labels.append("🗕 Minimize")
        else:
            styles.append(DEFAULT_WRAPPER_STYLE.copy())
            labels.append("⛶ Maximize")
    return styles, labels


# Callback 3: If a graph is clicked, update the AG Grid selection
@app.callback(
    Output('data-table', 'selectedRows'),
    Output('data-table', 'scrollTo'),
    # ALL means any graph click will trigger this
    Input({'type': 'dynamic-graph', 'index': ALL}, 'clickData'), 
    Input('deselect-btn', 'n_clicks'),
    prevent_initial_call=True
)
def handle_graph_click(click_data_list, deselect_clicks):
    ctx = callback_context
    if not ctx.triggered: return dash.no_update, dash.no_update
    
    trigger = ctx.triggered[0]['prop_id']
    
    if 'deselect-btn' in trigger:
        return [], dash.no_update
        
    if click_data_list:
        # Loop through the graphs to find the one that actually sent click data
        for click_data in click_data_list:
            if click_data and 'points' in click_data:
                # Dig into the JSON payload of the click. 
                # Remember that customdata array we made? Index 0 is the row ID.
                clicked_id = str(click_data['points'][0]['customdata'][0])
                
                # Fetch that entire row from the dataframe
                selected_row = df[df['id'] == clicked_id].to_dict('records')
                
                # Tell the table to select that row, AND scroll down to it so the user sees it.
                return selected_row, {'rowId': clicked_id}
                
    return dash.no_update, dash.no_update


# Callback 4: The "Source of Truth" Store Updater
# We use a central Store to track selection so that graphs and tables don't get 
# stuck in an infinite feedback loop trying to update each other.
@app.callback(
    Output('selected-data-store', 'data'),
    Input({'type': 'dynamic-graph', 'index': ALL}, 'clickData'),
    Input('data-table', 'selectedRows'),
    Input('deselect-btn', 'n_clicks'),
    prevent_initial_call=True
)
def update_store(click_data_list, selected_rows, deselect_clicks):
    ctx = callback_context
    if not ctx.triggered: return dash.no_update
    
    trigger = ctx.triggered[0]['prop_id']
    
    # If deselect button clicked, empty the store
    if 'deselect-btn' in trigger: return []
    
    # If the user selected a row in the TABLE, put that ID in the store
    if '.selectedRows' in trigger:
        if not selected_rows: return []
        return [str(selected_rows[0]['id'])]
        
    # If the user clicked a point on a GRAPH, put that ID in the store
    if '.clickData' in trigger:
        for click_data in click_data_list:
            if click_data and 'points' in click_data:
                return [str(click_data['points'][0]['customdata'][0])]
        return []
        
    return []

# Callback 5: If the central store updates, filter the table data.
@app.callback(
    Output('data-table', 'rowData'),
    Input('selected-data-store', 'data'),
    prevent_initial_call=True
)
def update_table_from_store(selected_ids):
    # If something is selected, show only that row. Otherwise, show all rows.
    filtered_df = df[df['id'].isin(selected_ids)] if selected_ids else df
    return filtered_df.to_dict('records')

# Callback 6: Update Graph opacities (highlighting) based on selection or table filtering
@app.callback(
    Output({'type': 'dynamic-graph', 'index': ALL}, 'figure'),
    Input('selected-data-store', 'data'),
    # virtualRowData tracks what rows are currently visible in the AG Grid 
    # (e.g., if the user typed "Item_3" into the grid's filter bar).
    Input('data-table', 'virtualRowData'), 
)
def sync_graphs_to_table(selected_ids, virtual_rows):
    # Rule 1: Explicit selection (clicking a point or selecting a row) trumps all.
    if selected_ids:
        active_ids = selected_ids
    # Rule 2: If there's no selection, look at what the user has filtered in the table.
    elif virtual_rows is not None:
        # If the table isn't filtered (all rows visible), active_ids is None (all points bright)
        # If the table IS filtered, extract the IDs of just the visible rows.
        active_ids = None if len(virtual_rows) == len(df) else [str(row['id']) for row in virtual_rows]
    else:
        active_ids = None
        
    # Recreate all the figures, passing in the active_ids so the create_figure 
    # function knows which points to make opaque and which to dim.
    return [create_figure(g, active_ids) for g in config['graphs']]

if __name__ == '__main__':
    app.run(debug=True)