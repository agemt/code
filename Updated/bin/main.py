import sys
import os

# Add parent directory of bin to sys.path to resolve utils imports correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import datetime
import pandas as pd
import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, Slot, QModelIndex, QEvent, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTableView, QPushButton, QHeaderView, QMenu, QWidgetAction,
    QCheckBox, QLineEdit, QSplitter, QLabel, QFrame, QScrollArea,
    QSizePolicy, QMessageBox, QDialog, QComboBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QSpinBox, QGridLayout, QFormLayout,
    QDialogButtonBox, QListWidget, QProgressBar, QTextEdit, QRadioButton
)
from PySide6.QtGui import QColor, QBrush, QFont, QAction, QIcon, QCursor, QClipboard

import subprocess
import webbrowser
from utils.parser import (
    parse_raw_file, load_database, save_database, evaluate_formula_in_python
)

# ---------------------------------------------------------
# 1. Background Worker Thread for File Scanning
# ---------------------------------------------------------
class ScanWorker(QThread):
    progress = Signal(int, int, str, int) # current, total, filename, rows_found
    finished = Signal(list)                # list of parsed records
    error = Signal(str)

    def __init__(self, file_configs, params):
        super().__init__()
        self.file_configs = file_configs
        self.params = params

    def run(self):
        all_records = []
        total = len(self.file_configs)
        
        for idx, cfg in enumerate(self.file_configs):
            if self.isInterruptionRequested():
                break
            file_path = cfg["file_path"]
            filename = os.path.basename(file_path)
            try:
                records = parse_raw_file(
                    file_path=file_path,
                    params=self.params,
                    engine_row_1based=int(cfg["engine_row"]),
                    test_row_1based=int(cfg["test_row"]),
                    date_row_1based=int(cfg["date_row"]),
                    custom_engine_name=cfg["custom_name"] if pd.notna(cfg.get("custom_name")) else None,
                    operator_name=cfg["operator"]
                )
                all_records.extend(records)
                self.progress.emit(idx + 1, total, filename, len(records))
            except Exception as e:
                self.progress.emit(idx + 1, total, f"ERROR: {filename} - {str(e)}", 0)
                
        self.finished.emit(all_records)

