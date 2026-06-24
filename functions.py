import inspect
import json
import os
import sys
from typing import Any

import baselines as baseline
import dash_ag_grid as dag
import dash_mantine_components as dmc
import lookup
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from plotly.colors import sample_colorscale

if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))


def _collect_required_columns(config, date_col, tracked_params=None):
    required = []

    def add_column(name):
        column_name = str(name or "").strip()
        if column_name and column_name not in required:
            required.append(column_name)

    add_column("Engine")
    add_column("Date_Tested")
    add_column("Perf. Point")
    add_column(date_col)

    for param_name in tracked_params or []:
        add_column(param_name)

    for col_name in config.get("locked_col", []):
        add_column(col_name)
    for col_name in config.get("pinned_col", []):
        add_column(col_name)

    return required


def get_data(count=False):
    config_path = os.path.join(base_path, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}")

    print("DEBUG --- DATA FETCH")
    with open(config_path, "r") as f:
        config = json.load(f)

    data_source = config.get("data_source", {})
    file_path = data_source.get("file_path")
    sheet_name = data_source.get("sheet_name", 0)
    date_col = config.get("date_col")

    if lookup.BACKEND == "access" and getattr(lookup, "fetch_dataset", None):
        tracked_params = lookup._load_all_params() if getattr(lookup, "_load_all_params", None) else []
        required_columns = _collect_required_columns(config, date_col, tracked_params=tracked_params)
        df = lookup.fetch_dataset(required_columns=required_columns)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name)

    active_date_col = date_col if date_col in df.columns else "Date_Tested" if "Date_Tested" in df.columns else date_col
    if active_date_col not in df.columns:
        df[active_date_col] = pd.NA
    df["Full_date"] = pd.to_datetime(df[active_date_col], errors="coerce")
    df = df.sort_values(by="Full_date", ascending=False).reset_index(drop=True)

    df["sequential_id"] = len(df) - df.index

    try:
        if active_date_col in df.columns and active_date_col != "Full_date":
            df = df.drop(columns=[active_date_col])
        df.insert(2, active_date_col, df["Full_date"].dt.strftime("%Y-%m-%d"))
        df.insert(3, "Time", df["Full_date"].dt.strftime("%H:%M:%S"))
    except ValueError:
        pass

    df["Full_date"] = df["Full_date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    baseline_options = [
        name for name, obj in inspect.getmembers(baseline, inspect.isfunction)
        if obj.__module__ == baseline.__name__
    ]
    config["baseline_options"] = baseline_options
    config.setdefault("graph_tabs", ["Tab 1", "Tab 2"])

    if "graphs" in config:
        for idx, graph in enumerate(config["graphs"]):
            graph["id"] = idx
            graph.setdefault("tab", config["graph_tabs"][0])

    if count:
        return config, df.to_dict("records"), len(df.columns)
    return config, df.to_dict("records")


