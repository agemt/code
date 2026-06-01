import json
from pathlib import Path
import numpy as np
import pandas as pd

import dash
from dash import Dash, dcc, html, Input, Output, State, ALL
# pyrefly: ignore [missing-import]
import dash_ag_grid as dag
import plotly.graph_objects as go

# Import the baseline calculation strategies registry
from baselines import BASELINE_STRATEGIES

# Define path to the configuration file
CONFIG_PATH = Path(__file__).with_name('config.json')


def load_config(path: Path) -> dict:
    """Loads configuration options from the local JSON config file."""
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def hex_to_rgba(hex_color: str, alpha: float = 0.1) -> str:
    """
    Converts a hexadecimal color code (e.g. '#636EFA') to an RGBA string with custom transparency.
    Returns transparent gray if the input is invalid.
    """
    if not isinstance(hex_color, str) or not hex_color.startswith('#'):
        return f'rgba(150, 150, 150, {alpha})'
    try:
        h = hex_color.lstrip('#')
        # Handle short hex format like #FFF
        if len(h) == 3:
            h = ''.join([char * 2 for char in h])
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    except Exception:
        return f'rgba(150, 150, 150, {alpha})'


def load_data(config: dict) -> pd.DataFrame:
    """
    Loads raw excel data, ensures 'id' and 'Category' fields exist,
    and rounds all numeric data to 3 decimal places.
    """
    source = config.get('data_source', {})
    file_path = source.get('file_path')
    if not file_path:
        raise ValueError("config.json must include data_source.file_path")
        
    path = Path(file_path)
    # Handle relative file path relative to this Python script
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
        
    df = pd.read_excel(path, sheet_name=source.get('sheet_name', 0))
    df = df.copy()
    
    # Ensure primary key ID exists
    if 'id' not in df.columns:
        df['id'] = df.index.astype(str)
        
    # Ensure category styling column exists
    if 'Category' not in df.columns:
        recent_rows = config.get('table_config', {}).get('recent_row_count', 10)
        df['Category'] = create_default_categories(len(df), recent_rows)
        
    # Round all numbers for visual presentation
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].round(3)
    
    return df


def create_default_categories(n: int, recent_rows: int) -> list[str]:
    """Assigns default categories to data points based on their table row index."""
    categories = []
    for index in range(n):
        if index == 0:
            categories.append('First')
        elif index < recent_rows:
            categories.append('Recent')
        elif index >= n - 10:
            categories.append('Baseline')
        else:
            categories.append('Regular')
    return categories


def build_column_defs(df: pd.DataFrame, table_config: dict) -> list[dict]:
    """
    Creates the column configuration (definitions) for Ag-Grid.
    Pins specific columns to the left and configures text filtering for the ID column.
    """
    locked_cols = table_config.get('locked_pinned_columns', [])
    pinned_cols = table_config.get('default_pinned_columns', [])
    
    column_definitions = []
    for col in df.columns:
        # Skip internal identifier and category styling columns
        if col in {'id', 'Category'}:
            continue
            
        col_def = {'field': col, 'sortable': True, 'filter': True}
        
        # Configure locked vs pin status
        if col in locked_cols:
            col_def.update({
                'pinned': 'left', 
                'lockPinned': True, 
                'lockPosition': True, 
                'suppressMovable': True
            })
        elif col in pinned_cols:
            col_def['pinned'] = 'left'
            
        column_definitions.append(col_def)
        
    # Reorder columns so that pinned/locked columns appear first on the left
    all_pinned_names = locked_cols + pinned_cols
    existing_fields = {c['field'] for c in column_definitions}
    ordered_pinned_fields = [f for f in all_pinned_names if f in existing_fields]
    
    pinned_defs = [c for c in column_definitions if c['field'] in ordered_pinned_fields]
    unpinned_defs = [c for c in column_definitions if c['field'] not in ordered_pinned_fields]
    sorted_columns = pinned_defs + unpinned_defs
    
    # Configure floating text search filter on the primary identifier column
    id_col_name = table_config.get('id_column')
    if not id_col_name:
        if ordered_pinned_fields:
            id_col_name = ordered_pinned_fields[0]
        elif sorted_columns:
            id_col_name = sorted_columns[0]['field']
            
    if id_col_name:
        for col_def in sorted_columns:
            if col_def['field'] == id_col_name:
                col_def.update({
                    'floatingFilter': True, 
                    'filter': 'agTextColumnFilter'
                })
                break
                
    return sorted_columns