# ---------------------------------------------------------
# 2. Scanning Progress Dialog
# ---------------------------------------------------------
class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scanning Raw Files...")
        self.resize(600, 350)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QLabel { color: #0f172a; font-weight: bold; }
            QProgressBar { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; text-align: center; color: #0f172a; }
            QProgressBar::chunk { background-color: #4752e8; }
            QTextEdit { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; font-family: monospace; font-size: 11px; }
            QPushButton { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #f1f5f9; }
        """)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel("Initializing scanner...", self)
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.log_area = QTextEdit(self)
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)
        
        self.btn_cancel = QPushButton("Cancel Scan", self)
        layout.addWidget(self.btn_cancel)

# ---------------------------------------------------------
# 3. Warning Alert Widget
# ---------------------------------------------------------
class WarningAlert(QFrame):
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.setObjectName("WarningAlert")
        self.setStyleSheet("""
            #WarningAlert {
                background-color: #fef9c3;
                border: 1px solid #fef08a;
                border-radius: 6px;
            }
            QLabel {
                color: #854d0e;
                font-weight: bold;
                background: transparent;
                font-size: 12px;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #854d0e;
                font-weight: bold;
                font-size: 13px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                color: #a16207;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        
        lbl = QLabel(message, self)
        layout.addWidget(lbl)
        
        layout.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.clicked.connect(self.close_and_delete)
        layout.addWidget(btn_close)
        
    def close_and_delete(self):
        self.setParent(None)
        self.deleteLater()

# ---------------------------------------------------------
# 4. Select File Dialog (Import Preview)
# ---------------------------------------------------------
class SelectFileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select File (Import Preview)")
        self.resize(800, 500)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QLabel { color: #0f172a; font-weight: bold; }
            QLineEdit, QSpinBox { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; }
            QTableWidget { background-color: #ffffff; border: 1px solid #cbd5e1; gridline-color: #e2e8f0; color: #0f172a; }
            QPushButton { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; padding: 6px 12px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #f1f5f9; }
        """)
        
        layout = QHBoxLayout(self)
        
        # Left Panel - Preview
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Raw File Preview"))
        
        self.preview_table = QTableWidget(15, 6)
        self.preview_table.setHorizontalHeaderLabels(["A", "B", "C", "D", "E", "F"])
        left_layout.addWidget(self.preview_table)
        
        layout.addLayout(left_layout, 3)
        
        # Right Panel - Parsing Settings
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Parsing Rules"))
        
        form = QFormLayout()
        
        self.engine_row = QSpinBox()
        self.engine_row.setValue(2)
        form.addRow("Engine Name Row:", self.engine_row)
        
        self.test_row = QSpinBox()
        self.test_row.setValue(3)
        form.addRow("Test/Keyword Row:", self.test_row)
        
        self.date_row = QSpinBox()
        self.date_row.setValue(4)
        form.addRow("Date Row:", self.date_row)
        
        self.custom_name = QLineEdit()
        self.custom_name.setPlaceholderText("Optional Name Override")
        form.addRow("Custom Engine Name:", self.custom_name)
        
        self.operator_name = QLineEdit()
        self.operator_name.setPlaceholderText("Enter your name (Required)")
        form.addRow("Added By (Operator):", self.operator_name)
        
        right_layout.addLayout(form)
        right_layout.addStretch()
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        right_layout.addWidget(self.buttons)
        
        layout.addLayout(right_layout, 2)

    def load_preview(self, file_path):
        import csv
        delimiter = ','
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                sample = f.read(1024)
                if '\t' in sample:
                    delimiter = '\t'
                elif ';' in sample:
                    delimiter = ';'
        except Exception:
            pass
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f, delimiter=delimiter)
                for r_idx, row in enumerate(reader):
                    if r_idx >= 15:
                        break
                    for c_idx, val in enumerate(row):
                        if c_idx >= 6:
                            break
                        self.preview_table.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))
        except Exception:
            pass

    def validate_and_accept(self):
        if not self.operator_name.text().strip():
            QMessageBox.warning(self, "Required Field", "Please enter your name in the 'Added By (Operator)' field.")
            return
        self.accept()

# ---------------------------------------------------------
# 4. Params Dialog
# ---------------------------------------------------------
class ParamsDialog(QDialog):
    def __init__(self, current_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Parameters / Equations")
        self.resize(600, 420)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QLabel { color: #0f172a; font-weight: bold; }
            QListWidget { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px; font-family: monospace; }
            QLineEdit { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; padding: 6px 12px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #f1f5f9; }
        """)
        
        layout = QHBoxLayout(self)
        
        # Left side - list of params
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Current Parameters & Equations"))
        
        self.list_widget = QListWidget(self)
        for p in current_params:
            self.list_widget.addItem(p)
        left_layout.addWidget(self.list_widget)
        
        btn_remove = QPushButton("Remove Selected Param")
        btn_remove.setStyleSheet("background-color: #ff5555; color: white; border: none;")
        btn_remove.clicked.connect(self.remove_param)
        left_layout.addWidget(btn_remove)
        
        layout.addLayout(left_layout, 3)
        
        # Right side - add param options
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Add Param / Equation"))
        
        self.new_param_edit = QLineEdit(self)
        self.new_param_edit.setPlaceholderText("e.g. W2K3 or FPR_calc=[@[FPR]]*1.01")
        right_layout.addWidget(self.new_param_edit)
        
        btn_add = QPushButton("Add New Variable")
        btn_add.clicked.connect(self.add_param)
        right_layout.addWidget(btn_add)
        
        right_layout.addStretch()
        
        # Recalculate options
        self.chk_recalc = QCheckBox("Recalculate database now", self)
        self.chk_recalc.setChecked(True)
        right_layout.addWidget(self.chk_recalc)
        
        # Dialog buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        right_layout.addWidget(self.buttons)
        
        layout.addLayout(right_layout, 2)

    def add_param(self):
        text = self.new_param_edit.text().strip()
        if text:
            self.list_widget.addItem(text)
            self.new_param_edit.clear()

    def remove_param(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                self.list_widget.takeItem(self.list_widget.row(item))

    def get_params(self):
        items = []
        for i in range(self.list_widget.count()):
            items.append(self.list_widget.item(i).text())
        return items

    def should_recalculate(self):
        return self.chk_recalc.isChecked()

# ---------------------------------------------------------
# 5. Main Application Window
# ---------------------------------------------------------
class EngineAnalysisApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Engine Test Data Analysis & Plotting Tool")
        self.setGeometry(100, 100, 1300, 850)
        
        # Directories
        self.config_dir = "config"
        self.data_dir = "data"
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.params_file = os.path.join(self.config_dir, "params.txt")
        self.db_file = os.path.join(self.data_dir, "database.xlsx")
        self.paths_file = os.path.join(self.config_dir, "paths.xlsx")
        
        # Ensure structures
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Loaded State
        self.config_data = {}
        self.params = []
        self.load_config_and_params()
        self.paths_df = self.load_paths_database()
        
        # Database dataframe
        self.df = load_database(self.db_file)
        
        # Setup Core Tabs Layout
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.setup_data_mgmt_tab()
        self.setup_dashboard_tab()
        
        self.tabs.addTab(self.data_mgmt_tab, "Data Management")
        self.tabs.addTab(self.dashboard_tab, "Dashboard Config")
        
        # Dashboard View Tab
        self.dashboard_view_tab = QWidget()
        dash_layout = QVBoxLayout(self.dashboard_view_tab)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add reload button
        dash_toolbar = QHBoxLayout()
        dash_toolbar.setContentsMargins(10, 10, 10, 10)
        
        btn_reload = QPushButton("⟳ Reload Dashboard Server")
        btn_reload.setStyleSheet("background-color: #2b2e38; color: #ffffff; padding: 10px; font-weight: bold; border-bottom: 1px solid #3d4250;")
        btn_reload.clicked.connect(lambda: self.launch_dashboard(silent=False))
        dash_toolbar.addWidget(btn_reload)
        
        btn_table = QPushButton("Table View")
        btn_table.setStyleSheet("background-color: #4752e8; color: #ffffff; padding: 10px; font-weight: bold;")
        btn_table.clicked.connect(lambda: self.web_view.setUrl(QUrl("http://127.0.0.1:8050/")))
        dash_toolbar.addWidget(btn_table)
        
        btn_graphs = QPushButton("Graphing View")
        btn_graphs.setStyleSheet("background-color: #4752e8; color: #ffffff; padding: 10px; font-weight: bold;")
        btn_graphs.clicked.connect(lambda: self.web_view.setUrl(QUrl("http://127.0.0.1:8050/graphs")))
        dash_toolbar.addWidget(btn_graphs)
        
        dash_toolbar.addStretch()
        
        dash_toolbar_widget = QWidget()
        dash_toolbar_widget.setLayout(dash_toolbar)
        dash_toolbar_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        dash_layout.addWidget(dash_toolbar_widget)
        
        self.web_view = QWebEngineView()
        dash_layout.addWidget(self.web_view, 1)
        
        self.tabs.addTab(self.dashboard_view_tab, "Dashboard View")
        
        # Apply theme stylesheet (light mode)
        self.apply_theme()
        
        self.dash_process = None
        
        # Launch dash subprocess silently
        self.launch_dashboard(silent=True)

    def load_config_and_params(self):
        # Read config.json
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
            except Exception:
                self.config_data = {}
        if not self.config_data:
            self.config_data = {
                "graphs": [],
                "locked_col": ["Engine"],
                "pinned_col": ["Engine", "Date_tested", "Perf. Point"],
                "imported_files": [],
                "layout_size": "Medium",
                "active_filters": {}
            }
        # Guarantee layout properties exist
        if "layout_size" not in self.config_data:
            self.config_data["layout_size"] = "Medium"
        if "active_filters" not in self.config_data:
            self.config_data["active_filters"] = {}
            
        # Read params.txt
        if os.path.exists(self.params_file):
            try:
                with open(self.params_file, 'r', encoding='utf-8') as f:
                    self.params = [line.strip() for line in f if line.strip()]
            except Exception:
                self.params = []
        else:
            self.params = ["W2K3", "FPR", "PO/PBAR_psia", "W2K3_calc==MAX([@[W2K3]];0)", "FPR_calc=[@[FPR]]*1.01"]
            with open(self.params_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.params))

    def save_config_and_params(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config_data, f, indent=2)
        with open(self.params_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(self.params))

    def load_paths_database(self):
        if os.path.exists(self.paths_file):
            try:
                df = pd.read_excel(self.paths_file)
                if not df.empty:
                    return df
            except Exception:
                pass
        return pd.DataFrame(columns=["file_path", "engine_row", "test_row", "date_row", "custom_name", "operator"])

    def save_paths_database(self):
        self.paths_df.to_excel(self.paths_file, index=False)

    def load_active_filters(self):
        active_filters = self.config_data.get("active_filters", {})
        full_df = self.table_model.get_full_dataframe()
        for col_name, allowed in active_filters.items():
            if col_name in full_df.columns:
                col_idx = list(full_df.columns).index(col_name)
                self.table_model._filters[col_idx] = allowed
        self.table_model.apply_filters()

    def on_table_model_changed(self):
        # Persist column filters
        active_filters = {}
        full_df = self.table_model.get_full_dataframe()
        for col_idx, allowed in self.table_model._filters.items():
            if col_idx < len(full_df.columns):
                col_name = full_df.columns[col_idx]
                active_filters[col_name] = allowed
        self.config_data["active_filters"] = active_filters
        self.save_config_and_params()
        
        # Update dynamic banner
        self.update_table_banner()
        
        # Update warnings
        self.update_warning_alerts()
        
        # Redraw

    def update_table_banner(self):
        count = len(self.table_model.get_dataframe()) # active filtered entries
        graphs = len(self.config_data.get("graphs", []))
        self.table_banner_label.setText(f"CFM56-5B Trending - {count} entries, {graphs} graphs")
        self.table_banner_label.setStyleSheet("font-size: 18px; color: #0f172a; font-weight: bold; margin-bottom: 5px;")

    def apply_layout_size(self, size_str, save_to_config=True):
        self.table_size_small.blockSignals(True)
        self.table_size_medium.blockSignals(True)
        self.table_size_large.blockSignals(True)
        self.graph_size_small.blockSignals(True)
        self.graph_size_medium.blockSignals(True)
        self.graph_size_large.blockSignals(True)
        
        self.table_size_small.setChecked(size_str == "Small")
        self.table_size_medium.setChecked(size_str == "Medium")
        self.table_size_large.setChecked(size_str == "Large")
        
        self.graph_size_small.setChecked(size_str == "Small")
        self.graph_size_medium.setChecked(size_str == "Medium")
        self.graph_size_large.setChecked(size_str == "Large")
        
        self.table_size_small.blockSignals(False)
        self.table_size_medium.blockSignals(False)
        self.table_size_large.blockSignals(False)
        self.graph_size_small.blockSignals(False)
        self.graph_size_medium.blockSignals(False)
        self.graph_size_large.blockSignals(False)
        
        if size_str == "Small":
            self.grid_columns = 3
            font_size = 9
            row_height = 20
        elif size_str == "Large":
            self.grid_columns = 1
            font_size = 13
            row_height = 34
        else: # Medium
            self.grid_columns = 2
            font_size = 11
            row_height = 26
            
        font = QFont("Inter", font_size)
        self.pinned_table.setFont(font)
        self.scroll_table.setFont(font)
        self.pinned_table.horizontalHeader().setFont(font)
        self.scroll_table.horizontalHeader().setFont(font)
        self.pinned_table.verticalHeader().setDefaultSectionSize(row_height)
        self.scroll_table.verticalHeader().setDefaultSectionSize(row_height)
        
        self.auto_fit_columns()
        self.sync_pinned_table_width()
        
        if save_to_config:
            self.config_data["layout_size"] = size_str
            self.save_config_and_params()
            

    def update_warning_alerts(self):
        self.df = self.table_model.get_full_dataframe()
        for i in reversed(range(self.alerts_layout.count())):
            item = self.alerts_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
                    
        missing_params = []
        for p in self.params:
            name = p.split("=", 1)[0] if "=" in p else p
            if name not in self.df.columns or self.df[name].isna().all():
                missing_params.append(name)
                
        if missing_params:
            for mp in missing_params:
                alert = WarningAlert(f"Could not find parameter ['{mp}']", self)
                self.alerts_layout.addWidget(alert)

    # ---------------------------------------------------------
    # TAB 1: Data Management Setup
    # ---------------------------------------------------------
    def setup_data_mgmt_tab(self):
        self.data_mgmt_tab = QWidget()
        layout = QHBoxLayout(self.data_mgmt_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Left Panel: PATHS Imported
        left_panel = QFrame()
        left_panel.setObjectName("Card")
        left_layout = QVBoxLayout(left_panel)
        
        header_left = QHBoxLayout()
        header_left.addWidget(QLabel("<h3>PATHS Imported</h3>"))
        header_left.addStretch()
        
        btn_add_file = QPushButton("+")
        btn_add_file.setToolTip("Import Raw File")
        btn_add_file.clicked.connect(self.import_file_flow)
        
        btn_recalc = QPushButton("G")
        btn_recalc.setToolTip("Re-scan All Files / Recalculate Database")
        btn_recalc.setStyleSheet("background-color: #00cc66; color: black; border: none; font-weight: bold;")
        btn_recalc.clicked.connect(self.recalculate_database_flow)
        
        header_left.addWidget(btn_add_file)
        header_left.addWidget(btn_recalc)
        left_layout.addLayout(header_left)
        
        self.files_table = QTableWidget()
        self.files_table.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; color: #0f172a;")
        self.files_table.setColumnCount(6)
        self.files_table.setHorizontalHeaderLabels(["File Path", "Engine Row", "Test Row", "Date Row", "Custom Name", "Added By"])
        left_layout.addWidget(self.files_table)
        self.refresh_files_table()
        
        layout.addWidget(left_panel, 1)
        
        # Right Panel: PARAMS / EQUATIONS
        right_panel = QFrame()
        right_panel.setObjectName("Card")
        right_layout = QVBoxLayout(right_panel)
        
        header_right = QHBoxLayout()
        header_right.addWidget(QLabel("<h3>PARAMS / EQUATIONS</h3>"))
        header_right.addStretch()
        
        btn_add_param = QPushButton("+")
        btn_add_param.setToolTip("Manage Variables / Formulas")
        btn_add_param.clicked.connect(self.manage_params_flow)
        header_right.addWidget(btn_add_param)
        
        right_layout.addLayout(header_right)
        
        self.params_list_view = QListWidget()
        self.params_list_view.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; font-family: monospace; color: #0f172a;")
        self.refresh_params_list_ui()
        right_layout.addWidget(self.params_list_view)
        
        layout.addWidget(right_panel, 1)

    def refresh_params_list_ui(self):
        self.params_list_view.clear()
        self.params_list_view.addItems(self.params)

    def refresh_files_table(self):
        self.files_table.setRowCount(0)
        for _, row in self.paths_df.iterrows():
            r = self.files_table.rowCount()
            self.files_table.insertRow(r)
            self.files_table.setItem(r, 0, QTableWidgetItem(str(row.get("file_path", ""))))
            self.files_table.setItem(r, 1, QTableWidgetItem(str(row.get("engine_row", ""))))
            self.files_table.setItem(r, 2, QTableWidgetItem(str(row.get("test_row", ""))))
            self.files_table.setItem(r, 3, QTableWidgetItem(str(row.get("date_row", ""))))
            self.files_table.setItem(r, 4, QTableWidgetItem(str(row.get("custom_name", "")) if pd.notna(row.get("custom_name")) else ""))
            self.files_table.setItem(r, 5, QTableWidgetItem(str(row.get("operator", ""))))
        self.files_table.resizeColumnsToContents()

    # File Importer flow
    def import_file_flow(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Raw Engine Test File", "", "Data Files (*.xls *.txt *.csv)")
        if not file_path:
            return
            
        dialog = SelectFileDialog(self)
        dialog.load_preview(file_path)
        
        if dialog.exec() == QDialog.Accepted:
            operator = dialog.operator_name.text().strip()
            engine_row = dialog.engine_row.value()
            test_row = dialog.test_row.value()
            date_row = dialog.date_row.value()
            custom_name = dialog.custom_name.text().strip() or None
            
            # Create file config
            file_configs = [{
                "file_path": file_path,
                "engine_row": engine_row,
                "test_row": test_row,
                "date_row": date_row,
                "custom_name": custom_name,
                "operator": operator
            }]
            
            # Start a single-file scan using worker thread for responsive feedback
            self.run_threaded_scan(
                file_configs=file_configs,
                append=True
            )

    # Re-scan All / Recalculate flow
    def recalculate_database_flow(self):
        if self.paths_df.empty:
            QMessageBox.warning(self, "No Files", "No raw files have been imported to re-scan.")
            return
            
        # Prompt for operator name (re-scanning operator)
        from PySide6.QtWidgets import QInputDialog
        operator, ok = QInputDialog.getText(self, "Operator Name", "Re-scanning Operator Name:")
        if not ok or not operator.strip():
            operator = "Re-scan Worker"
            
        file_configs = self.paths_df.to_dict('records')
        for cfg in file_configs:
            cfg["operator"] = operator.strip()
            if pd.isna(cfg.get("custom_name")):
                cfg["custom_name"] = None
                
        self.run_threaded_scan(
            file_configs=file_configs,
            append=False
        )

    def manage_params_flow(self):
        dialog = ParamsDialog(self.params, self)
        if dialog.exec() == QDialog.Accepted:
            self.params = dialog.get_params()
            self.save_config_and_params()
            self.refresh_params_list_ui()
            
            if dialog.should_recalculate():
                self.recalculate_database_flow()

    def run_threaded_scan(self, file_configs, append=True):
        self.progress_dlg = ProgressDialog(self)
        self.progress_dlg.progress_bar.setMaximum(len(file_configs))
        self.progress_dlg.progress_bar.setValue(0)
        
        # Cancel thread action
        self.worker = ScanWorker(file_configs, self.params)
        self.progress_dlg.btn_cancel.clicked.connect(self.worker.requestInterruption)
        
        self.worker.progress.connect(self.on_scan_progress)
        self.worker.finished.connect(lambda records: self.on_scan_finished(records, file_configs, append))
        
        self.worker.start()
        self.progress_dlg.exec()

    @Slot(int, int, str, int)
    def on_scan_progress(self, current, total, filename, rows_found):
        self.progress_dlg.progress_bar.setValue(current)
        self.progress_dlg.label.setText(f"Scanning file {current} of {total}...")
        self.progress_dlg.log_area.append(f"[{current}/{total}] Parsed {filename}: {rows_found} rows found.")

    def on_scan_finished(self, records, file_configs, append):
        self.progress_dlg.close()
        
        new_df = pd.DataFrame(records)
        if new_df.empty:
            QMessageBox.information(self, "Finished", "Scanner finished. No 'Takeoff' keyword columns found.")
            return
            
        if append:
            # Load current and append
            current_df = self.df
            # Drop duplicates if exactly matching Engine, Date, Perf Point
            combined_df = pd.concat([current_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=["Engine", "Date_tested", "Perf. Point"], keep='last')
        else:
            # Full rebuild
            combined_df = new_df
            
        # Ensure Date_tested formatting is clean
        if "Date_tested" in combined_df.columns:
            combined_df["Date_tested"] = pd.to_datetime(combined_df["Date_tested"], errors='coerce')
            combined_df["Date_tested"] = combined_df["Date_tested"].dt.date
            
        # Setup columns matching params
        columns = ["Engine", "Date_tested", "Perf. Point"]
        for p in self.params:
            name = p.split("=", 1)[0] if "=" in p else p
            if name not in columns:
                columns.append(name)
                
        # Fill missing columns with NaN
        for col in columns:
            if col not in combined_df.columns:
                combined_df[col] = np.nan
                
        # Keep only configured columns
        combined_df = combined_df[columns]
        
        # Sort by date
        combined_df = combined_df.sort_values("Date_tested").reset_index(drop=True)
        
        # Update paths.xlsx
        for cfg in file_configs:
            fp = cfg["file_path"]
            if not (self.paths_df["file_path"] == fp).any():
                self.paths_df = pd.concat([self.paths_df, pd.DataFrame([cfg])], ignore_index=True)
            else:
                idx = self.paths_df.index[self.paths_df["file_path"] == fp].tolist()[0]
                for k, v in cfg.items():
                    self.paths_df.at[idx, k] = v
        self.save_paths_database()
        
        self.refresh_files_table()
        
        # Update model
        self.df = combined_df
        
        # Save to database file immediately
        save_database(combined_df, self.db_file, self.params)
        
        QMessageBox.information(self, "Success", f"Scan complete. Total rows in database: {len(combined_df)}")

    # ---------------------------------------------------------
    # TAB 2: Table View Setup (AG Grid-like)
    # ---------------------------------------------------------
    def setup_table_view_tab(self):
        self.table_view_tab = QWidget()
        layout = QVBoxLayout(self.table_view_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Banner Label
        self.table_banner_label = QLabel()
        layout.addWidget(self.table_banner_label)
        
        # Header controls
        header = QHBoxLayout()
        
        # Quick Search Box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Quick Search across all columns...")
        self.search_box.setMinimumWidth(300)
        self.search_box.textChanged.connect(self.table_model.set_quick_search)
        header.addWidget(self.search_box)
        
        header.addStretch()
        
        # Auto-fit button
        btn_fit = QPushButton("Auto-size Columns")
        btn_fit.clicked.connect(self.auto_fit_columns)
        header.addWidget(btn_fit)
        
        # Save Button
        btn_save = QPushButton("Save to Excel")
        btn_save.setObjectName("AccentButton")
        btn_save.clicked.connect(self.save_table_edits)
        header.addWidget(btn_save)
        layout.addLayout(header)
        
        # Double Table Layout
        table_container = QWidget()
        table_container_layout = QHBoxLayout(table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        table_container_layout.setSpacing(0)
        
        self.pinned_table = QTableView()
        self.pinned_table.setModel(self.table_model)
        self.pinned_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pinned_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pinned_table.setSelectionBehavior(QTableView.SelectRows)
        self.pinned_table.setSelectionMode(QTableView.SingleSelection)
        
        self.scroll_table = QTableView()
        self.scroll_table.setModel(self.table_model)
        self.scroll_table.setSelectionBehavior(QTableView.SelectRows)
        self.scroll_table.setSelectionMode(QTableView.SingleSelection)

        # Configure columns hiding for split
        self.reconfigure_table_split()
            
        table_container_layout.addWidget(self.pinned_table, 0) # stretch=0
        table_container_layout.addWidget(self.scroll_table, 1) # stretch=1
        
        self.scroll_table.setSelectionModel(self.pinned_table.selectionModel())
        self.pinned_table.verticalScrollBar().valueChanged.connect(self.scroll_table.verticalScrollBar().setValue)
        self.scroll_table.verticalScrollBar().valueChanged.connect(self.pinned_table.verticalScrollBar().setValue)
        
        # Connect column resize signal to adjust pinned table container width dynamically
        self.pinned_table.horizontalHeader().sectionResized.connect(self.sync_pinned_table_width)
        
        layout.addWidget(table_container)
        
        self.pinned_table.horizontalHeader().sectionClicked.connect(self.show_header_filter)
        self.scroll_table.horizontalHeader().sectionClicked.connect(self.show_header_filter)
        
        # Enable Right-click Context Menu
        self.pinned_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scroll_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pinned_table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.scroll_table.customContextMenuRequested.connect(self.show_table_context_menu)
        
        # Layout Size Selector at the bottom of Table View
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Layout Size:"))
        
        self.table_size_small = QRadioButton("Small")
        self.table_size_medium = QRadioButton("Medium")
        self.table_size_large = QRadioButton("Large")
        
        size_layout.addWidget(self.table_size_small)
        size_layout.addWidget(self.table_size_medium)
        size_layout.addWidget(self.table_size_large)
        size_layout.addStretch()
        
        layout.addLayout(size_layout)
        
        # Warnings/Alerts Container
        self.alerts_container = QWidget()
        self.alerts_layout = QVBoxLayout(self.alerts_container)
        self.alerts_layout.setContentsMargins(0, 5, 0, 5)
        self.alerts_layout.setSpacing(5)
        layout.addWidget(self.alerts_container)
        
        # Connect size signals
        self.table_size_small.clicked.connect(lambda: self.apply_layout_size("Small"))
        self.table_size_medium.clicked.connect(lambda: self.apply_layout_size("Medium"))
        self.table_size_large.clicked.connect(lambda: self.apply_layout_size("Large"))
        
        # Initial width sync
        self.sync_pinned_table_width()

    def sync_pinned_table_width(self):
        width = 0
        for i in range(3):
            if not self.pinned_table.isColumnHidden(i):
                width += self.pinned_table.columnWidth(i)
        if self.pinned_table.verticalHeader().isVisible():
            width += self.pinned_table.verticalHeader().width()
        # Set fixed size
        self.pinned_table.setFixedWidth(width + 4)

    def reconfigure_table_split(self):
        # Refresh column layout splits dynamically based on model columns count
        cols = self.table_model.columnCount()
        for c in range(cols):
            self.pinned_table.setColumnHidden(c, False)
            self.scroll_table.setColumnHidden(c, False)
            
        # Hide columns 3+ in pinned
        for c in range(3, cols):
            self.pinned_table.setColumnHidden(c, True)
        # Hide columns 0, 1, 2 in scroll
        for c in range(0, 3):
            self.scroll_table.setColumnHidden(c, True)
            
        self.sync_pinned_table_width()

    def auto_fit_columns(self):
        self.pinned_table.resizeColumnsToContents()
        self.scroll_table.resizeColumnsToContents()
        self.sync_pinned_table_width()

    def save_table_edits(self):
        save_database(self.table_model.get_full_dataframe(), self.db_file, self.params)
        QMessageBox.information(self, "Save", "Changes successfully saved to database.xlsx. Calculated formulas updated in cells.")

    def show_table_context_menu(self, pos):
        # Build AG Grid-like right-click contextual actions
        sender = self.sender()
        index = sender.indexAt(pos)
        if not index.isValid():
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e2026; color: #ffffff; border: 1px solid #3d4250; }
            QMenu::item:selected { background-color: #4752e8; }
        """)
        
        copy_action = QAction("Copy Cell Text", self)
        copy_action.triggered.connect(lambda: self.copy_cell_to_clipboard(index))
        menu.addAction(copy_action)
        
        delete_action = QAction("Delete Selected Test/Row", self)
        delete_action.triggered.connect(lambda: self.delete_row_at_index(index.row()))
        menu.addAction(delete_action)
        
        menu.exec(sender.viewport().mapToGlobal(pos))

    def copy_cell_to_clipboard(self, index):
        val = self.table_model.data(index, Qt.DisplayRole)
        if val:
            QApplication.clipboard().setText(val)

    def delete_row_at_index(self, row):
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            "Are you sure you want to remove this engine test entry? This operation will be saved when you click 'Save to Excel'.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.table_model.remove_row(row)

    # ---------------------------------------------------------
    # TAB 3: Graphing View Setup (Grid Dashboard)
    # ---------------------------------------------------------
    def setup_graphing_view_tab(self):
        self.graphing_tab = QWidget()
        layout = QVBoxLayout(self.graphing_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Dashboard Controls Header
        controls = QHBoxLayout()
        controls.addWidget(QLabel("<h2>Graphing Dashboard</h2>"))
        controls.addStretch()
        
        controls.addWidget(QLabel("Layout Size:"))
        self.graph_size_small = QRadioButton("Small")
        self.graph_size_medium = QRadioButton("Medium")
        self.graph_size_large = QRadioButton("Large")
        
        controls.addWidget(self.graph_size_small)
        controls.addWidget(self.graph_size_medium)
        controls.addWidget(self.graph_size_large)
        
        layout.addLayout(controls)
        
        # Connect size signals
        self.graph_size_small.clicked.connect(lambda: self.apply_layout_size("Small"))
        self.graph_size_medium.clicked.connect(lambda: self.apply_layout_size("Medium"))
        self.graph_size_large.clicked.connect(lambda: self.apply_layout_size("Large"))
        
        # Sub Tabs: Trending | Historical | Configuration
        self.graph_sub_tabs = QTabWidget()
        layout.addWidget(self.graph_sub_tabs)
        
        self.setup_trending_tab()
        self.setup_historical_tab()
        self.setup_config_tab()
        
        self.graph_sub_tabs.addTab(self.trending_scroll, "Trending")
        self.graph_sub_tabs.addTab(self.historical_scroll, "Historical")
        self.graph_sub_tabs.addTab(self.graph_config_tab, "Configuration")

    def setup_trending_tab(self):
        self.trending_scroll = QScrollArea()
        self.trending_scroll.setWidgetResizable(True)
        self.trending_scroll.setStyleSheet("QScrollArea { border: none; background-color: #121318; }")
        
        self.trending_widget = QWidget()
        self.trending_grid = QGridLayout(self.trending_widget)
        self.trending_grid.setSpacing(15)
        self.trending_scroll.setWidget(self.trending_widget)

    def setup_historical_tab(self):
        self.historical_scroll = QScrollArea()
        self.historical_scroll.setWidgetResizable(True)
        self.historical_scroll.setStyleSheet("QScrollArea { border: none; background-color: #121318; }")
        
        self.historical_widget = QWidget()
        self.historical_grid = QGridLayout(self.historical_widget)
        self.historical_scroll.setWidget(self.historical_widget)

    def setup_dashboard_tab(self):
        self.dashboard_tab = QWidget()
        layout = QHBoxLayout(self.dashboard_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Left Panel - Launch Dashboard
        launch_panel = QFrame()
        launch_panel.setObjectName("Card")
        launch_layout = QVBoxLayout(launch_panel)
        launch_layout.addWidget(QLabel("<h3>Web Dashboard</h3>"))
        
        lbl_info = QLabel("The table and graph views have been migrated to an interactive Dash web application.\nIt is embedded in the 'Dashboard View' tab.")
        lbl_info.setWordWrap(True)
        launch_layout.addWidget(lbl_info)
        
        # Button moved to Dashboard View tab
        launch_layout.addStretch()
        layout.addWidget(launch_panel, 1)
        
        # Center Panel - Graphs List
        list_panel = QFrame()
        list_panel.setObjectName("Card")
        list_layout = QVBoxLayout(list_panel)
        list_layout.addWidget(QLabel("<h3>Graphs List</h3>"))
        
        self.config_graphs_list = QListWidget()
        self.config_graphs_list.currentRowChanged.connect(self.load_selected_graph_to_editor)
        list_layout.addWidget(self.config_graphs_list)
        
        btn_lay_left = QHBoxLayout()
        btn_add = QPushButton("Add Graph")
        btn_add.clicked.connect(self.add_graph_config)
        btn_delete = QPushButton("Delete Selected")
        btn_delete.setStyleSheet("background-color: #ff5555; border: none;")
        btn_delete.clicked.connect(self.delete_graph_config)
        btn_lay_left.addWidget(btn_add)
        btn_lay_left.addWidget(btn_delete)
        list_layout.addLayout(btn_lay_left)
        
        layout.addWidget(list_panel, 1)
        
        # Center Panel - Config Form panel
        form_panel = QFrame()
        form_panel.setObjectName("Card")
        form_layout = QVBoxLayout(form_panel)
        form_layout.addWidget(QLabel("<h3>Edit Selected Graph Configuration</h3>"))
        
        form = QFormLayout()
        
        self.cfg_title = QLineEdit()
        form.addRow("Graph Title:", self.cfg_title)
        
        self.cfg_x = QComboBox()
        self.cfg_x.addItems(["W2K3", "FPR", "PO/PBAR_psia", "W2K3_calc", "FPR_calc", "Date_tested"])
        form.addRow("X Parameter Column:", self.cfg_x)
        
        self.cfg_y = QComboBox()
        self.cfg_y.addItems(["W2K3", "FPR", "PO/PBAR_psia", "W2K3_calc", "FPR_calc"])
        form.addRow("Y Parameter Column:", self.cfg_y)
        
        self.cfg_x_min = QLineEdit()
        self.cfg_x_max = QLineEdit()
        self.cfg_x_min.setPlaceholderText("Min (auto)")
        self.cfg_x_max.setPlaceholderText("Max (auto)")
        range_lay_x = QHBoxLayout()
        range_lay_x.addWidget(self.cfg_x_min)
        range_lay_x.addWidget(self.cfg_x_max)
        form.addRow("X Range limits:", range_lay_x)
        
        self.cfg_y_min = QLineEdit()
        self.cfg_y_max = QLineEdit()
        self.cfg_y_min.setPlaceholderText("Min (auto)")
        self.cfg_y_max.setPlaceholderText("Max (auto)")
        range_lay_y = QHBoxLayout()
        range_lay_y.addWidget(self.cfg_y_min)
        range_lay_y.addWidget(self.cfg_y_max)
        form.addRow("Y Range limits:", range_lay_y)
        
        self.cfg_baseline = QComboBox()
        self.cfg_baseline.addItems(["linear", "ignore"])
        form.addRow("Baseline regression:", self.cfg_baseline)
        
        form_layout.addLayout(form)
        form_layout.addStretch()
        
        btn_save = QPushButton("Save / Apply Changes")
        btn_save.setObjectName("AccentButton")
        btn_save.clicked.connect(self.save_graph_config)
        form_layout.addWidget(btn_save)
        
        layout.addWidget(form_panel, 2)
        
        # Right Panel - Raw Preview
        preview_panel = QFrame()
        preview_panel.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("<h3>Active config.json Preview</h3>"))
        
        self.json_preview = QLabel()
        self.json_preview.setStyleSheet("color: #abb2bf; font-family: monospace; font-size: 11px;")
        preview_layout.addWidget(self.json_preview)
        
        layout.addWidget(preview_panel, 1)
        
        # Populate list and preview
        self.populate_config_graphs_list()
        self.update_json_preview()
        
        # Select first graph by default
        if len(self.config_data.get("graphs", [])) > 0:
            self.config_graphs_list.setCurrentRow(0)

    def populate_config_graphs_list(self):
        self.config_graphs_list.blockSignals(True)
        self.config_graphs_list.clear()
        for g in self.config_data.get("graphs", []):
            title = g.get("title", f"{g.get('y')} vs {g.get('x')}")
            self.config_graphs_list.addItem(f"[{g.get('id')}] {title}")
        self.config_graphs_list.blockSignals(False)

    def load_selected_graph_to_editor(self, row_idx):
        if row_idx < 0 or row_idx >= len(self.config_data.get("graphs", [])):
            return
        g = self.config_data["graphs"][row_idx]
        self.cfg_title.setText(g.get("title", ""))
        self.cfg_x.setCurrentText(g.get("x", "W2K3"))
        self.cfg_y.setCurrentText(g.get("y", "FPR"))
        self.cfg_baseline.setCurrentText(g.get("baseline", "linear"))
        
        # range limits
        x_range = g.get("x_range", [])
        self.cfg_x_min.setText(str(x_range[0]) if len(x_range) == 2 else "")
        self.cfg_x_max.setText(str(x_range[1]) if len(x_range) == 2 else "")
        
        y_range = g.get("y_range", [])
        self.cfg_y_min.setText(str(y_range[0]) if len(y_range) == 2 else "")
        self.cfg_y_max.setText(str(y_range[1]) if len(y_range) == 2 else "")

    def update_json_preview(self):
        self.json_preview.setText(json.dumps({"graphs": self.config_data.get("graphs", [])}, indent=2)[:650] + "\n...")

    def change_grid_columns(self, idx):
        self.grid_columns = idx + 1

    def refresh_graphs(self):
        def clear_grid(grid, canvas_list):
            for cv in canvas_list:
                grid.removeWidget(cv)
                # Find toolbar wrapper
                wrapper = cv.parentWidget()
                if wrapper:
                    wrapper.setParent(None)
            canvas_list.clear()
            
        clear_grid(self.trending_grid, self.trending_canvases)
        clear_grid(self.historical_grid, self.historical_canvases)
        
        trend_count = 0
        hist_count = 0
        
        selected_rows = self.pinned_table.selectionModel().selectedRows()
        row = selected_rows[0].row() if selected_rows else None
        
        filtered_df = self.table_model.get_dataframe()
        
        # Build grids
        for g_cfg in self.config_data.get("graphs", []):
            canvas_wrapper = QWidget()
            canvas_lay = QVBoxLayout(canvas_wrapper)
            canvas_lay.setContentsMargins(0, 0, 0, 0)
            canvas_lay.setSpacing(2)
            
            canvas = MplCanvas(self)
            canvas.plot_data(filtered_df, g_cfg, highlighted_row=row)
            canvas.point_clicked.connect(self.graph_point_selected)
            
            # Embed Matplotlib interactive controls (Sleek minimalist bar)
            from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
            toolbar = NavigationToolbar2QT(canvas, self)
            toolbar.setMaximumHeight(30)
            toolbar.setStyleSheet("background-color: #f1f5f9; border: none; color: #0f172a;")
            
            canvas_lay.addWidget(toolbar)
            canvas_lay.addWidget(canvas)
            
            x_col = g_cfg.get("x")
            if x_col == "Date_tested":
                # Historical layout
                r = hist_count // self.grid_columns
                c = hist_count % self.grid_columns
                self.historical_grid.addWidget(canvas_wrapper, r, c)
                self.historical_canvases.append(canvas)
                hist_count += 1
            else:
                # Trending layout
                r = trend_count // self.grid_columns
                c = trend_count % self.grid_columns
                self.trending_grid.addWidget(canvas_wrapper, r, c)
                self.trending_canvases.append(canvas)
                trend_count += 1

    def add_graph_config(self):
        new_id = str(max([int(g.get("id", 0)) for g in self.config_data.get("graphs", [])] + [0]) + 1)
        new_g = {
            "id": new_id,
            "title": f"Custom Graph {new_id}",
            "x": "W2K3",
            "y": "FPR",
            "hover_data": ["Engine", "Date_tested", "Perf. Point"],
            "baseline": "linear"
        }
        self.config_data["graphs"].append(new_g)
        self.save_config_and_params()
        self.update_json_preview()
        self.populate_config_graphs_list()
        self.config_graphs_list.setCurrentRow(len(self.config_data["graphs"]) - 1)
        QMessageBox.information(self, "Added", f"Added graph template {new_id}. Customize it in the form editor.")

    def delete_graph_config(self):
        row_idx = self.config_graphs_list.currentRow()
        if row_idx < 0 or row_idx >= len(self.config_data.get("graphs", [])):
            QMessageBox.warning(self, "No Selection", "Please select a graph from the list to delete.")
            return
            
        g = self.config_data["graphs"][row_idx]
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to remove the graph config '{g.get('title')}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.config_data["graphs"].pop(row_idx)
            self.save_config_and_params()
            self.update_json_preview()
            self.populate_config_graphs_list()
                
            # Select first or empty forms
            if len(self.config_data.get("graphs", [])) > 0:
                self.config_graphs_list.setCurrentRow(0)
            else:
                self.cfg_title.clear()
                self.cfg_x_min.clear()
                self.cfg_x_max.clear()
                self.cfg_y_min.clear()
                self.cfg_y_max.clear()

    def save_graph_config(self):
        row_idx = self.config_graphs_list.currentRow()
        if row_idx < 0 or row_idx >= len(self.config_data.get("graphs", [])):
            QMessageBox.warning(self, "No Selection", "Please select a graph from the list to edit.")
            return
            
        active_g = self.config_data["graphs"][row_idx]
        active_g["title"] = self.cfg_title.text() or active_g["title"]
        active_g["x"] = self.cfg_x.currentText()
        active_g["y"] = self.cfg_y.currentText()
        active_g["baseline"] = self.cfg_baseline.currentText()
        
        # Ranges
        x_min = self.cfg_x_min.text().strip()
        x_max = self.cfg_x_max.text().strip()
        if x_min and x_max:
            try:
                active_g["x_range"] = [float(x_min), float(x_max)]
            except ValueError:
                pass
        else:
            active_g.pop("x_range", None)
            
        y_min = self.cfg_y_min.text().strip()
        y_max = self.cfg_y_max.text().strip()
        if y_min and y_max:
            try:
                active_g["y_range"] = [float(y_min), float(y_max)]
            except ValueError:
                pass
        else:
            active_g.pop("y_range", None)
            
        self.save_config_and_params()
        self.update_json_preview()
        self.populate_config_graphs_list()
        self.config_graphs_list.setCurrentRow(row_idx)
        QMessageBox.information(self, "Saved", f"Graph configuration saved successfully.")



    # ---------------------------------------------------------
    # UI Styling
    # ---------------------------------------------------------
    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f8fafc; }
            QWidget { color: #0f172a; font-family: "Inter", "Outfit", sans-serif; font-size: 13px; }
            #Card { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }
            QLabel { color: #0f172a; }
            QTabWidget::pane { border: 1px solid #cbd5e1; background-color: #ffffff; border-radius: 4px; }
            QTabBar::tab { background: #f1f5f9; border: 1px solid #cbd5e1; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; color: #64748b; margin-right: 2px; }
            QTabBar::tab:selected { background: #ffffff; color: #0f172a; border-bottom: 2px solid #4752e8; }
            QTableView { background-color: #ffffff; border: 1px solid #cbd5e1; gridline-color: #e2e8f0; selection-background-color: rgba(71, 82, 232, 0.1); selection-color: #0f172a; }
            QTableView::item { padding: 6px; border-bottom: 1px solid #e2e8f0; }
            QTableView::item:selected { background-color: rgba(71, 82, 232, 0.15); color: #0f172a; }
            QHeaderView::section { background-color: #f1f5f9; color: #475569; padding: 6px; font-weight: bold; border: 1px solid #cbd5e1; }
            QPushButton { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #f1f5f9; }
            #AccentButton { background-color: #4752e8; border: none; color: #ffffff; }
            #AccentButton:hover { background-color: #3b46db; }
            QComboBox, QLineEdit { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px; color: #0f172a; }
            QComboBox QAbstractItemView { background-color: #ffffff; color: #0f172a; selection-background-color: rgba(71, 82, 232, 0.1); border: 1px solid #cbd5e1; }
            QScrollBar:vertical { border: none; background: #f1f5f9; width: 8px; margin: 0px; }
            QScrollBar::handle:vertical { background: #cbd5e1; min-height: 20px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #4752e8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; }
            QRadioButton { spacing: 6px; color: #0f172a; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QToolTip { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; }
        """)

    def launch_dashboard(self, silent=True):
        import sys
        if self.dash_process is None or self.dash_process.poll() is not None:
            dash_script = os.path.join(os.path.dirname(__file__), "dash_app.py")
            # Use the venv python if available, else sys.executable
            venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "python.exe"))
            python_exe = venv_python if os.path.exists(venv_python) else sys.executable
            self.dash_process = subprocess.Popen([python_exe, dash_script])
        
        self.web_view.setUrl(QUrl("http://127.0.0.1:8050"))
        
        if not silent:
            self.tabs.setCurrentWidget(self.dashboard_view_tab)

# ---------------------------------------------------------
# Launch main application
# ---------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font = QFont("Inter", 10)
    app.setFont(font)
    
    window = EngineAnalysisApp()
    window.show()
    
    sys.exit(app.exec())

    def closeEvent(self, event):
        self.save_config_and_params()
        if self.dash_process and self.dash_process.poll() is None:
            self.dash_process.terminate()
        super().closeEvent(event)
