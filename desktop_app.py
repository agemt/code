import copy
import json
import os
import sys
import tempfile
from typing import Any

import pandas as pd
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

import functions
from functions import build_graph, get_data


def _parse_optional_number(raw_value: str) -> float | None:
    text = (raw_value or "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _selected_values(list_widget: QListWidget) -> list[str]:
    return [item.text() for item in list_widget.selectedItems()]


def _set_selected_values(list_widget: QListWidget, values: list[str]) -> None:
    wanted = set(values)
    for idx in range(list_widget.count()):
        item = list_widget.item(idx)
        item.setSelected(item.text() in wanted)


class ApplicationState:
    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.selected_ids: list[str] = []

    @property
    def dataframe(self) -> pd.DataFrame:
        if not self.records:
            return pd.DataFrame()
        return pd.DataFrame(self.records)

    def load(self) -> None:
        config, records = get_data()
        self.config = config
        self.records = records


class PlotlyView(QWebEngineView):
    def __init__(self) -> None:
        super().__init__()
        self._temp_dir = tempfile.mkdtemp(prefix="plotly_qt_")
        self._last_html_path: str | None = None

    def set_figure(self, figure, filename: str, capture_h: int, capture_w: int, capture_scale: int) -> None:
        config = {
            "displaylogo": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": filename,
                "height": capture_h,
                "width": capture_w,
                "scale": capture_scale,
            },
        }
        html = figure.to_html(full_html=False, include_plotlyjs="inline", config=config)
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (filename or "plot"))
        html_path = os.path.join(self._temp_dir, f"{safe_name}.html")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(html)
        self._last_html_path = html_path
        self.load(QUrl.fromLocalFile(html_path))


class TableTab(QWidget):
    def __init__(self, state: ApplicationState, status: QStatusBar) -> None:
        super().__init__()
        self.state = state
        self.status = status

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter rows...")

        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)

        self.model = QStandardItemModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.table.setModel(self.proxy)

        top = QHBoxLayout()
        top.addWidget(QLabel("Search"))
        top.addWidget(self.filter_input)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

        self.filter_input.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def reload(self) -> None:
        df = self.state.dataframe
        self.model.clear()
        if df.empty:
            self.model.setHorizontalHeaderLabels(["No data loaded"])
            return

        columns = [c for c in df.columns if c != "Full_date"]
        self.model.setHorizontalHeaderLabels(columns)

        for _, row in df[columns].iterrows():
            items = [QStandardItem("" if pd.isna(v) else str(v)) for v in row.values]
            self.model.appendRow(items)

        if "sequential_id" in columns:
            seq_col = columns.index("sequential_id")
            self.table.setColumnHidden(seq_col, True)

        self.table.resizeColumnsToContents()
        self.status.showMessage(f"Loaded {len(df)} rows in table", 3000)

    def _on_selection_changed(self, *_args) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        seq_idx = self._sequential_column_index()
        if seq_idx is None:
            self.state.selected_ids = []
            return

        ids: list[str] = []
        for index in selected_rows:
            src = self.proxy.mapToSource(index)
            value = self.model.item(src.row(), seq_idx).text()
            ids.append(value)

        self.state.selected_ids = ids
        self.status.showMessage(f"Selected {len(ids)} rows for graph highlighting", 2000)

    def _sequential_column_index(self) -> int | None:
        for col in range(self.model.columnCount()):
            if self.model.horizontalHeaderItem(col).text() == "sequential_id":
                return col
        return None