def build_graph_figure(df: pd.DataFrame, graph_config: dict, full_config: dict, active_ids: list[str] | None = None) -> go.Figure:
    """
    Generates a Plotly scatter plot figure with optional linear baseline regressions
    and active row highlighting/dimming.
    """
    x_col = graph_config['x']
    y_col = graph_config['y']
    title = graph_config.get('title', f'{y_col} vs {x_col}')
    hover_col = full_config.get('hover_data', y_col)
    
    fig = go.Figure()
    
    # 1. Plot Baseline Trendlines & Bounds (drawn first so they sit behind data points)
    baseline_mode = graph_config.get('baseline_mode', 'default_linear')
    if baseline_mode in BASELINE_STRATEGIES:
        kwargs = graph_config.get('baseline_kwargs', {})
        baseline_data = BASELINE_STRATEGIES[baseline_mode](df, x_col, y_col, **kwargs)
        
        if baseline_data is not None:
            # Load default limit styling from config
            base_config = full_config.get('baseline_config', {})
            limit_style_default = base_config.get('limit_style', {'color': 'red', 'dash': 'dot', 'width': 2})
            center_style_default = base_config.get('center_style', {'color': 'gray', 'dash': 'dash', 'width': 1})
            
            show_bounds_fill = base_config.get('show_bounds_fill', True)
            show_limit_lines = base_config.get('show_limit_lines', True)
            show_center_line = base_config.get('show_center_line', True)
            
            # Support both single baseline results and lists of grouped results
            baselines_list = [baseline_data] if isinstance(baseline_data, dict) else baseline_data
            
            for b_data in baselines_list:
                group_name = b_data.get('group')
                group_color = None
                
                # Check for custom style overrides for this baseline group
                if group_name and 'category_styles' in full_config:
                    group_style = full_config['category_styles'].get(group_name)
                    if group_style and 'color' in group_style:
                        group_color = group_style['color']
                
                # Apply custom colors to line styles
                limit_style = limit_style_default.copy()
                center_style = center_style_default.copy()
                if group_color:
                    center_style['color'] = group_color
                    limit_style['color'] = group_color
                
                fill_color = hex_to_rgba(group_color, 0.1) if group_color else 'rgba(150, 150, 150, 0.1)'
                trace_name = f"{group_name} ±2σ" if group_name else "±2σ Bound"
                trend_name = f"{group_name} Trend" if group_name else "Baseline"
                
                # Draw bounds shading & boundary lines
                if show_limit_lines or show_bounds_fill:
                    lower_upper_line = limit_style if show_limit_lines else {'width': 0}
                    lower_upper_mode = 'lines' if show_limit_lines else 'none'
                    
                    # Lower Bound
                    fig.add_trace(go.Scatter(
                        x=b_data['x'], y=b_data['y_lower'],
                        mode=lower_upper_mode, line=lower_upper_line, showlegend=False, hoverinfo='skip'
                    ))
                    # Upper Bound
                    upper_kwargs = {
                        'x': b_data['x'],
                        'y': b_data['y_upper'],
                        'mode': lower_upper_mode,
                        'line': lower_upper_line,
                        'showlegend': False,
                        'hoverinfo': 'skip',
                        'name': trace_name
                    }
                    if show_bounds_fill:
                        upper_kwargs.update({
                            'fill': 'tonexty',
                            'fillcolor': fill_color
                        })
                    fig.add_trace(go.Scatter(**upper_kwargs))
                
                # Draw Center Trendline
                if show_center_line:
                    fig.add_trace(go.Scatter(
                        x=b_data['x'], y=b_data['y_trend'],
                        mode='lines', line=center_style,
                        name=trend_name, showlegend=False, hoverinfo='skip'
                    ))

    # 2. Draw Scatter Points grouped by Category
    default_style = {'color': 'gray', 'symbol': 'circle', 'size': 8}
    for category, group in df.groupby('Category', sort=False):
        style = full_config.get('category_styles', {}).get(category, default_style)
        ids = group['id'].astype(str)
        selected_points = None
        
        # If the user has filtered rows in Ag-Grid, highlight only the active items
        if active_ids is not None:
            selected_points = [i for i, item in enumerate(ids) if item in active_ids]
            
        hover_values = group[hover_col].astype(str) if hover_col in group else ids
        figure_data = np.stack((ids, hover_values), axis=-1)
        
        fig.add_trace(go.Scatter(
            x=group[x_col],
            y=group[y_col],
            mode='markers',
            name=category,
            customdata=figure_data,
            hovertemplate=(
                f'<b>{hover_col}</b>: %{{customdata[1]}}<br>'
                f'<b>{x_col}</b>: %{{x}}<br>'
                f'<b>{y_col}</b>: %{{y}}<extra></extra>'
            ),
            marker={
                'color': style['color'],
                'symbol': style['symbol'],
                'size': style['size'],
                'line': {'width': 1, 'color': 'white'}
            },
            selected={'marker': {'opacity': 1}},
            unselected={'marker': {'opacity': 0.2}},
            selectedpoints=selected_points
        ))
        
    # 3. Setup Layout options (margins, gridlines, axis ranges)
    layout = {
        'title': {
            'text': title,
            'yref': 'container',
            'y': 1,
            'yanchor': 'top',
            'pad': {'t': 15},
            'automargin': True
        },
        'xaxis_title': x_col,
        'yaxis_title': y_col,
        'uirevision': graph_config['id'],  # Prevents zoom reset during updates
        'dragmode': 'pan',
        'margin': {'l': 55, 'r': 20, 't': 75, 'b': 45},
        'showlegend': False,
        'plot_bgcolor': '#ffffff',
        'paper_bgcolor': '#ffffff',
        'xaxis': {
            'showgrid': True, 
            'gridcolor': 'rgba(225, 225, 225, 0.7)', 
            'zeroline': False, 
            'showline': True, 
            'linecolor': 'rgba(120,120,120,0.6)', 
            'ticks': 'outside'
        },
        'yaxis': {
            'showgrid': True, 
            'gridcolor': 'rgba(225, 225, 225, 0.7)', 
            'zeroline': False, 
            'showline': True, 
            'linecolor': 'rgba(120,120,120,0.6)', 
            'ticks': 'outside'
        }
    }
    
    if 'x_range' in graph_config:
        layout['xaxis_range'] = graph_config['x_range']
    if 'y_range' in graph_config:
        layout['yaxis_range'] = graph_config['y_range']
        
    fig.update_layout(**layout)
    return fig


