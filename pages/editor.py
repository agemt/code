import json
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ALL
import dash_mantine_components as dmc

dash.register_page(__name__, path="/editor")

# Define editor layout
def layout():
    return html.Div(
        style={
            "height": "85vh",
            "overflow": "hidden",
            "paddingRight": "5px",
            "marginTop": "20px",
        },
        children=[
            html.H3("Graph configuration", className="mb-4"),
            dbc.Alert(id="editor-status-alert", is_open=False, duration=2000, className="mb-3"),
            
            # Track strings that are not in the Excel columns list
            dbc.Row(
                [
                ],
                className="p-2 border rounded bg-light",
            ),
            dbc.Row(
                [
                    # LEFT COLUMN
                    dbc.Col(
                        [
                            html.H5("Configured System Graphs"),
                            html.Hr(),
                            
                            html.Div(
                                dbc.ListGroup(id="editor-graph-list-group", numbered=True, flush=True),
                                style={
                                    "maxHeight": "60vh",
                                    "overflowY": "scroll",
                                    "border": "1px solid rgba(0,0,0,0.125)",
                                    "borderRadius": "0.25rem",
                                    "backgroundColor": "#ffffff"
                                },
                                className="mb-3"
                            ),
                            #dbc.Row([
                            #dbc.Col(dbc.Button("Add New Graph", id="add-blank-graph-btn", color="success", size="sm", className="w-100 mt-2")),
                            #dbc.Col(dbc.Button("Delete Graph", id="delete-graph-btn", color="danger", size="sm", className="w-100 mt-2")),
                            #]),
                            dmc.Group(
                                children=[
                                    dbc.Button("Add New Graph", id="add-blank-graph-btn", color="success", size="sm", className="w-100 mt-2"),
                                    dbc.Button("Delete Graph", id="delete-graph-btn", color="danger", size="sm", className="w-100 mt-2"),
                                ],
                                grow=True
                            ),
                        ],
                        md=5,
                        className="p-4 border rounded bg-light mb-3",
                        style={"height": "fit-content"}
                    ),
                    
                    # RIGHT COLUMN
                    dbc.Col(
                        [
                            html.Hr(),
                            html.H5("Graph Configuration Properties", id="form-panel-header"),
                            html.Hr(),
                            
                            dash.dcc.Store(id="active-edit-index-store", storage_type="local"),
                            
                            html.Div(
                                id="editor-form-fields-container",
                                style={"display": "flex", "flexDirection": "column", "flex": "1", "minHeight": 0},
                                children=[
                                    html.Div(
                                        style={"overflowY": "auto", "flex": "1", "minHeight": 0, "paddingRight": "6px"},
                                        children=[
                                            dmc.Text("Identity", fw=700, size="sm", className="mb-1"),
                                            dmc.TextInput(label="Title", id="edit-title", placeholder="[Default title]", className="mb-3"),

                                            dmc.Text("Axes", fw=700, size="sm", className="mb-1 mt-1"),
                                            dmc.Group(
                                                children=[
                                                    dmc.Select(
                                                        label="Horizontal Axis (X)",
                                                        id="edit-x-axis",
                                                        searchable=True,
                                                        placeholder="Select column...",
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                        maxDropdownHeight=400,
                                                    ),
                                                    dmc.NumberInput(
                                                        id="edit-x-min",
                                                        placeholder="Min",
                                                        label="X Range",
                                                        hideControls=True,
                                                        className="mb-2",
                                                    ),
                                                    dmc.NumberInput(
                                                        id="edit-x-max",
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
                                                        id="edit-y-axis",
                                                        searchable=True,
                                                        placeholder="Select one or more columns...",
                                                        className="mb-2",
                                                        clearSearchOnChange=False,
                                                        hidePickedOptions=True,
                                                        maxDropdownHeight=400,
                                                    ),
                                                    dmc.NumberInput(
                                                        id="edit-y-min",
                                                        placeholder="Min",
                                                        label="Y Range",
                                                        hideControls=True,
                                                        className="mb-2",
                                                    ),
                                                    dmc.NumberInput(
                                                        id="edit-y-max",
                                                        placeholder="Max",
                                                        label=" ",
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
                                                        id="edit-axis-mode",
                                                        searchable=False,
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                        value="single_axis",
                                                        data=[
                                                            {"label": "Single axis (unlimited Y)", "value": "single_axis"},
                                                            {"label": "Dual axis (max 2 Y)", "value": "dual_axis"},
                                                        ],
                                                    ),
                                                    dmc.Select(
                                                        label="Trace mode",
                                                        id="edit-trace-mode",
                                                        searchable=False,
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                        value="markers",
                                                        data=[
                                                            {"label": "Markers", "value": "markers"},
                                                            {"label": "Lines + Markers", "value": "lines+markers"},
                                                        ],
                                                    ),
                                                    dmc.Select(
                                                        label="Filter mode",
                                                        id="edit-filter-mode",
                                                        searchable=False,
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                    ),
                                                ],
                                                grow=True,
                                            ),
                                            dmc.Group(
                                                children=[
                                                    dmc.Select(
                                                        label="Baseline",
                                                        id="edit-baseline-data",
                                                        searchable=False,
                                                        placeholder="",
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                        maxDropdownHeight=400,
                                                    ),
                                                    dmc.Select(
                                                        label="Target tab",
                                                        id="edit-target-tab",
                                                        searchable=False,
                                                        placeholder="",
                                                        className="mb-2",
                                                        allowDeselect=False,
                                                        maxDropdownHeight=400,
                                                    ),
                                                ],
                                                grow=True,
                                            ),

                                            dmc.Text("Metadata", fw=700, size="sm", className="mb-1 mt-1"),
                                            dmc.MultiSelect(
                                                label="Hover Data",
                                                id="edit-hover-data",
                                                searchable=True,
                                                placeholder="Select columns...",
                                                clearSearchOnChange=False,
                                                hidePickedOptions=True,
                                                className="mb-3",
                                                maxDropdownHeight=400,
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        style={"borderTop": "1px solid rgba(0,0,0,0.1)", "paddingTop": "10px", "marginTop": "8px"},
                                        children=[
                                            dmc.Text("Actions", fw=700, size="sm", className="mb-1"),
                                            dbc.Button("Apply locally", id="apply-edits-btn", size="sm", className="w-100", color="primary"),
                                            dmc.Group(
                                                children=[
                                                    dbc.Button("Save to File", id="save-disk-btn", size="sm", className="w-100", color="success"),
                                                    dbc.Button("Restore from File", id="restore-file-btn", size="sm", className="w-100", color="secondary"),
                                                ],
                                                grow=True,
                                                className="g-2 mt-2",
                                            ),
                                        ],
                                    ),
                                ]
                            )
                        ],
                        md={"size": 7},
                        className="p-4 border rounded bg-light mb-3",
                        style={"height": "78vh", "display": "flex", "flexDirection": "column"},
                    ),
                ]
            )
        ]
    )

######################################################### CALLBACKS #########################################################

#@callback(
#    Output("active-id-feedback", "children"),
#    Input("active-edit-index-store", "data")
#)
#def update_text(text):
#    return text

@callback(
    Output("session-config", "data", allow_duplicate=True),
    State("session-config", "data"),
    Input("edit-export-height", "value"),
    Input("edit-export-width", "value"),
    Input("edit-export-scale", "value"),
    prevent_initial_call=True,
)
def apply_export(config, exp_h, exp_w, exp_s):
    if config:
        config["captureheight"] = exp_h
        config["capturewidth"] = exp_w
        config["capturescale"] = exp_s
        return config
    return dash.no_update

# Populated dropdown
@callback(
    Output("editor-graph-list-group", "children"),
    Output("edit-x-axis", "data"),
    Output("edit-y-axis", "data"),
    Output("edit-hover-data", "data"),
    Output("edit-filter-mode", "data"),
    Output("edit-baseline-data", "data"),
    Output("edit-target-tab", "data"),
    Output("edit-export-height", "value"),
    Output("edit-export-width", "value"),
    Output("edit-export-scale", "value"),
    State("session-config", "data"),
    Input("session-dataframe", "data"),
    Input("active-edit-index-store", "data"),
    State("active-edit-index-store", "data"),
)
def render_graph_list_and_dropdowns(config, records, trigger, active_idx):
    if not config or not records:
        return [], [], [], [], [], [], [], None, None, None
    import pandas as pd

    df_cols = list(pd.DataFrame(records).columns)
    base_options = [{"label": col, "value": col} for col in df_cols]
    baseline_options = config.get("baseline_options")
    tab_options = [{"label": tab, "value": tab} for tab in config.get("graph_tabs", ["Tab 1", "Tab 2"])]
    filter_options = [
        {"label": "Auto", "value": "Auto"},
        {"label": "Perf", "value": "Perf"},
        {"label": "Time", "value": "Time"},
        {"label": "Baseline", "value": "linear"},
    ]
    for col in df_cols:
        if col not in {"Auto", "Perf", "Time", "linear"}:
            filter_options.append({"label": col, "value": col})

    list_items = []
    for g in config.get("graphs", []):
        g_id = g["id"]
        y_value = g.get("y")
        y_label = ", ".join(y_value) if isinstance(y_value, list) else y_value
        g_title = g.get("title", f"{y_label} vs {g.get('x')}")
        is_active = (active_idx == g_id)

        list_items.append(
            dbc.ListGroupItem(
                f"{g_title}",
                id={"type": "graph-list-item", "index": g_id},
                action=True,
                active=is_active,
                style={"cursor": "pointer"}
            )
        )

    return (
        list_items,
        base_options,
        base_options,
        base_options,
        filter_options,
        baseline_options,
        tab_options,
        config.get("captureheight"),
        config.get("capturewidth"),
        config.get("capturescale"),
    )


@callback(
    Output("edit-y-axis", "value", allow_duplicate=True),
    Input("edit-axis-mode", "value"),
    Input("edit-y-axis", "value"),
    prevent_initial_call=True,
)
def enforce_editor_y_axis_mode(axis_mode, y_cols):
    selected = y_cols or []
    if axis_mode == "dual_axis" and len(selected) > 2:
        return selected[:2]
    return dash.no_update

# Index selection
@callback(
    Output("active-edit-index-store", "data"),
    Input({"type": "graph-list-item", "index": dash.ALL}, "n_clicks"),
    Input("add-blank-graph-btn", "n_clicks"),
    State("session-config", "data"),
    State("active-edit-index-store", "data"),
    prevent_initial_call=True,
)
def update_active_selection(list_clicks, add_clicks, current_config, current_id):
    ctx = dash.callback_context
    if not ctx.triggered or not current_config:
        return current_id
        
    trigger_id = ctx.triggered[0]["prop_id"]
    if "add-blank-graph-btn" in trigger_id:
        return len(current_config.get("graphs", []))
        
    try:
        raw_split = trigger_id.split(".")
        json_string = raw_split[0]
        prop_dict = json.loads(json_string)
        return prop_dict["index"]
    except Exception:
        return current_id

# Reloads fresh configuration values from file
@callback(
    Output("session-config", "data", allow_duplicate=True),
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Input("restore-file-btn", "n_clicks"),
    running=[(Output("restore-file-btn", "loading"), True, False)],
    prevent_initial_call=True,
)
def restore_configuration_from_disk(n_clicks):
    if not n_clicks:
        return dash.no_update, []
    try:
        from functions import get_data
        config, _ = get_data() # type: ignore
        
        return config, [dict(title="Completed", action="show", autoClose=6000, message="Configuration restored from file", color="green")]
    except Exception as e:
        return dash.no_update, [dict(title="Error", action="show", autoClose=False, message="Failed to load configuration", color="red")]

# 4. Sync forms and selection
@callback(
    Output("edit-x-axis", "value"),
    Output("edit-y-axis", "value"),
    Output("edit-title", "value"),
    Output("form-panel-header", "children"),
    Output("edit-hover-data", "value"),
    Output("edit-filter-mode", "value"),
    Output("edit-baseline-data", "value"),
    Output("edit-target-tab", "value"),
    Output("edit-axis-mode", "value"),
    Output("edit-trace-mode", "value"),
    Output("edit-x-min", "value"),
    Output("edit-x-max", "value"),
    Output("edit-y-min", "value"),
    Output("edit-y-max", "value"),
    Input("active-edit-index-store", "data"),
    Input("session-config", "data"),
    State("edit-x-axis", "data"),
)
def sync_selection(active_idx, config, dropdown_options):
    if active_idx is None or not config or not dropdown_options:
        return None, None, "", "Select a Graph to Edit", None, "Auto", "ignore", "Tab 1", "single_axis", "markers", None, None, None, None

    graphs = config.get("graphs", [])
    known_values = [opt["value"] for opt in dropdown_options if opt["value"] != "__CUSTOM_VALUE__"]

    if active_idx >= len(graphs):
        return None, None, "", f"New Graph #{active_idx+1}", None, "Auto", "ignore", config.get("graph_tabs", ["Tab 1", "Tab 2"])[0], "single_axis", "markers", "", "", "", ""

    for g in graphs:
        if g.get("id") == active_idx:
            x_val = g.get("x")
            y_val = g.get("y")
            hover_data = g.get("hover_data")
            filter_mode = g.get("filter", "Auto")
            baseline_status = g.get("baseline", "ignore")
            target_tab = g.get("tab", config.get("graph_tabs", ["Tab 1", "Tab 2"])[0])
            axis_mode = g.get("axis_mode", "dual_axis" if g.get("dual_axis", False) else "single_axis")
            trace_mode = g.get("trace_mode", "markers")

            if g.get("x_range"):
                x_min = g.get("x_range")[0]
                x_max = g.get("x_range")[1]
            else:
                x_min = ""
                x_max = ""
            if g.get("y_range"):
                y_min = g.get("y_range")[0]
                y_max = g.get("y_range")[1]
            else:
                y_min = ""
                y_max = ""

            ui_x_dropdown = x_val if x_val in known_values else None
            if isinstance(y_val, list):
                ui_y_dropdown = [y for y in y_val if y in known_values]
            elif y_val in known_values:
                ui_y_dropdown = [y_val]
            else:
                ui_y_dropdown = []
            ui_hoverdata_dropdown = hover_data or []

            return (
                ui_x_dropdown,
                ui_y_dropdown,
                g.get("title", ""),
                f"Editing Graph #{active_idx + 1}",
                ui_hoverdata_dropdown,
                filter_mode,
                baseline_status,
                target_tab,
                axis_mode,
                trace_mode,
                x_min,
                x_max,
                y_min,
                y_max,
            )

    return None, None, "", "Select a Graph to Edit", None, "Auto", "ignore", config.get("graph_tabs", ["Tab 1", "Tab 2"])[0], "single_axis", "markers", None, None, None, None


#################################################################################################################
#################################################################################################################
#################################################################################################################

# 5. Main modification callback
# ADD NEW CONFIGURATION STATES

@callback(
    Output("session-config", "data", allow_duplicate=True),
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Output("active-edit-index-store", "data", allow_duplicate=True),
    Input("apply-edits-btn", "n_clicks"),
    Input("delete-graph-btn", "n_clicks"),
    State("active-edit-index-store", "data"),
    State("edit-x-axis", "value"),
    State("edit-y-axis", "value"),
    State("edit-title", "value"),
    State("session-config", "data"),
    State("edit-hover-data", "value"),
    State("edit-filter-mode", "value"),
    State("edit-x-min", "value"),
    State("edit-x-max", "value"),
    State("edit-y-min", "value"),
    State("edit-y-max", "value"),
    State("edit-baseline-data", "value"),
    State("edit-target-tab", "value"),
    State("edit-axis-mode", "value"),
    State("edit-trace-mode", "value"),
    prevent_initial_call=True,
)
def edit_configuration(
    apply_clicks,
    delete_clicks,
    active_idx,
    x_drop,
    y_drop,
    title,
    current_config,
    hover_data,
    filter_mode,
    x_min,
    x_max,
    y_min,
    y_max,
    baseline_data,
    target_tab,
    axis_mode,
    trace_mode,
):
    if active_idx is None or not current_config:
        return dash.no_update, [dict(title="Error", action="show", autoClose=False, message="No graph selected", color="orange")], active_idx

    ctx = dash.callback_context
    trigger_component = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
    updated_config = current_config.copy()
    graphs = updated_config.get("graphs", [])

    selected_y_cols = y_drop or []
    if not isinstance(selected_y_cols, list):
        selected_y_cols = [selected_y_cols] if selected_y_cols else []
    if axis_mode == "dual_axis":
        selected_y_cols = selected_y_cols[:2]

    if not x_drop or not selected_y_cols:
        return dash.no_update, [dict(title="Error", action="show", autoClose=False, message="X and at least one Y are required", color="orange")], active_idx

    is_multi_y = len(selected_y_cols) > 1
    effective_filter = "Auto" if is_multi_y else (filter_mode or "Auto")
    multi_y_palette = [
        "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#17becf", "#bcbd22",
    ]
    y_color_map = {y_col: multi_y_palette[idx % len(multi_y_palette)] for idx, y_col in enumerate(selected_y_cols)}

    if "delete-graph-btn" in trigger_component:
        if active_idx >= len(graphs):
            return dash.no_update, [dict(title="Error", action="show", autoClose=False, message="Cannot delete a blank graph", color="red")], active_idx

        graphs = [g for g in graphs if g.get("id") != active_idx]
        for i, g in enumerate(graphs):
            g["id"] = i

        updated_config["graphs"] = graphs
        return updated_config, [dict(title="Completed", action="show", message="Graph removed successfully", color="green")], active_idx

    if active_idx >= len(graphs):
        new_node = {
            "id": active_idx,
            **({"title": title} if title else {}),
            "x": str(x_drop),
            "y": selected_y_cols,
            "y_axis_columns": selected_y_cols,
            "axis_mode": axis_mode or "single_axis",
            "dual_axis": (axis_mode == "dual_axis"),
            "trace_mode": trace_mode or "markers",
            "hover_data": hover_data or [],
            **({"filter": effective_filter} if effective_filter and effective_filter != "Auto" else {}),
            **({"multi_y_colors": [y_color_map[y_col] for y_col in selected_y_cols], "y_color_map": y_color_map} if is_multi_y else {}),
            **({"x_range": [x_min, x_max]} if x_min is not None and x_max is not None else {}),
            **({"y_range": [y_min, y_max]} if y_min is not None and y_max is not None else {}),
            **({"baseline": baseline_data} if baseline_data else {"baseline": "ignore"}),
            **({"tab": target_tab} if target_tab else {}),
        }
        graphs.append(new_node)
        updated_config["graphs"] = graphs
        return updated_config, [dict(title="Completed", action="show", message=f"Added Graph #{active_idx+1}", color="green")], active_idx

    for g in graphs:
        if g.get("id") == active_idx:
            if title:
                g["title"] = title
            elif title == "":
                g.pop("title", None)
            g["x"] = str(x_drop)
            g["y"] = selected_y_cols
            g["y_axis_columns"] = selected_y_cols
            g["axis_mode"] = axis_mode or "single_axis"
            g["dual_axis"] = (axis_mode == "dual_axis")
            g["trace_mode"] = trace_mode or "markers"
            g["hover_data"] = hover_data or []
            if effective_filter and effective_filter != "Auto":
                g["filter"] = effective_filter
            else:
                g.pop("filter", None)
            if is_multi_y:
                g["multi_y_colors"] = [y_color_map[y_col] for y_col in selected_y_cols]
                g["y_color_map"] = y_color_map
            else:
                g.pop("multi_y_colors", None)
                g.pop("y_color_map", None)
            if x_min is not None and x_max is not None:
                g["x_range"] = [x_min, x_max]
            else:
                g.pop("x_range", None)
            if y_min is not None and y_max is not None:
                g["y_range"] = [y_min, y_max]
            else:
                g.pop("y_range", None)
            g["baseline"] = baseline_data or "ignore"
            if target_tab:
                g["tab"] = target_tab
            break

    updated_config["graphs"] = graphs
    return updated_config, [dict(title="Completed", action="show", message=f"Saved Graph #{active_idx+1} locally")], active_idx

#################################################################################################################
#################################################################################################################

# Commits current memory state to drive config.json
@callback(
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Input("save-disk-btn", "n_clicks"),
    State("session-config", "data"),
    prevent_initial_call=True,
)
def commit_config_to_disk(n_clicks, session_config):
    if not n_clicks or not session_config:
        return dash.no_update
    try:
        clean_file_output = json.loads(json.dumps(session_config))
        
        if "graphs" in clean_file_output:
            for g in clean_file_output["graphs"]:
                g.pop("id", None)
                
        with open("config.json", "w") as target_file:
            json.dump(clean_file_output, target_file, indent=2)
            
        return [dict(title="Completed", action="show", message="Configuration updated", color="green")]
    except Exception as ex:
        return [dict(title="Error", action="show", message="Failed to write configuration", color="red")]
