import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html

from functions import build_graph

# Register page and define path
dash.register_page(__name__, path="/export")


def layout():
    return html.Div(
        dmc.Grid(
            columns=12,
            gutter="sm",
            children=[
                dmc.GridCol(
                    [
                        dmc.Paper(
                            children=[
                                dcc.Store(id="local-custom-graph-store", storage_type="session"),
                                dcc.Store(
                                    id="local-export-graph-settings-store",
                                    storage_type="local",
                                    data={
                                        "captureheight": 1200,
                                        "capturewidth": 1600,
                                        "capturescale": 2,
                                        "export_graph_config": {
                                            "displaylogo": False,
                                            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                                            "toImageButtonOptions": {
                                                "format": "png",
                                                "filename": "custom_export_graph",
                                                "height": 1200,
                                                "width": 1600,
                                                "scale": 2,
                                            },
                                        },
                                    },
                                ),
                                dmc.TextInput(
                                    label="Title",
                                    id="custom-edit-title",
                                    placeholder="[Default title]",
                                    className="mb-3",
                                ),
                                dmc.Text("Export", fw=700, size="sm", className="mb-1"),
                                dmc.Group(
                                    children=[
                                        dmc.NumberInput(
                                            label="PNG Height",
                                            id="custom-export-capture-height",
                                            placeholder="1200",
                                            min=200,
                                            max=5000,
                                            step=100,
                                            allowDecimal=False,
                                            hideControls=False,
                                            value=1200,
                                            persistence=True,
                                            persistence_type="local",
                                            className="mb-2",
                                        ),
                                        dmc.NumberInput(
                                            label="PNG Width",
                                            id="custom-export-capture-width",
                                            placeholder="1600",
                                            min=200,
                                            max=5000,
                                            step=100,
                                            allowDecimal=False,
                                            hideControls=False,
                                            value=1600,
                                            persistence=True,
                                            persistence_type="local",
                                            className="mb-2",
                                        ),
                                        dmc.NumberInput(
                                            label="Scale",
                                            id="custom-export-capture-scale",
                                            placeholder="2",
                                            min=1,
                                            max=10,
                                            step=1,
                                            allowDecimal=False,
                                            hideControls=False,
                                            value=2,
                                            persistence=True,
                                            persistence_type="local",
                                            className="mb-2",
                                        ),
                                    ],
                                    grow=True,
                                ),
                                dmc.Text("Axes", fw=700, size="sm", className="mb-1 mt-1"),
                                dmc.Group(
                                    children=[
                                        dmc.Select(
                                            label="Horizontal Axis (X)",
                                            id="custom-edit-x-axis",
                                            searchable=True,
                                            placeholder="Select column...",
                                            className="mb-2",
                                            allowDeselect=False,
                                            maxDropdownHeight=400,
                                        ),
                                        dmc.NumberInput(
                                            id="custom-edit-x-min",
                                            placeholder="Min",
                                            label="X Range",
                                            hideControls=True,
                                            className="mb-2",
                                        ),
                                        dmc.NumberInput(
                                            id="custom-edit-x-max",
                                            placeholder="Max",
                                            label=" ",
                                            hideControls=True,
                                            className="mb-2",
                                        ),
                                    ],
                                    grow=True,
                                ),
                                dmc.Group(
                                    children=[
                                        dmc.MultiSelect(
                                            label="Vertical Axis (Y - multi)",
                                            id="custom-edit-y-axis",
                                            searchable=True,
                                            placeholder="Select one or more columns...",
                                            className="mb-2",
                                            clearSearchOnChange=False,
                                            hidePickedOptions=True,
                                            maxDropdownHeight=400,
                                        ),
                                        dmc.NumberInput(
                                            id="custom-edit-y-min",
                                            placeholder="Min",
                                            label="Y Range",
                                            hideControls=True,
                                            className="mb-2",
                                        ),
                                        dmc.NumberInput(
                                            id="custom-edit-y-max",
                                            placeholder="Max",
                                            hideControls=True,
                                            className="mb-2",
                                        ),
                                    ],
                                    grow=True,
                                ),
                                dmc.Text("Behavior", fw=700, size="sm", className="mb-1 mt-1"),
                                dmc.Group(
                                    children=[
                                        dmc.Select(
                                            label="Y-axis mode",
                                            id="custom-edit-axis-mode",
                                            searchable=False,
                                            allowDeselect=False,
                                            value="single_axis",
                                            data=[
                                                {"label": "Single axis (unlimited Y)", "value": "single_axis"},
                                                {"label": "Dual axis (max 2 Y)", "value": "dual_axis"},
                                            ],
                                            className="mb-2",
                                        ),
                                        dmc.Select(
                                            label="Trace mode",
                                            id="custom-edit-trace-mode",
                                            searchable=False,
                                            allowDeselect=False,
                                            value="markers",
                                            data=[
                                                {"label": "Markers", "value": "markers"},
                                                {"label": "Lines + Markers", "value": "lines+markers"},
                                            ],
                                            className="mb-2",
                                        ),
                                        dmc.Select(
                                            label="Filter mode",
                                            id="custom-edit-filter-mode",
                                            searchable=False,
                                            allowDeselect=False,
                                            className="mb-2",
                                        ),
                                    ],
                                    grow=True,
                                ),
                                dmc.Group(
                                    children=[
                                        dmc.Select(
                                            label="Baseline",
                                            id="custom-edit-baseline-data",
                                            searchable=False,
                                            allowDeselect=False,
                                            className="mb-2",
                                        ),
                                    ],
                                    grow=True,
                                ),
                                dmc.Text("Metadata", fw=700, size="sm", className="mb-1 mt-1"),
                                dmc.MultiSelect(
                                    label="Hover Data",
                                    id="custom-edit-hover-data",
                                    searchable=True,
                                    placeholder="Select columns...",
                                    clearSearchOnChange=False,
                                    hidePickedOptions=True,
                                    className="mb-3",
                                    maxDropdownHeight=400,
                                ),
                                dmc.Text("Actions", fw=700, size="sm", className="mb-1 mt-1"),
                                dbc.Button(
                                    "Save locally",
                                    id="save-local-custom-btn",
                                    color="primary",
                                    className="w-100 mt-2",
                                ),
                            ],
                            style={"height": "80vh"},
                            p="lg",
                            shadow="xl",
                            withBorder=True,
                        ),
                    ],
                    span=4,
                    style={"minWidth": 0},
                ),
                dmc.GridCol(
                    children=[
                        dmc.Paper(
                            children=[
                                dcc.Graph(
                                    id="custom-graph",
                                    figure={"data": [], "layout": {}},
                                    style={"height": "100%", "width": "100%"},
                                    config={
                                        "displaylogo": False,
                                        "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                                    },
                                ),
                            ],
                            style={"height": "80vh"},
                            p="lg",
                            shadow="xl",
                            withBorder=True,
                        ),
                    ],
                    span=8,
                    style={"minWidth": 0},
                ),
            ]
        )
    )


@callback(
    Output("custom-edit-x-axis", "data"),
    Output("custom-edit-y-axis", "data"),
    Output("custom-edit-hover-data", "data"),
    Output("custom-edit-filter-mode", "data"),
    Output("custom-edit-baseline-data", "data"),
    Input("session-dataframe", "data"),
    Input("session-config", "data"),
)
def populate_custom_editor(records, config):
    if not records or not config:
        return [], [], [], [], []

    df = pd.DataFrame(records)
    columns = df.columns.tolist()
    filter_options = [
        {"label": "Auto", "value": "Auto"},
        {"label": "Perf", "value": "Perf"},
        {"label": "Time", "value": "Time"},
        {"label": "Baseline", "value": "linear"},
    ]
    for col in columns:
        if col not in {"Auto", "Perf", "Time", "linear"}:
            filter_options.append({"label": col, "value": col})

    return (
        [{"label": col, "value": col} for col in columns],
        [{"label": col, "value": col} for col in columns],
        [{"label": col, "value": col} for col in columns],
        filter_options,
        [{"label": name, "value": name} for name in config.get("baseline_options", [])],
    )


@callback(
    Output("custom-edit-y-axis", "value"),
    Input("custom-edit-axis-mode", "value"),
    Input("custom-edit-y-axis", "value"),
    prevent_initial_call=True,
)
def enforce_y_axis_mode(axis_mode, y_cols):
    selected = y_cols or []
    if axis_mode == "dual_axis" and len(selected) > 2:
        return selected[:2]
    return dash.no_update


@callback(
    Output("local-export-graph-settings-store", "data"),
    Input("custom-export-capture-height", "value"),
    Input("custom-export-capture-width", "value"),
    Input("custom-export-capture-scale", "value"),
    State("local-export-graph-settings-store", "data"),
    prevent_initial_call=True,
)
def persist_export_graph_settings(capture_height, capture_width, capture_scale, current_settings):
    settings = current_settings or {
        "captureheight": 1200,
        "capturewidth": 1600,
        "capturescale": 2,
        "export_graph_config": {
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": "custom_export_graph",
                "height": 1200,
                "width": 1600,
                "scale": 2,
            },
        },
    }
    if capture_height is None or capture_width is None or capture_scale is None:
        return dash.no_update

    updated = {
        "captureheight": int(capture_height),
        "capturewidth": int(capture_width),
        "capturescale": int(capture_scale),
        "export_graph_config": {
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": "custom_export_graph",
                "height": int(capture_height),
                "width": int(capture_width),
                "scale": int(capture_scale),
            },
        },
    }
    if (
        settings.get("captureheight") == updated["captureheight"]
        and settings.get("capturewidth") == updated["capturewidth"]
        and settings.get("capturescale") == updated["capturescale"]
    ):
        return dash.no_update

    return updated