def build_graph_cards(graphs: list[dict], df: pd.DataFrame, full_config: dict) -> list[html.Div]:
    """Creates a list of html card wrappers, each holding a maximize toggle and a Graph component."""
    cards = []
    for graph in graphs:
        cards.append(html.Div(
            id={'type': 'graph-wrapper', 'index': graph['id']},
            className='graph-card',
            children=[
                # Stores the maximized state (boolean) of the graph
                dcc.Store(id={'type': 'max-state', 'index': graph['id']}, data=False),
                
                # Header actions
                html.Div(
                    html.Button('⛶ Maximize', id={'type': 'max-btn', 'index': graph['id']}, className='btn-maximize'),
                    className='graph-card-header'
                ),
                
                # Graph component
                dcc.Graph(
                    id={'type': 'dynamic-graph', 'index': graph['id']},
                    figure=build_graph_figure(df, graph, full_config),
                    config={
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': graph.get('title', 'plot'),
                            'height': 1080,
                            'width': 1920,
                            'scale': 2
                        }
                    },
                    className='graph-element'
                )
            ]
        ))
    return cards


def build_layout() -> html.Div:
    """Builds the main dashboard page structure."""
    graph_cards = build_graph_cards(config['graphs'], df, config)
    
    return html.Div([
        # Header Area
        html.Div([
            html.H1('Data Correlation Dashboard'),
            html.P('Interactive data visualization and baseline correlation analysis')
        ], className='dashboard-header'),
        
        # Grid of Graphs
        html.Div(graph_cards, className='graph-grid'),
        
        # Data Table Area
        html.Div([
            html.H3('Data Records'),
            dag.AgGrid(
                id='data-table',
                rowData=df.to_dict('records'),
                columnDefs=column_defs,
                getRowId='params.data.id',
                defaultColDef={'resizable': True, 'sortable': True, 'filter': True},
                columnSize='autoSize',
                dashGridOptions={'animateRows': True, 'enableCellTextSelection': True, 'ensureDomOrder': True},
                style={'height': '400px', 'width': '100%'}
            )
        ], className='table-card')
    ], className='dashboard-container')


