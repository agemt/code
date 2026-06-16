import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
import json
import os
import baseline
from dash import dcc

def get_data():
    print(f"---data lookup")
    config_path = r'c:\application\config\config.json'
    if not os.path.exists(config_path):
        return {}, pd.DataFrame()
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    data_source = config.get('data_source', {})
    dffile_path = data_source.get('file_path', r'c:\application\data\database.xlsx')
    dfsheet_name = data_source.get('sheet_name', 0)

    if not os.path.exists(dffile_path):
        return config, pd.DataFrame()

    df = pd.read_excel(dffile_path, sheet_name=dfsheet_name)
    df.rename(columns={config['date_col']: 'Full_date'}, inplace=True)
    df = df.sort_values(by='Full_date', ascending=True).reset_index(drop=True)
    df['sequential_id'] = range(1, len(df) + 1)
    df['Full_date'] = pd.to_datetime(df['Full_date'], errors='coerce')

    try:
        df.insert(2, config['date_col'], df["Full_date"].dt.strftime("%Y-%m-%d"))
        df.insert(3, 'Time', df["Full_date"].dt.strftime("%H:%M:%S"))
    except ValueError:
        pass

    df = df.sort_values(by='Full_date', ascending=False).reset_index(drop=True)
    return config, df


def build_graph(graph, dfa, activeIDs=None):
    #print(f"building graph")

    fig = go.Figure()
    x_col = graph['x']
    y_col = graph['y']
    title = graph.get('title', f"{y_col} vs {x_col}")
    hover_cols = graph.get('hover_data', [])
    clean_df = dfa.dropna(subset=[x_col, y_col])
    last_10_uniques = clean_df['Engine'].unique()[:10]
    b1 = clean_df[clean_df['Engine'].isin(last_10_uniques)].copy()

    ranges = {
        "Default": b1,
        "Baseline": b1,
        "Recent": dfa.iloc[1:11],
        "Last": dfa.iloc[:1]
    }

    excluded_indices = list(range(0, 11))
    excluded_indices.extend(b1.index.tolist())
    ranges["Default"] = dfa.drop(index=excluded_indices, errors="ignore")

    linecolor = {
        "Last": "rgb(0, 200, 0)",
        "Recent": "rgb(255, 200, 0)",
        "Default": "rgb(0, 0, 255)",
        "Baseline": "rgb(0, 0, 255)"
    }

    fillcolor = {
        "Last": "rgb(0, 200, 0)",
        "Recent": "rgb(255, 200, 0)",
        "Baseline": "rgb(255, 0, 255)",
        "Default": "rgba(0,0,0,0)"
    }
    
    size = {
        "Last": 10,
        "Recent": 8,
        "Baseline": 6,
        "Default": 6
    }
    
    ### CHANGE PERFORMANCE COLORS HERE
    perf_colors = {
        'B3_Take_Off': '#1f77b4',
        'B4_Take_Off': '#ff7f0e',
        'B6_Take_Off': '#008600',
        'A3_Take_Off': '#1f77b4',
        'B8_Take_Off': '#00ddff',
        'B9_Take_Off': '#ff0000',
        'B5_Take_Off': '#b9e200'
    }

    hovertemplate = (
        f"<b>{x_col}</b>: %{{x}}<br>"
        f"<b>{y_col}</b>: %{{y}}"
    )
    if hover_cols:
        for i, col in enumerate(hover_cols):
            hovertemplate += f"<br><b>{col}</b>: %{{customdata[{i}]}}"

    hovertemplate += "<extra></extra>"

    # graph parameters
    for label, subset in ranges.items():
        if subset is None or subset.empty:
            continue

        if hover_cols:
            # Only use columns that exist in this subset
            available_cols = [c for c in hover_cols if c in subset.columns]
            subset_customdata = subset[available_cols] if available_cols else None
        else:
            subset_customdata = None

        color_filter = graph.get("filter")

        if color_filter == "Perf":
            marker_colors = "rgba(0,0,0,0)"
            line_colors = subset['Perf. Point'].map(perf_colors).tolist()
            marker_size = 6
        else:
            marker_colors = fillcolor[label]
            line_colors = linecolor[label]
            marker_size = size[label]

        id_column = 'sequential_id'

        if activeIDs is None:
            opacity_values = 1.0
        else:
            string_active_ids = {str(i) for i in activeIDs}
            opacity_values = [
                1.0 if str(val) in string_active_ids else 0.1
                for val in subset[id_column]
            ]

        fig.add_trace(go.Scatter(
            name=label,
            x=subset[x_col],
            y=subset[y_col],
            mode='markers',
            customdata=subset_customdata,
            hovertemplate=hovertemplate,
            marker=dict(
                size=marker_size,
                line=dict(
                    width=1,
                    color=line_colors,
                ),
                color=marker_colors,
                opacity=opacity_values
            )
        ))

    # get pair of coordinates from baseline
    baseline_function = getattr(baseline, graph['baseline'])
    lineset = baseline_function(dfa, b1, graph, graph['id'], x_col, y_col)

    if lineset is not None:
        for row in lineset:
            x1, x2, y1, y2, lineid = row
            if lineid == 0:
                # center line
                linestyle = dict(color="rgb(255, 0, 0)", width=1, dash="dash")
            else:
                # border lines
                linestyle = dict(color="rgb(0, 13, 255)", width=1, dash="dot")

            # line parameters
            fig.add_shape(
                type='line',
                x0=x1,
                y0=y1,
                x1=x2,
                y1=y2,
                xref="x", yref="y",
                layer="below",
                line=linestyle
            )

    layout_args = {
        'title': dict(text=title, font=dict(size=22)),
        'xaxis_title': x_col,
        'yaxis_title': y_col,
        'clickmode': None,
        'hovermode': 'closest',
        'showlegend': False,
        'margin': dict(l=5, r=5, t=50, b=10),
        'paper_bgcolor': 'rgb(255, 255, 255)',
        'plot_bgcolor': 'rgb(205, 212, 221)',
        'xaxis': {
            'showgrid': True,
            'gridcolor': 'rgba(200,200,200,0.25)',
            'gridwidth': 1,
            'zeroline': False,
            'showline': True,
            'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside',
            'ticklen': 5,
            'nticks': 20
        },
        'yaxis': {
            'showgrid': True,
            'gridcolor': 'rgba(200,200,200,0.25)',
            'gridwidth': 1,
            'zeroline': False,
            'showline': True,
            'linecolor': 'rgba(120,120,120,0.6)',
            'ticks': 'outside',
            'ticklen': 5,
            'nticks': 20
        }
    }

    if 'x_range' in graph:
        layout_args['xaxis_range'] = graph['x_range']
    if 'y_range' in graph:
        layout_args['yaxis_range'] = graph['y_range']

    fig.update_layout(**layout_args)
    return fig


