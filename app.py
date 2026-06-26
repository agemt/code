import os
import sys
import dash
import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, callback, html, dcc
import dash_mantine_components as dmc
import compiler_explicit_imports  # noqa: F401
from functions import get_data
import threading

prod = False
#prod = True

def _resolve_base_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else script_dir

    # PyInstaller exposes _MEIPASS, while Nuitka keeps compiled modules near __file__.
    meipass_dir = getattr(sys, "_MEIPASS", None)
    candidates = [meipass_dir, script_dir, exe_dir]

    for candidate in candidates:
        if candidate and os.path.isdir(os.path.join(candidate, "pages")):
            return candidate

    return script_dir


base_path = _resolve_base_path()
pages_dir = os.path.join(base_path, "pages")

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=pages_dir,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

# Pre-load layouts to memory
page_containers = []
for page in dash.page_registry.values():
    page_containers.append(
        html.Div(
            id={"type": "page-wrapper", "path": page["relative_path"]},
            children=page["layout"](),
            style={"display": "none"},
        )
    )

# Define main layout and memory elements
app.layout = dmc.MantineProvider([html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="session-config", data=None, storage_type="session"),
        dcc.Store(id="session-dataframe", data=None, storage_type="session"),
        dcc.Store(id="virtual-ids-store", data=None, storage_type="session"),
        dcc.Store(id="config-apply", data=False, storage_type="session"),

        # Top bar setup
        dbc.NavbarSimple(
            children=[
                dmc.Button(
                    "Reload Data",
                    id="global-fetch-btn",
                    color="light",
                    variant="white",
                    size="sm",
                    className="me-4",
                    loading=False,
                    loaderProps={"type": "dots"},
                ),
                dmc.Button(
                    "test",
                    id="notification-test",
                    color="light",
                    size="sm",
                    className="me-4",
                ),
                dbc.NavItem(dbc.NavLink("Table", id="nav-grid-btn", href="/table", style={"color": "rgb(255, 255, 255)"})),
                dbc.NavItem(dbc.NavLink("Lookup", href="/", style={"color": "rgb(255, 255, 255)"})),
                dbc.NavItem(dbc.NavLink("Graph", href="/graphs", style={"color": "rgb(255, 255, 255)"})),
                dbc.NavItem(dbc.NavLink("Export", href="/export", style={"color": "rgb(255, 255, 255)"})),
                dbc.NavItem(dbc.NavLink("Configuration", href="/editor", style={"color": "rgb(255, 255, 255)"})),
            ],
            brand="CFM56-5B Trending",
            brand_href="/",
            color="primary",
            dark=True,
            className="me-auto ms-0 ps-0",
            fluid=True,
        ),
        # Current page container
        dmc.LoadingOverlay(
            visible=False,
            id="main-loader",
            overlayProps={"radius": "sm", "blur": 2},
            zIndex=10,
        ),
        dbc.Container(page_containers, fluid=True),
        # Notification engine
        dmc.NotificationContainer(id="notification-container", position="bottom-right", autoClose=6000, limit=5),
    ]
)])

@callback(
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Input("notification-test", "n_clicks"),
    prevent_initial_call=True
)
def test(n):
    return [dict(title="Notification", action="show", message="Notif", color="green")]

# Page switching
@callback(
    Output({"type": "page-wrapper", "path": dash.ALL}, "style"),
    Input("url", "pathname"),
    State({"type": "page-wrapper", "path": dash.ALL}, "id"),
    running=[(Output("main-loader", "visible"), True, False)],
)
def route_page(current_pathname, wrapper_ids):
    current = (current_pathname or "/").rstrip("/") or "/"
    styles = []
    for wid in wrapper_ids:
        wrapper_path = (wid.get("path") or "/").rstrip("/") or "/"
        if wrapper_path == current:
            styles.append({"display": "block"})
        else:
            styles.append({"display": "none"})
    return styles

# Reload data button
@callback(
    Output("notification-container", "sendNotifications", allow_duplicate=True),
    Output("session-config", "data"),
    Output("session-dataframe", "data"),
    Input("global-fetch-btn", "n_clicks"),
    running=[(Output("global-fetch-btn", "loading"), True, False)],
    prevent_initial_call=True,
)
def fetch_trigger(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    config, records, count = get_data(count=True) # type: ignore
    return [dict(title="Data loaded", action="show", message=f"Data loaded from {config.get('data_source').get('file_path')}. Found {len(records)} entries")], config, records

@callback(
    Output("data-grid", "columnSize"),
    Input("nav-grid-btn", "n_clicks"),
    State("session-dataframe", "data"),
    prevent_initial_call=True
)
def force_grid_autosize_on_tab_switch(n_clicks, grid_data):
    if not grid_data:
        return dash.no_update
    return "autoSize"

def run_dash():
    app.run(debug=False, port=8050, use_reloader=False)

if prod:
    if __name__ == "__main__":
        # Start the Flask/Dash server in the background
        threading.Thread(target=run_dash, daemon=True).start()

        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtCore import QUrl

        qt_app = QApplication(sys.argv)
        window = QMainWindow()
        window.setWindowTitle("Dash Desktop App")
        #window.resize(1200, 800)

        browser = QWebEngineView()
        browser.setUrl(QUrl("http://127.0.0.1:8050"))

        def handle_download(download_item: QWebEngineDownloadRequest):
            download_item.setDownloadDirectory(download_item.downloadDirectory())
            download_item.accept()

        browser.page().profile().downloadRequested.connect(handle_download)
        
        window.setCentralWidget(browser)
        window.showMaximized()
        sys.exit(qt_app.exec())
else:
    if __name__ == "__main__":
        app.run(debug=True, port=8050, use_reloader=True)