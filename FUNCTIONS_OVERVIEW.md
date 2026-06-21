# Current function overview

## Core data helpers

- `get_data(count=False)`
  - Reads `config.json` from the project root.
  - Loads the configured Excel sheet.
  - Converts the configured date column into a sortable datetime field.
  - Adds `Full_date`, `Time`, and `sequential_id` columns.
  - Populates `config["baseline_options"]` from the baseline strategy module.

- `build_graph(graph, dfa, activeIDs=None)`
  - Builds a Plotly figure for one graph definition.
  - Uses `graph["x"]` / `graph["y"]` to plot scatter points.
  - Supports hover columns, axis ranges, and active-row highlighting.
  - Calls the configured baseline strategy to draw helper lines.

- `build_card(config, graphs, dfa, active_ids=None)`
  - Wraps each graph in a Dash Mantine card.
  - Uses export settings from the config for image capture.

- `build_grid(config, records)`
  - Converts records into an Ag-Grid table.
  - Applies pinned/locked columns from config.
  - Formats numeric cells for display.

## Page-specific callbacks

- `pages/editor.py`
  - Renders the graph configuration editor.
  - Lets the user change titles, axes, hover data, ranges, and baseline settings.
  - Applies local edits in memory and can save them back to `config.json`.

- `pages/graph.py`
  - Displays the configured graph cards.
  - Refreshes graph figures when selections change.

- `pages/table.py`
  - Shows the loaded dataset in a grid.
  - Caches visible row IDs for cross-page filtering.

## Baseline strategies

- `baselines.py`
  - `linear(...)` computes a regression line and bounds.
  - `ignore(...)` returns no baseline.

## Expected config shape

The restored config now uses the keys consumed by the app:

- `date_col`
- `data_source.file_path`
- `data_source.sheet_name`
- `locked_col`
- `pinned_col`
- `captureheight`, `capturewidth`, `capturescale`
- `graphs[]` entries with `x`, `y`, `title`, `hover_data`, `filter`, `baseline`, `x_range`, and `y_range`