def _normalize_columns(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_list(value):
    return value if isinstance(value, list) else []


def _get_reference_ranges(dfa, clean_df, graph):
    df_len = len(dfa)
    if df_len == 0:
        return {}

    # Keep the original behavior of distinguishing between last / recent / default / baseline groups.
    # The baseline subset is intentionally computed from the cleaned frame so the graph still works
    # when the data contains missing values.
    base_df = clean_df.copy()

    if "Engine" in base_df.columns and "Date_tested" in base_df.columns:
        last_20_uniques = base_df["Engine"].dropna().unique()[-20:]
        if len(last_20_uniques) > 0:
            base_df = base_df[base_df["Engine"].isin(last_20_uniques)].copy()
        cutoff_date = graph.get("baseline_cutoff", "2012-01-01")
        if cutoff_date in base_df.columns:
            base_df = base_df[base_df[cutoff_date] <= cutoff_date].copy()
        elif "Date_tested" in base_df.columns:
            base_df = base_df[base_df["Date_tested"] <= cutoff_date].copy()

    ranges = {
        "Last": dfa.iloc[:1].copy() if len(dfa) > 0 else dfa.copy(),
        "Recent": dfa.iloc[1:11].copy() if len(dfa) > 11 else dfa.copy(),
        "Default": dfa.copy(),
        "Baseline": base_df.copy(),
    }

    excluded_indices = list(range(0, min(11, len(dfa))))
    ranges["Default"] = dfa.drop(index=excluded_indices, errors="ignore")
    return ranges


def _get_color_scale(graph, values):
    values_list = list(values)
    if not values_list:
        return []

    numeric_values = pd.to_numeric(pd.Series(values_list), errors="coerce")
    if numeric_values.notna().all():
        min_val = numeric_values.min()
        max_val = numeric_values.max()
        if pd.isna(min_val) or pd.isna(max_val):
            scale_points = [0.5] * len(values_list)
        elif max_val == min_val:
            scale_points = [0.5] * len(values_list)
        else:
            scale_points = ((numeric_values - min_val) / (max_val - min_val)).astype(float).tolist()
    else:
        if len(values_list) == 1:
            scale_points = [0.5]
        else:
            denom = float(len(values_list) - 1)
            scale_points = [idx / denom for idx in range(len(values_list))]

    custom_scale = graph.get("colorscale")
    if custom_scale:
        try:
            return sample_colorscale(custom_scale, scale_points)
        except Exception:
            pass

    try:
        return sample_colorscale("Viridis", scale_points)
    except Exception:
        return ["#636EFA"] * len(scale_points)


def _get_marker_style(graph, label, default_size, default_fill, default_line):
    marker_config = graph.get("marker_config", {})
    label_config = marker_config.get(label, {}) if isinstance(marker_config, dict) else {}
    return {
        "size": label_config.get("size", default_size),
        "color": label_config.get("fill", label_config.get("color", default_fill)),
        "line": {
            "width": label_config.get("line_width", 1),
            "color": label_config.get("line_color", default_line),
        },
    }


def _make_hovertemplate(x_col, y_cols, hover_cols):
    template = f"<b>{x_col}</b>: %{{x}}<br>"
    for idx, y_col in enumerate(y_cols):
        template += f"<b>{y_col}</b>: %{{y{idx + 1}}}<br>" if idx > 0 else f"<b>{y_col}</b>: %{{y}}<br>"
    for i, col in enumerate(hover_cols):
        template += f"<br><b>{col}</b>: %{{customdata[{i}]}}"
    template += "<extra></extra>"
    return template


def _resolve_filter_mode(graph):
    filter_mode = graph.get("filter")
    if filter_mode in (None, "", "Auto", "auto"):
        return "Auto"
    return filter_mode


def build_graph(graph, dfa, activeIDs=None):
    if dfa.empty:
        return go.Figure()

    x_col = graph.get("x")
    y_cols = _normalize_columns(graph.get("y", []))
    if not x_col or not y_cols or any(col not in dfa.columns for col in ([x_col] + y_cols)):
        return go.Figure()

    clean_df = dfa.dropna(subset=[x_col] + y_cols).copy()
    if clean_df.empty:
        return go.Figure()

    title = graph.get("title", f"{' vs '.join(y_cols)} vs {x_col}")
    hover_cols = _safe_list(graph.get("hover_data"))
    valid_hover_cols = [c for c in hover_cols if c in dfa.columns]
    hovertemplate = _make_hovertemplate(x_col, y_cols, valid_hover_cols)
    graph_trace_mode = graph.get("trace_mode", "markers")
    if graph_trace_mode not in {"markers", "lines+markers"}:
        graph_trace_mode = "markers"

    fig = go.Figure()
    baseline_mode = graph.get("baseline", "ignore")
    baseline_config = graph.get("baseline_config", {})
    filter_mode = _resolve_filter_mode(graph)

    default_layout = {
        "title": {"text": title, "font": {"size": 12}},
        "clickmode": "none",
        "hovermode": "closest",
        "showlegend": False,
        "margin": {"l": 5, "r": 5, "t": 50, "b": 10},
        "xaxis": {
            "showgrid": True,
            "gridcolor": "rgba(200,200,200,0.25)",
            "gridwidth": 1,
            "zeroline": False,
            "showline": True,
            "linecolor": "rgba(120,120,120,0.6)",
            "ticks": "outside",
            "ticklen": 5,
            "nticks": 35,
        },
        "yaxis": {
            "showgrid": True,
            "gridcolor": "rgba(200,200,200,0.25)",
            "gridwidth": 1,
            "zeroline": False,
            "showline": True,
            "linecolor": "rgba(120,120,120,0.6)",
            "ticks": "outside",
            "ticklen": 5,
            "nticks": 20,
        },
    }

    layout_overrides = graph.get("layout", {})
    if isinstance(layout_overrides, dict):
        default_layout.update(layout_overrides)
        if "xaxis" in layout_overrides and isinstance(layout_overrides["xaxis"], dict):
            default_layout["xaxis"].update(layout_overrides["xaxis"])
        if "yaxis" in layout_overrides and isinstance(layout_overrides["yaxis"], dict):
            default_layout["yaxis"].update(layout_overrides["yaxis"])

    if graph.get("x_range"):
        default_layout["xaxis"]["range"] = graph["x_range"]
    if graph.get("y_range"):
        default_layout["yaxis"]["range"] = graph["y_range"]

    range_map = _get_reference_ranges(dfa, clean_df, graph)

    if len(y_cols) > 1 and graph.get("dual_axis", False):
        default_layout["yaxis2"] = {
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        }

    def _opacity_for_subset(subset):
        if activeIDs is None:
            return 1.0
        selected = {str(i) for i in activeIDs}
        return [1.0 if str(val) in selected else 0.1 for val in subset["sequential_id"]]

    def _sort_subset_for_lines(subset, mode):
        if "lines" not in str(mode):
            return subset

        sorted_subset = subset.copy()

        # Prefer datetime progression first, then numeric progression, then string fallback.
        datetime_values = pd.to_datetime(sorted_subset[x_col], errors="coerce")
        if datetime_values.notna().any():
            sorted_subset = sorted_subset.assign(_sort_key=datetime_values)
            return sorted_subset.sort_values(by="_sort_key", kind="mergesort").drop(columns=["_sort_key"])

        numeric_values = pd.to_numeric(sorted_subset[x_col], errors="coerce")
        if numeric_values.notna().any():
            sorted_subset = sorted_subset.assign(_sort_key=numeric_values)
            return sorted_subset.sort_values(by="_sort_key", kind="mergesort").drop(columns=["_sort_key"])

        sorted_subset = sorted_subset.assign(_sort_key=sorted_subset[x_col].astype(str))
        return sorted_subset.sort_values(by="_sort_key", kind="mergesort").drop(columns=["_sort_key"])

    def _add_trace(subset, y_col, label, axis_name="y", trace_style=None):
        subset = _sort_subset_for_lines(subset, trace_style.get("mode", "markers") if trace_style else "markers")
        subset_customdata = subset[valid_hover_cols] if valid_hover_cols else None
        if trace_style is None:
            trace_style = {}

        marker_style = dict(
            size=trace_style.get("size", graph.get("marker_size", 8)),
            color=trace_style.get("color", graph.get("marker_color", "rgba(0,0,0,0)")),
            line={
                "width": trace_style.get("line_width", graph.get("line_width", 1)),
                "color": trace_style.get("line_color", graph.get("line_color", "rgba(0,0,0,0.25)")),
            },
        )

        fig.add_trace(
            go.Scatter(
                name=label,
                x=subset[x_col],
                y=subset[y_col],
                mode=trace_style.get("mode", "markers"),
                customdata=subset_customdata,
                hovertemplate=hovertemplate,
                yaxis=axis_name,
                line={
                    "width": trace_style.get("line_width", graph.get("line_width", 1)),
                    "color": trace_style.get("line_color", graph.get("line_color", "rgba(0,0,0,0.25)")),
                },
                marker=dict(
                    size=marker_style["size"],
                    color=marker_style["color"],
                    line=marker_style["line"],
                    opacity=_opacity_for_subset(subset) if activeIDs is not None else 1.0,
                ),
            )
        )

    # Default trace groups (still used as the fallback reference behavior requested).
    trace_order = ["Last", "Recent", "Default", "Baseline"]
    trace_specs = {}
    for label in trace_order:
        subset = range_map.get(label)
        if subset is None or subset.empty:
            continue
        trace_specs[label] = {
            "subset": subset,
            "size": graph.get("trace_size", {}).get(label, graph.get("marker_size", 8)),
            "line_color": graph.get("trace_line_color", {}).get(label, graph.get("line_color", "rgba(0,0,0,0.25)")),
            "fill": graph.get("trace_color", {}).get(label, graph.get("marker_color", "rgba(0,0,0,0)")),
        }

    # Multi-Y mode ignores filter coloring and uses stable, per-series colors.
    if len(y_cols) > 1:
        multi_y_colors = graph.get("multi_y_colors", [
            "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#17becf", "#bcbd22",
        ])
        if not isinstance(multi_y_colors, list) or len(multi_y_colors) == 0:
            multi_y_colors = ["#1f77b4", "#d62728", "#2ca02c"]

        trace_mode = graph_trace_mode
        for idx, y_col in enumerate(y_cols):
            axis_name = "y2" if graph.get("dual_axis", False) and idx == 1 else "y"
            if graph.get("dual_axis", False) and idx == 1:
                default_layout["yaxis2"] = {
                    "overlaying": "y",
                    "side": "right",
                    "showgrid": False,
                }

            series_color = multi_y_colors[idx % len(multi_y_colors)]
            _add_trace(
                clean_df,
                y_col,
                y_col,
                axis_name=axis_name,
                trace_style={
                    "mode": trace_mode,
                    "size": graph.get("marker_size", 6),
                    "color": series_color,
                    "line_color": series_color,
                },
            )
    else:
        if "lines" in graph_trace_mode:
            perf_col = graph.get("perf_col", "Perf. Point")
            marker_color = graph.get("marker_color", "rgba(0,0,0,0)")
            line_color = graph.get("line_color", "rgba(0,0,0,0.25)")

            if filter_mode == "Perf" and perf_col in clean_df.columns:
                perf_colors = graph.get("perf_colors", {
                    "03_Take_Off": "#1f77b4",
                    "04_Take_Off": "#ff7f0e",
                    "08_Take_Off": "#008000",
                    "A3_Take_Off": "#1f77b4",
                    "B8_Take_Off": "#00d0ff",
                    "B9_Take_Off": "#ff0000",
                    "B5_Take_Off": "#604200",
                })
                marker_color = clean_df[perf_col].map(perf_colors).fillna(graph.get("perf_default_color", "rgb(0,0,255)")).tolist()
            elif filter_mode in ("Time", "Date", "DateTime") and x_col in clean_df.columns:
                marker_color = _get_color_scale(graph, range(len(clean_df)))
            elif filter_mode in clean_df.columns and filter_mode != "Perf":
                column_values = clean_df[filter_mode].dropna()
                if pd.api.types.is_numeric_dtype(column_values):
                    normalized = (column_values - column_values.min()) / (column_values.max() - column_values.min()) if column_values.max() != column_values.min() else column_values
                    marker_color = _get_color_scale(graph, normalized.to_list())
                else:
                    marker_color = _get_color_scale(graph, range(len(column_values)))

            _add_trace(
                clean_df,
                y_cols[0],
                graph.get("filter_label", y_cols[0]),
                trace_style={
                    "mode": graph_trace_mode,
                    "size": graph.get("marker_size", 6),
                    "color": marker_color,
                    "line_color": line_color,
                },
            )
        else:
            perf_col = graph.get("perf_col", "Perf. Point")
            if filter_mode == "Perf" and perf_col in clean_df.columns:
                perf_colors = graph.get("perf_colors", {
                    "03_Take_Off": "#1f77b4",
                    "04_Take_Off": "#ff7f0e",
                    "08_Take_Off": "#008000",
                    "A3_Take_Off": "#1f77b4",
                    "B8_Take_Off": "#00d0ff",
                    "B9_Take_Off": "#ff0000",
                    "B5_Take_Off": "#604200",
                })
                perf_labels = graph.get("perf_labels", {})
                for label in trace_order:
                    subset = trace_specs.get(label, {}).get("subset")
                    if subset is None or subset.empty or perf_col not in subset.columns:
                        continue
                    color_values = subset[perf_col].map(perf_colors).fillna(graph.get("perf_default_color", "rgb(0,0,255)"))
                    _add_trace(
                        subset,
                        y_cols[0],
                        perf_labels.get(label, label),
                        trace_style={
                            "size": trace_specs[label].get("size", graph.get("marker_size", 6)),
                            "mode": graph_trace_mode,
                            "color": color_values.tolist(),
                            "line_color": trace_specs[label].get("line_color", graph.get("line_color", "rgba(0,0,0,0.25)")),
                        },
                    )
            elif filter_mode in ("Time", "Date", "DateTime") and x_col in clean_df.columns:
                color_values = clean_df[x_col].astype(str)
                trace_colors = _get_color_scale(graph, range(len(color_values)))
                _add_trace(
                    clean_df,
                    y_cols[0],
                    graph.get("filter_label", filter_mode),
                    trace_style={
                        "size": graph.get("marker_size", 6),
                        "mode": graph_trace_mode,
                        "color": trace_colors,
                        "line_color": graph.get("line_color", "rgba(0,0,0,0.25)"),
                    },
                )
            elif filter_mode in clean_df.columns and filter_mode != "Perf":
                column_values = clean_df[filter_mode].dropna()
                if pd.api.types.is_numeric_dtype(column_values):
                    normalized = (column_values - column_values.min()) / (column_values.max() - column_values.min()) if column_values.max() != column_values.min() else column_values
                    trace_colors = _get_color_scale(graph, normalized.to_list())
                else:
                    trace_colors = _get_color_scale(graph, range(len(column_values)))
                _add_trace(
                    clean_df,
                    y_cols[0],
                    graph.get("filter_label", filter_mode),
                    trace_style={
                        "size": graph.get("marker_size", 6),
                        "mode": graph_trace_mode,
                        "color": trace_colors,
                        "line_color": graph.get("line_color", "rgba(0,0,0,0.25)"),
                    },
                )
            else:
                for label in trace_order:
                    subset = trace_specs.get(label, {}).get("subset")
                    if subset is None or subset.empty:
                        continue
                    _add_trace(
                        subset,
                        y_cols[0],
                        label,
                        trace_style={
                            "size": trace_specs[label].get("size", graph.get("marker_size", 6)),
                            "mode": graph_trace_mode,
                            "color": trace_specs[label].get("fill", graph.get("marker_color", "rgba(0,0,0,0)")),
                            "line_color": trace_specs[label].get("line_color", graph.get("line_color", "rgba(0,0,0,0.25)")),
                        },
                    )

    # Baseline lines are still optional and can be configured via the graph settings.
    if baseline_mode != "ignore":
        baseline_function = getattr(baseline, baseline_mode, None)
        if baseline_function is not None:
            try:
                lineset = baseline_function(dfa, clean_df, graph, graph.get("id", 0), x_col, y_cols[0])
                if lineset is not None:
                    for row in lineset:
                        x1, x2, y1, y2, lineid = row
                        line_color = "rgb(255, 0, 0)" if lineid == 0 else "rgb(0, 13, 255)"
                        line_style = baseline_config.get("line_style", {})
                        fig.add_shape(
                            type="line",
                            x0=x1,
                            y0=y1,
                            x1=x2,
                            y1=y2,
                            xref="x",
                            yref="y",
                            layer="below",
                            line={
                                "color": line_style.get("color", line_color),
                                "width": line_style.get("width", 1),
                                "dash": line_style.get("dash", "dash" if lineid == 0 else "dot"),
                            },
                        )
            except Exception as exc:
                print(f"Baseline render error: {exc}")

    # Keep a commented version of the previous hard-coded baseline logic for future tweaks.
    # if "Engine" in clean_df.columns and "Date_tested" in clean_df.columns:
    #     cutoff_date = graph.get("baseline_cutoff", "2012-01-01")
    #     bl = clean_df[clean_df["Date_tested"] <= cutoff_date].copy()

    fig.update_layout(**default_layout)
    return fig


def build_card(config, graphs, dfa, active_ids=None, layout_span=None):
    graph_tabs = config.get("graph_tabs", ["Tab 1", "Tab 2"])
    tab_panels = []

    height_map = {
        4: "45vh",
        6: "60vh",
        12: "75vh",
    }

    selected_span = None
    try:
        selected_span = int(layout_span) if layout_span is not None else None
    except (TypeError, ValueError):
        selected_span = None

    for tab_name in graph_tabs:
        cards = []
        grouped_graphs = [graph for graph in graphs if graph.get("tab", graph_tabs[0]) == tab_name]
        card_span = selected_span if selected_span in height_map else (12 if len(grouped_graphs) == 1 else 6 if len(grouped_graphs) == 2 else 4)
        card_height = height_map.get(card_span, "60vh")
        for graph in grouped_graphs:
            try:
                graph_id = graph["id"]
                fig = build_graph(graph, dfa, active_ids)
                cards.append(
                    dmc.GridCol(
                        [
                            dmc.Paper(
                                [
                                    dcc.Loading(
                                        overlay_style={"visibility": "visible", "opacity": .8, "backgroundColor": "white"},
                                        id=f"loading-{graph_id}",
                                        type="default",
                                        style={"height": "100%", "width": "100%", "display": "flex", "flexDirection": "column"},
                                        parent_style={"height": "100%", "width": "100%"},
                                        children=dcc.Graph(
                                            id={"type": "graphcard", "index": graph_id},
                                            figure=fig,
                                            responsive=True,
                                            style={"flexGrow": 1, "height": "100%", "width": "100%"},
                                            config={
                                                "displaylogo": False,
                                                "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                                                "toImageButtonOptions": {
                                                    "format": "png",
                                                    "filename": graph.get("title", f"{graph.get('y')} vs {graph.get('x')}"),
                                                    "height": config.get("captureheight"),
                                                    "width": config.get("capturewidth"),
                                                    "scale": config.get("capturescale"),
                                                },
                                            },
                                        ),
                                    )
                                ],
                                withBorder=True,
                                shadow="sm",
                                p="md",
                                style={"height": "100%", "display": "flex", "flexDirection": "column"},
                            )
                        ],
                        id={"type": "col_container", "index": graph_id},
                        span=card_span,
                        style={"height": card_height, "display": "flex", "flexDirection": "column", "width": "100%"},
                    )
                )
            except Exception as exc:
                cards.insert(
                    0,
                    dmc.GridCol([
                        dmc.Alert(f"Missing configuration parameters: {exc}", color="red", withCloseButton=True),
                    ], span=12),
                )
                print(exc)

        tab_panels.append(
            dmc.TabsPanel(
                children=dmc.Grid(
                    cards,
                    gutter="sm",
                    columns=12,
                    # Future reference: setting grow=True makes the last row stretch cards to fill remaining space.
                    # grow=True,
                    grow=False,
                    justify="stretch",
                    style={"minHeight": "75vh", "width": "100%"},
                ) if cards else dmc.Text("No graphs configured for this tab."),
                value=tab_name,
                style={"minHeight": "75vh", "width": "100%"},
            )
        )

    return dmc.Tabs(
        [
            dmc.TabsList(
                [dmc.TabsTab(tab_name, value=tab_name) for tab_name in graph_tabs],
                style={"justifyContent": "center"},
            ),
            *tab_panels,
        ],
        value=graph_tabs[0],
        id="graph-tabs",
        className="mb-3",
        style={"width": "100%"},
    )


