import dash
from dash import MATCH, Input, Output, State, callback, html, ALL
import dash_mantine_components as dmc
from functions import build_card, build_graph

# Register page and define path
dash.register_page(__name__, path="/graphs")

def layout():
    return html.Div(
        [
            dash.dcc.Store(id="graph-layout-selector-store", storage_type="local", data="4"),
            dmc.Paper(
                withBorder=True,
                shadow="xs",
                p="sm",
                mt=60,
                children=dmc.Group(
                    justify="space-between",
                    align="end",
                    wrap="wrap",
                    children=[
                        dmc.Group(
                            gap="sm",
                            align="end",
                            wrap="wrap",
                            children=[
                                dmc.NumberInput(
                                    id="edit-export-height",
                                    placeholder="1200",
                                    label="PNG H",
                                    hideControls=True,
                                    style={"width": "110px"},
                                ),
                                dmc.NumberInput(
                                    id="edit-export-width",
                                    placeholder="1600",
                                    label="PNG W",
                                    hideControls=True,
                                    style={"width": "110px"},
                                ),
                                dmc.NumberInput(
                                    id="edit-export-scale",
                                    placeholder="2",
                                    label="Scale",
                                    hideControls=False,
                                    style={"width": "90px"},
                                ),
                            ],
                        ),
                        dmc.Group(
                            gap="md",
                            align="center",
                            wrap="wrap",
                            children=[
                                dmc.Text("Layout", size="sm", fw=600),
                                dash.dcc.RadioItems(
                                    id="selector",
                                    options=[
                                        {"label": "Small", "value": "4"},
                                        {"label": "Medium", "value": "6"},
                                        {"label": "Large", "value": "12"},
                                    ],
                                    value="4",
                                    persistence=True,
                                    persistence_type="local",
                                    inline=True,
                                ),
                                dmc.Button(
                                    id="refresh-graphs",
                                    children="Refresh",
                                    size="sm",
                                    variant="outline",
                                ),
                            ],
                        ),
                    ],
                ),
            ),
            html.Hr(),
            #dash.dcc.Loading(
            #    id="loading-graphics",
            #    overlay_style={"visibility": "visible", "opacity": .5, "backgroundColor": "white"},
            #    children=
                    html.Div(
                        id="graph-cards-holder",
                        style={"minHeight": "75vh", "width": "100%"},
                    )
            #),
        ],
        style={"marginTop": "20px"}
    )

@callback(
    Output("graph-layout-selector-store", "data"),
    Input("selector", "value"),
    State("graph-layout-selector-store", "data"),
    prevent_initial_call=True,
)
def persist_layout_selector(selected_layout, stored_layout):
    if not selected_layout or selected_layout == stored_layout:
        return dash.no_update
    return selected_layout


@callback(
    Output("graph-cards-holder", "children"),
    Output("config-apply", "data"),
    State("session-config", "data"),
    Input("session-dataframe", "data"),
    Input("virtual-ids-store", "data"),
    Input("graph-layout-selector-store", "data"),
    State("config-apply", "data"),
    #running=[(Output("main-loader", "visible"), True, False)],
)
def update_graph_data(config, records, filtered_ids, layout_selection, apply):
    if not config or not records:
        return html.Div("No data loaded"), False
    if apply == True:
        return dash.no_update, False
    import pandas as pd
    df = pd.DataFrame(records)
    return build_card(
        config,
        config.get("graphs", []),
        df,
        active_ids=filtered_ids,
        layout_span=layout_selection or "4",
    ), False

@callback(
    Output({"type": "col_container", "index": ALL}, "span"),
    Output({"type": "col_container", "index": ALL}, "style"),
    Input("selector", "value"),
    State({"type": "col_container", "index": ALL}, "id"),
    prevent_initial_call=True
)
def update_layout_dimensions(span_selection, existing_container_ids):
    # Fallback early if no elements exist on screen yet
    if not existing_container_ids:
        return [], []

    span_value = int(span_selection)

    # Calculate corresponding heights based on column layout sizes
    if span_value == 4:
        computed_height = "45vh"
    elif span_value == 6:
        computed_height = "60vh"
    else:
        computed_height = "75vh"

    updated_style = {
        "height": computed_height,
        "display": "flex",
        "flexDirection": "column"
    }

    matched_graphs_count = len(existing_container_ids)

    # Return pristine python lists directly without relying on js script rendering
    return [span_value] * matched_graphs_count, [updated_style] * matched_graphs_count


@callback(
    Output({"type": "graphcard", "index": MATCH}, "figure"),
    Input("virtual-ids-store", "data"),
    Input("refresh-graphs", "n_clicks"),
    State("session-config", "data"),
    State("session-dataframe", "data"),
    State({"type": "graphcard", "index": MATCH}, "id"),
    prevent_initial_call=True,
)
def refresh_brushed_subset(filtered_ids, trigger, config, records, trace_identity):
    if not config or not records:
        return dash.no_update
    import pandas as pd
    df = pd.DataFrame(records)
    target_id = trace_identity["index"]
    graph_config = None

    for g in config.get("graphs", []):
        if g.get("id") == target_id:
            graph_config = g
            break

    if not graph_config:
        return dash.no_update

    return build_graph(graph_config, df, activeIDs=filtered_ids)