@callback(
    Output("custom-graph", "config"),
    Input("local-export-graph-settings-store", "data"),
    Input("custom-edit-title", "value"),
)
def apply_export_graph_config(export_settings, title):
    settings = export_settings or {}
    capture_height = int(settings.get("captureheight", 1200))
    capture_width = int(settings.get("capturewidth", 1600))
    capture_scale = int(settings.get("capturescale", 2))

    return {
        "displaylogo": False,
        "modeBarButtonsToRemove": ["select2d", "lasso2d"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": title or "custom_export_graph",
            "height": capture_height,
            "width": capture_width,
            "scale": capture_scale,
        },
    }


@callback(
    Output("custom-graph", "figure"),
    Output("local-custom-graph-store", "data"),
    Input("custom-edit-title", "value"),
    Input("custom-edit-x-axis", "value"),
    Input("custom-edit-y-axis", "value"),
    Input("custom-edit-x-min", "value"),
    Input("custom-edit-x-max", "value"),
    Input("custom-edit-y-min", "value"),
    Input("custom-edit-y-max", "value"),
    Input("custom-edit-hover-data", "value"),
    Input("custom-edit-filter-mode", "value"),
    Input("custom-edit-baseline-data", "value"),
    Input("custom-edit-axis-mode", "value"),
    Input("custom-edit-trace-mode", "value"),
    Input("custom-export-capture-height", "value"),
    Input("custom-export-capture-width", "value"),
    Input("custom-export-capture-scale", "value"),
    State("session-dataframe", "data"),
)
def update_custom_graph(title, x_col, y_cols, x_min, x_max, y_min, y_max, hover_data, filter_mode, baseline, axis_mode, trace_mode, capture_height, capture_width, capture_scale, records):
    export_capture_settings = {
        "captureheight": int(capture_height) if capture_height is not None else 1200,
        "capturewidth": int(capture_width) if capture_width is not None else 1600,
        "capturescale": int(capture_scale) if capture_scale is not None else 2,
    }

    selected_y_cols = y_cols or []
    if axis_mode == "dual_axis":
        selected_y_cols = selected_y_cols[:2]

    if not records or not x_col or not selected_y_cols:
        return {"data": [], "layout": {}}, None

    df = pd.DataFrame(records)
    display_y = ", ".join(selected_y_cols)
    multi_y_palette = [
        "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#17becf", "#bcbd22",
    ]
    y_color_map = {y_col: multi_y_palette[idx % len(multi_y_palette)] for idx, y_col in enumerate(selected_y_cols)}
    is_multi_y = len(selected_y_cols) > 1
    effective_filter = "Auto" if is_multi_y else (filter_mode or "Auto")

    config = {
        "title": title or f"{display_y} vs {x_col}",
        "x": x_col,
        "y": selected_y_cols,
        "y_axis_columns": selected_y_cols,
        "axis_mode": axis_mode or "single_axis",
        "dual_axis": (axis_mode == "dual_axis"),
        "trace_mode": trace_mode or "markers",
        "multi_y_colors": [y_color_map[y_col] for y_col in selected_y_cols],
        "y_color_map": y_color_map,
        **export_capture_settings,
        "export_graph_config": {
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": title or "custom_export_graph",
                "height": export_capture_settings["captureheight"],
                "width": export_capture_settings["capturewidth"],
                "scale": export_capture_settings["capturescale"],
            },
        },
        "hover_data": hover_data or [],
        "filter": effective_filter,
        "baseline": baseline or "ignore",
        "x_range": [x_min, x_max] if x_min is not None and x_max is not None else None,
        "y_range": [y_min, y_max] if y_min is not None and y_max is not None else None,
    }
    fig = build_graph(config, df)

    return fig, config


@callback(
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Input("save-local-custom-btn", "n_clicks"),
    State("local-custom-graph-store", "data"),
    prevent_initial_call=True,
)
def save_local_custom_graph(n_clicks, local_config):
    if not n_clicks or not local_config:
        return dash.no_update
    return [dict(
        title="Saved locally",
        action="show",
        message="Custom graph settings saved for this session.",
        color="green",
    )]