def build_grid(config, records):
    if not records:
        return html.Div("No rows to display. Fetch data first.")
    df = pd.DataFrame(records)
    columnDefs = []
    locked_cols = config.get("locked_col", [])
    pinned_cols = config.get("pinned_col", [])

    decimal_rounding = {"function": "d3.format('.3f')(params.value) "}

    for i in df.columns:
        if i in ["Full_date", "sequential_id"]:
            continue

        col_setup: dict[str, Any] = {"field": i, "columnSize": "autoSize", "headerClass": "center-header"}

        if pd.api.types.is_numeric_dtype(df[i]):
            col_setup["valueFormatter"] = decimal_rounding
            col_setup["type"] = "numericColumn"
            col_setup["cellStyle"] = {"styleConditions": [
                {
                    "condition": "params.value < -1000",
                    "style": {"backgroundColor": "red"},
                },
                {
                    "condition": "params.value > 50000",
                    "style": {"backgroundColor": "red"},
                }
            ]}

        if i in locked_cols:
            col_setup.update(
                {
                    "floatingFilter": True,
                    "pinned": "left",
                    "lockPinned": True,
                    "lockPosition": True,
                    "suppressMovable": True,
                }
            )
        elif i in pinned_cols:
            col_setup.update({"pinned": True})

        columnDefs.append(col_setup)

    return dag.AgGrid(
        id="data-grid",
        rowData=records,
        columnDefs=columnDefs,
        dashGridOptions={
            "suppressFieldDotNotation": True,
            "suppressColumnVirtualisation": False,
            "rowBuffer": 10,
            "animateRows": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "cacheQuickFilter": True,
            "rowHeight": 20,
            "onBodyScroll": {"function": "dash_clientside.my_namespace.handleScrollSizing"},
            "theme": {
                "function": "themeQuartz.withParams({ spacing: 2, fontSize: 12 })"
            },
        },
        defaultColDef={
            "filter": True,
            "sortable": True,
            "resizable": True,
            "suppressMovable": False,
            "headerClass": "center-header",
        },
        columnSize="autoSize",
        style={"height": "100%"},
        className="ag-theme-quartz",
    )