# --- INITIALIZATION ---
config = load_config(CONFIG_PATH)
df = load_data(config)
column_defs = build_column_defs(df, config.get('table_config', {}))

# Create the Dash Application
app = Dash(__name__)
app.layout = build_layout()

# List of graph IDs for lookup in callbacks
graph_ids = [graph['id'] for graph in config['graphs']]


# --- CALLBACKS ---

@app.callback(
    Output({'type': 'max-state', 'index': ALL}, 'data'),
    Input({'type': 'max-btn', 'index': ALL}, 'n_clicks'),
    State({'type': 'max-state', 'index': ALL}, 'data'),
    prevent_initial_call=True
)
def update_max_states(max_clicks: list[int], current_states: list[bool]) -> list[bool]:
    """
    Toggles the maximize/minimize state when a user clicks the maximize button.
    Ensures that only one graph is maximized at a time.
    """
    # dash.callback_context.triggered_id retrieves the ID of the exact component that fired this callback
    triggered_id = dash.callback_context.triggered_id
    if not triggered_id:
        raise dash.exceptions.PreventUpdate
        
    clicked_id = triggered_id.get('index')
    
    # Toggle the clicked graph's state and reset all other graphs to minimized (False)
    return [
        not state if idx == clicked_id else False 
        for idx, state in zip(graph_ids, current_states)
    ]


@app.callback(
    Output({'type': 'graph-wrapper', 'index': ALL}, 'className'),
    Output({'type': 'max-btn', 'index': ALL}, 'children'),
    Input({'type': 'max-state', 'index': ALL}, 'data')
)
def apply_maximize_state(max_states: list[bool]) -> tuple[list[str], list[str]]:
    """
    Applies the maximized/minimized layout styles by updating the CSS className
    of the graph containers and the labels of the buttons.
    """
    class_names = []
    btn_labels = []
    
    for is_maximized in max_states:
        if is_maximized:
            class_names.append('graph-card maximized')
            btn_labels.append('🗕 Minimize')
        else:
            class_names.append('graph-card')
            btn_labels.append('⛶ Maximize')
            
    return class_names, btn_labels


@app.callback(
    Output({'type': 'dynamic-graph', 'index': ALL}, 'figure'),
    Input('data-table', 'virtualRowData')
)
def sync_graphs(virtual_rows: list[dict] | None) -> list[go.Figure]:
    """
    Synchronizes the graphs with the Ag-Grid table filters.
    When rows are filtered, this callback triggers and highlights only the remaining rows.
    """
    global config
    try:
        # Re-load configuration to catch run-time changes dynamically
        config = load_config(CONFIG_PATH)
    except Exception:
        pass
        
    if virtual_rows is None:
        active_ids = None
    else:
        # If all rows are currently displayed, do not apply dimming
        active_ids = [str(row['id']) for row in virtual_rows] if len(virtual_rows) != len(df) else None
        
    # Rebuild all figures with the active selection/filter state
    return [build_graph_figure(df, graph, config, active_ids) for graph in config['graphs']]


if __name__ == '__main__':
    # Start the local development web server
    app.run(debug=True)