def build_card(graphs, width, height, dfa, activeIDs=None):
    #print(f"start building cards")
    cards = []
    for graph in graphs:
        try:
            cards.append(dbc.Col(
                dcc.Loading(
                    dcc.Graph(
                        id={'type': 'graphcard', 'index': graph['id']},
                        figure=build_graph(graph, dfa, activeIDs=activeIDs),
                        style={"height": height, "width": "100%"},
                        config={
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                            'modeBarButtonsToAdd': [
                                'drawline',
                                'drawopenpath',
                                'drawclosedpath',
                                'drawcircle',
                                'drawrect',
                                'eraseshape'
                            ],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': graph.get('title', f"{graph.get('y')} vs {graph.get('x')}"),
                                'height': 720,
                                'width': 1280,
                                'scale': 3
                            }
                        },
                        className='graph-element'
                    ),
                    id="loading",
                    type="default",
                ),
                width=int(width),
                id={'type': 'col_container', 'index': graph['id']},
                style={"height": height, "display": "flex", "flexDirection": "column"},
                class_name="mb-3"
            ))
            #print(f"card {graph['id']} completed")
        except KeyError as e:
            cards.insert(0,
                dbc.Alert(
                    f"Could not find parameter {e}",
                    is_open=True,
                    dismissable=True,
                    color="warning",
                    duration=5000
                ),
            )
            #print(e)
    return cards

#print(len(dataframe['sequential_id']))

def build_grid(config, df):
    #print(f"building grid")
    columnDefs = []
    for i in df.columns:
        if i == "Added_by":
            continue
        elif i in config.get('locked_col', []):
            columnDefs.append({"field": i, "floatingFilter": True, "pinned": "left", "lockPinned": True, "lockPosition": True, "suppressMovable": True, })
            #print([i])
        elif i in config.get('pinned_col', []):
            columnDefs.append({"field": i, "pinned": True, })
        elif i == "Full_date":
            continue
        elif i == "sequential_id":
            continue
        else:
            columnDefs.append({"field": i})

    default_colDef = {
        "filter": True
    }

    grid = dag.AgGrid(
        id="data-grid",
        rowData=df.to_dict("records"),
        columnDefs=columnDefs,
        dangerously_allow_code=True,
        dashGridOptions={
            "suppressFieldDotNotation": True,
            "suppressColumnVirtualisation": True,
            "animateRows": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "dataTypeDefinitions": {
                "number": {
                    "baseDataType": "number",
                    "extendsDataType": "number",
                    "valueFormatter": {"function": "d3.format('.3f')(params.value)"}
                }
            },
            "theme": {
                "function": "themeQuartz.withParams({ spacing: 2, fontSize: 12 })",
            },
        },
        defaultColDef=default_colDef,
        columnSize="autoSize",
        style={"height": "100%"},
        persistence=True,
        persisted_props=["filterModel"],
        className="ag-theme-alpine"
    )
    return grid