class GraphsTab(QWidget):
    def __init__(self, state: ApplicationState) -> None:
        super().__init__()
        self.state = state

        self.layout_selector = QComboBox()
        self.layout_selector.addItems(["Small", "Medium", "Large"])
        self.layout_selector.setCurrentText("Small")
        self.refresh_btn = QPushButton("Refresh")

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("Layout"))
        control_row.addWidget(self.layout_selector)
        control_row.addStretch(1)
        control_row.addWidget(self.refresh_btn)

        self.tabs = QTabWidget()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.tabs)

        layout = QVBoxLayout(self)
        layout.addLayout(control_row)
        layout.addWidget(self.tabs)

        self.refresh_btn.clicked.connect(self.reload)
        self.layout_selector.currentTextChanged.connect(self.reload)

    def reload(self) -> None:
        self.tabs.clear()
        if not self.state.config or not self.state.records:
            empty = QLabel("No data loaded")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            holder = QWidget()
            box = QVBoxLayout(holder)
            box.addWidget(empty)
            self.tabs.addTab(holder, "Graphs")
            return

        config = self.state.config
        df = self.state.dataframe
        graph_tabs = config.get("graph_tabs", ["Tab 1", "Tab 2"])
        graphs = config.get("graphs", [])

        span = {"Small": 4, "Medium": 6, "Large": 12}[self.layout_selector.currentText()]
        cols = {4: 3, 6: 2, 12: 1}[span]
        card_height = {4: 320, 6: 430, 12: 560}[span]

        for tab_name in graph_tabs:
            container = QWidget()
            grid = QGridLayout(container)
            row = 0
            col = 0

            for graph in [g for g in graphs if g.get("tab", graph_tabs[0]) == tab_name]:
                graph_id = graph.get("id", 0)
                panel = QGroupBox(graph.get("title", f"Graph #{graph_id + 1}"))
                panel_layout = QVBoxLayout(panel)

                view = PlotlyView()
                view.setMinimumHeight(card_height)

                fig = build_graph(graph, df, activeIDs=self.state.selected_ids)
                filename = graph.get("title", f"graph_{graph_id + 1}")
                view.set_figure(
                    fig,
                    filename=filename,
                    capture_h=int(config.get("captureheight", 1200)),
                    capture_w=int(config.get("capturewidth", 1600)),
                    capture_scale=int(config.get("capturescale", 2)),
                )

                panel_layout.addWidget(view)
                grid.addWidget(panel, row, col)

                col += 1
                if col >= cols:
                    col = 0
                    row += 1

            if grid.count() == 0:
                empty = QLabel("No graphs configured in this tab")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(empty, 0, 0)

            self.tabs.addTab(container, str(tab_name))


