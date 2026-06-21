import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback, html, State
from functions import build_grid, get_data

# Register page and define path
dash.register_page(__name__, path="/table")

# Define current app layout
def layout():
    return html.Div(
        [
            html.H3("", className="mb-3"),
            html.Div(style={"height": 40}),
            html.Div(
                id="grid-target-mount",
                children=[dmc.Alert("Data not loaded", color="red", variant="outline", withCloseButton=False)],
                style={"minHeight": "70vh"},
            ),
        ],
        style={"marginTop": "20px", "minHeight": "80vh"}
    )

@callback(
    Output("grid-target-mount", "children"),
    State("session-config", "data"),
    Input("session-dataframe", "data"),
)
def render_workspace_grid(config, records):
    if (not config or not records):
        try:
            loaded_config, loaded_records = get_data()
            config = config or loaded_config
            records = records or loaded_records
        except Exception:
            pass

    if not config or not records:
        return html.Div(
            dmc.Alert(
                "Data not loaded",
                color="red",
                variant="light",
                withCloseButton=False,
            )
        )
    return build_grid(config, records)

@callback(
    Output("virtual-ids-store", "data"),
    Input("data-grid", "virtualRowData"),
    prevent_initial_call=True,
)
def cache_grid_filters(virtual_data):
    if not virtual_data:
        return dash.no_update
    return [
        row["sequential_id"]
        for row in virtual_data
        if "sequential_id" in row
    ]