class ExportTab(QWidget):
    def __init__(self, state: ApplicationState, status: QStatusBar) -> None:
        super().__init__()
        self.state = state
        self.status = status
        self.local_graph: dict[str, Any] | None = None

        self.title_edit = QLineEdit()
        self.x_combo = QComboBox()
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Auto", "Perf", "Time"])
        self.baseline_combo = QComboBox()
        self.axis_mode_combo = QComboBox()
        self.axis_mode_combo.addItems(["single_axis", "dual_axis"])
        self.trace_mode_combo = QComboBox()
        self.trace_mode_combo.addItems(["markers", "lines+markers"])

        self.y_list = QListWidget()
        self.y_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.hover_list = QListWidget()
        self.hover_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        self.x_min = QLineEdit()
        self.x_max = QLineEdit()
        self.y_min = QLineEdit()
        self.y_max = QLineEdit()

        self.capture_h = QLineEdit("1200")
        self.capture_w = QLineEdit("1600")
        self.capture_scale = QLineEdit("2")

        self.preview_btn = QPushButton("Preview")
        self.save_local_btn = QPushButton("Save locally")

        form = QFormLayout()
        form.addRow("Title", self.title_edit)
        form.addRow("X", self.x_combo)
        form.addRow("Y (multi)", self.y_list)
        form.addRow("Hover data", self.hover_list)
        form.addRow("Filter", self.filter_combo)
        form.addRow("Baseline", self.baseline_combo)
        form.addRow("Axis mode", self.axis_mode_combo)
        form.addRow("Trace mode", self.trace_mode_combo)
        form.addRow("X min", self.x_min)
        form.addRow("X max", self.x_max)
        form.addRow("Y min", self.y_min)
        form.addRow("Y max", self.y_max)
        form.addRow("PNG height", self.capture_h)
        form.addRow("PNG width", self.capture_w)
        form.addRow("PNG scale", self.capture_scale)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addLayout(form)
        left_layout.addWidget(self.preview_btn)
        left_layout.addWidget(self.save_local_btn)

        self.preview = PlotlyView()

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.preview)
        splitter.setSizes([350, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.preview_btn.clicked.connect(self.preview_graph)
        self.save_local_btn.clicked.connect(self.save_local)
        self.axis_mode_combo.currentTextChanged.connect(self._enforce_dual_axis_limit)

    def reload(self) -> None:
        self.x_combo.blockSignals(True)
        self.baseline_combo.blockSignals(True)
        self.y_list.blockSignals(True)
        self.hover_list.blockSignals(True)

        self.x_combo.clear()
        self.baseline_combo.clear()
        self.y_list.clear()
        self.hover_list.clear()

        if not self.state.records or not self.state.config:
            self.x_combo.blockSignals(False)
            self.baseline_combo.blockSignals(False)
            self.y_list.blockSignals(False)
            self.hover_list.blockSignals(False)
            return

        cols = self.state.dataframe.columns.tolist()
        for col in cols:
            self.x_combo.addItem(col)
            self.y_list.addItem(QListWidgetItem(col))
            self.hover_list.addItem(QListWidgetItem(col))

        for baseline_name in self.state.config.get("baseline_options", []):
            self.baseline_combo.addItem(baseline_name)

        self.x_combo.blockSignals(False)
        self.baseline_combo.blockSignals(False)
        self.y_list.blockSignals(False)
        self.hover_list.blockSignals(False)

        self.preview_graph()

    def _enforce_dual_axis_limit(self) -> None:
        if self.axis_mode_combo.currentText() != "dual_axis":
            return
        selected = self.y_list.selectedItems()
        if len(selected) <= 2:
            return
        for item in selected[2:]:
            item.setSelected(False)

    def preview_graph(self) -> None:
        if not self.state.records:
            return

        y_cols = _selected_values(self.y_list)
        if self.axis_mode_combo.currentText() == "dual_axis" and len(y_cols) > 2:
            y_cols = y_cols[:2]

        if not self.x_combo.currentText() or not y_cols:
            return

        cfg: dict[str, Any] = {
            "title": self.title_edit.text().strip() or f"{', '.join(y_cols)} vs {self.x_combo.currentText()}",
            "x": self.x_combo.currentText(),
            "y": y_cols,
            "hover_data": _selected_values(self.hover_list),
            "filter": self.filter_combo.currentText() or "Auto",
            "baseline": self.baseline_combo.currentText() or "ignore",
            "axis_mode": self.axis_mode_combo.currentText(),
            "dual_axis": self.axis_mode_combo.currentText() == "dual_axis",
            "trace_mode": self.trace_mode_combo.currentText(),
        }

        x_min = _parse_optional_number(self.x_min.text())
        x_max = _parse_optional_number(self.x_max.text())
        y_min = _parse_optional_number(self.y_min.text())
        y_max = _parse_optional_number(self.y_max.text())
        if x_min is not None and x_max is not None:
            cfg["x_range"] = [x_min, x_max]
        if y_min is not None and y_max is not None:
            cfg["y_range"] = [y_min, y_max]

        fig = build_graph(cfg, self.state.dataframe)
        capture_h = int(_parse_optional_number(self.capture_h.text()) or 1200)
        capture_w = int(_parse_optional_number(self.capture_w.text()) or 1600)
        capture_scale = int(_parse_optional_number(self.capture_scale.text()) or 2)

        self.preview.set_figure(
            fig,
            filename=cfg["title"],
            capture_h=capture_h,
            capture_w=capture_w,
            capture_scale=capture_scale,
        )

        self.local_graph = {
            **cfg,
            "captureheight": capture_h,
            "capturewidth": capture_w,
            "capturescale": capture_scale,
        }

    def save_local(self) -> None:
        if not self.local_graph:
            self.status.showMessage("No custom graph to save", 2500)
            return
        self.status.showMessage("Custom graph settings saved locally for this session", 2500)


class EditorTab(QWidget):
    def __init__(self, state: ApplicationState, status: QStatusBar) -> None:
        super().__init__()
        self.state = state
        self.status = status
        self.active_index = 0

        self.graph_list = QListWidget()
        self.add_btn = QPushButton("Add New Graph")
        self.delete_btn = QPushButton("Delete Graph")

        self.title_edit = QLineEdit()
        self.x_combo = QComboBox()
        self.y_list = QListWidget()
        self.y_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.hover_list = QListWidget()
        self.hover_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.filter_combo = QComboBox()
        self.baseline_combo = QComboBox()
        self.target_tab_combo = QComboBox()
        self.axis_mode_combo = QComboBox()
        self.axis_mode_combo.addItems(["single_axis", "dual_axis"])
        self.trace_mode_combo = QComboBox()
        self.trace_mode_combo.addItems(["markers", "lines+markers"])

        self.x_min = QLineEdit()
        self.x_max = QLineEdit()
        self.y_min = QLineEdit()
        self.y_max = QLineEdit()

        self.apply_btn = QPushButton("Apply locally")
        self.save_btn = QPushButton("Save to File")
        self.restore_btn = QPushButton("Restore from File")

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Configured Graphs"))
        left_layout.addWidget(self.graph_list)
        left_layout.addWidget(self.add_btn)
        left_layout.addWidget(self.delete_btn)

        form = QFormLayout()
        form.addRow("Title", self.title_edit)
        form.addRow("X", self.x_combo)
        form.addRow("Y (multi)", self.y_list)
        form.addRow("Hover data", self.hover_list)
        form.addRow("Filter", self.filter_combo)
        form.addRow("Baseline", self.baseline_combo)
        form.addRow("Target tab", self.target_tab_combo)
        form.addRow("Axis mode", self.axis_mode_combo)
        form.addRow("Trace mode", self.trace_mode_combo)
        form.addRow("X min", self.x_min)
        form.addRow("X max", self.x_max)
        form.addRow("Y min", self.y_min)
        form.addRow("Y max", self.y_max)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addLayout(form)
        right_layout.addWidget(self.apply_btn)
        right_layout.addWidget(self.save_btn)
        right_layout.addWidget(self.restore_btn)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([350, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.graph_list.currentRowChanged.connect(self._on_graph_selection_changed)
        self.add_btn.clicked.connect(self._on_add_graph)
        self.delete_btn.clicked.connect(self._on_delete_graph)
        self.apply_btn.clicked.connect(self._on_apply)
        self.save_btn.clicked.connect(self._on_save)
        self.restore_btn.clicked.connect(self._on_restore)
        self.axis_mode_combo.currentTextChanged.connect(self._enforce_dual_axis_limit)

    def reload(self) -> None:
        if not self.state.config:
            return

        cfg = self.state.config
        graphs = cfg.get("graphs", [])

        self.graph_list.blockSignals(True)
        self.graph_list.clear()
        for graph in graphs:
            title = graph.get("title") or f"{graph.get('y')} vs {graph.get('x')}"
            self.graph_list.addItem(str(title))
        self.graph_list.blockSignals(False)

        df_cols = self.state.dataframe.columns.tolist()

        self.x_combo.clear()
        self.y_list.clear()
        self.hover_list.clear()
        self.filter_combo.clear()
        self.baseline_combo.clear()
        self.target_tab_combo.clear()

        for col in df_cols:
            self.x_combo.addItem(col)
            self.y_list.addItem(QListWidgetItem(col))
            self.hover_list.addItem(QListWidgetItem(col))

        self.filter_combo.addItems(["Auto", "Perf", "Time", "linear"])
        for col in df_cols:
            if col not in {"Auto", "Perf", "Time", "linear"}:
                self.filter_combo.addItem(col)

        for baseline_name in cfg.get("baseline_options", ["ignore"]):
            self.baseline_combo.addItem(str(baseline_name))

        for tab_name in cfg.get("graph_tabs", ["Tab 1", "Tab 2"]):
            self.target_tab_combo.addItem(str(tab_name))

        if graphs:
            active = min(self.active_index, len(graphs) - 1)
            self.graph_list.setCurrentRow(active)
            self._load_graph(active)

    def _on_graph_selection_changed(self, row: int) -> None:
        if row < 0:
            return
        self.active_index = row
        self._load_graph(row)

    def _load_graph(self, index: int) -> None:
        if not self.state.config:
            return
        graphs = self.state.config.get("graphs", [])
        if index >= len(graphs):
            return

        graph = graphs[index]
        self.title_edit.setText(graph.get("title", ""))

        x_val = str(graph.get("x", ""))
        x_idx = self.x_combo.findText(x_val)
        if x_idx >= 0:
            self.x_combo.setCurrentIndex(x_idx)

        y_val = graph.get("y", [])
        y_values = y_val if isinstance(y_val, list) else [y_val]
        _set_selected_values(self.y_list, [str(y) for y in y_values])

        hover = graph.get("hover_data", [])
        _set_selected_values(self.hover_list, [str(h) for h in hover])

        filter_mode = graph.get("filter", "Auto")
        f_idx = self.filter_combo.findText(str(filter_mode))
        self.filter_combo.setCurrentIndex(max(0, f_idx))

        baseline_mode = graph.get("baseline", "ignore")
        b_idx = self.baseline_combo.findText(str(baseline_mode))
        self.baseline_combo.setCurrentIndex(max(0, b_idx))

        tab_name = graph.get("tab", "Tab 1")
        t_idx = self.target_tab_combo.findText(str(tab_name))
        self.target_tab_combo.setCurrentIndex(max(0, t_idx))

        axis_mode = graph.get("axis_mode", "dual_axis" if graph.get("dual_axis") else "single_axis")
        a_idx = self.axis_mode_combo.findText(str(axis_mode))
        self.axis_mode_combo.setCurrentIndex(max(0, a_idx))

        trace_mode = graph.get("trace_mode", "markers")
        m_idx = self.trace_mode_combo.findText(str(trace_mode))
        self.trace_mode_combo.setCurrentIndex(max(0, m_idx))

        x_range = graph.get("x_range") or ["", ""]
        y_range = graph.get("y_range") or ["", ""]
        self.x_min.setText(str(x_range[0]))
        self.x_max.setText(str(x_range[1]))
        self.y_min.setText(str(y_range[0]))
        self.y_max.setText(str(y_range[1]))

    def _enforce_dual_axis_limit(self) -> None:
        if self.axis_mode_combo.currentText() != "dual_axis":
            return
        selected = self.y_list.selectedItems()
        if len(selected) <= 2:
            return
        for item in selected[2:]:
            item.setSelected(False)

    def _on_add_graph(self) -> None:
        if not self.state.config:
            return
        graphs = self.state.config.setdefault("graphs", [])
        new_id = len(graphs)
        graphs.append(
            {
                "id": new_id,
                "x": "",
                "y": [],
                "hover_data": [],
                "baseline": "ignore",
                "tab": self.state.config.get("graph_tabs", ["Tab 1"])[0],
                "axis_mode": "single_axis",
                "dual_axis": False,
                "trace_mode": "markers",
            }
        )
        self.reload()
        self.graph_list.setCurrentRow(new_id)
        self.status.showMessage(f"Added Graph #{new_id + 1}", 2000)

    def _on_delete_graph(self) -> None:
        if not self.state.config:
            return
        graphs = self.state.config.get("graphs", [])
        row = self.graph_list.currentRow()
        if row < 0 or row >= len(graphs):
            return
        del graphs[row]
        for idx, graph in enumerate(graphs):
            graph["id"] = idx
        self.active_index = max(0, row - 1)
        self.reload()
        self.status.showMessage("Graph removed", 2000)

    def _on_apply(self) -> None:
        if not self.state.config:
            return
        graphs = self.state.config.get("graphs", [])
        row = self.graph_list.currentRow()
        if row < 0 or row >= len(graphs):
            return

        x_value = self.x_combo.currentText()
        y_values = _selected_values(self.y_list)
        if self.axis_mode_combo.currentText() == "dual_axis" and len(y_values) > 2:
            y_values = y_values[:2]

        if not x_value or not y_values:
            QMessageBox.warning(self, "Invalid graph", "X and at least one Y are required")
            return

        graph = graphs[row]
        title = self.title_edit.text().strip()
        if title:
            graph["title"] = title
        else:
            graph.pop("title", None)

        graph["x"] = x_value
        graph["y"] = y_values
        graph["hover_data"] = _selected_values(self.hover_list)

        filter_mode = self.filter_combo.currentText()
        if filter_mode and filter_mode != "Auto":
            graph["filter"] = filter_mode
        else:
            graph.pop("filter", None)

        graph["baseline"] = self.baseline_combo.currentText() or "ignore"
        graph["tab"] = self.target_tab_combo.currentText() or "Tab 1"
        graph["axis_mode"] = self.axis_mode_combo.currentText()
        graph["dual_axis"] = self.axis_mode_combo.currentText() == "dual_axis"
        graph["trace_mode"] = self.trace_mode_combo.currentText()

        x_min = _parse_optional_number(self.x_min.text())
        x_max = _parse_optional_number(self.x_max.text())
        y_min = _parse_optional_number(self.y_min.text())
        y_max = _parse_optional_number(self.y_max.text())
        if x_min is not None and x_max is not None:
            graph["x_range"] = [x_min, x_max]
        else:
            graph.pop("x_range", None)
        if y_min is not None and y_max is not None:
            graph["y_range"] = [y_min, y_max]
        else:
            graph.pop("y_range", None)

        self.status.showMessage(f"Saved Graph #{row + 1} locally", 2500)
        self.reload()

    def _on_save(self) -> None:
        if not self.state.config:
            return
        output = copy.deepcopy(self.state.config)
        for graph in output.get("graphs", []):
            graph.pop("id", None)

        config_path = os.path.join(functions.base_path, "config.json")
        with open(config_path, "w", encoding="utf-8") as target:
            json.dump(output, target, indent=2)

        self.status.showMessage("Configuration saved to file", 3000)

    def _on_restore(self) -> None:
        self.state.load()
        self.status.showMessage("Configuration restored from file", 3000)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CFM56-5B Trending Desktop")
        self.resize(1680, 980)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.state = ApplicationState()

        self.table_tab = TableTab(self.state, self.status)
        self.graphs_tab = GraphsTab(self.state)
        self.export_tab = ExportTab(self.state, self.status)
        self.editor_tab = EditorTab(self.state, self.status)

        tabs = QTabWidget()
        tabs.addTab(self.table_tab, "Table")
        tabs.addTab(self.graphs_tab, "Graphs")
        tabs.addTab(self.export_tab, "Export")
        tabs.addTab(self.editor_tab, "Configuration")
        self.setCentralWidget(tabs)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        reload_action = QAction("Reload Data", self)
        reload_action.triggered.connect(self.reload_data)
        toolbar.addAction(reload_action)

        refresh_graphs_action = QAction("Refresh Graphs", self)
        refresh_graphs_action.triggered.connect(self.graphs_tab.reload)
        toolbar.addAction(refresh_graphs_action)

        self.reload_data(initial=True)

    def reload_data(self, initial: bool = False) -> None:
        try:
            self.state.load()
            self._refresh_views()
            loaded_path = self.state.config.get("data_source", {}).get("file_path") if self.state.config else ""
            self.status.showMessage(f"Data loaded from {loaded_path}", 3500)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", f"Failed to load data: {exc}")
            if initial:
                raise

    def _refresh_views(self) -> None:
        self.table_tab.reload()
        self.graphs_tab.reload()
        self.export_tab.reload()
        self.editor_tab.reload()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
