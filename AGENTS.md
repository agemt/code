# AI Agent Instructions for Graph Dashboard

## Project Overview
- This repository contains a Dash-based data correlation dashboard.
- `app.py` builds an interactive web app using `dash`, `dash_ag_grid`, `plotly`, `pandas`, and `numpy`.
- `config.json` defines the dashboard behavior, including graph definitions, table pinning, category styles, and baseline regression settings.

## Key Files
- `app.py` - main application logic, layout, and callbacks.
- `config.json` - runtime configuration for graph panels and styling.
- `requirements.txt` - Python dependencies required to run the project.

## How to Run
- Install dependencies from `requirements.txt`.
- Run the app with:
  - `python app.py`
- The app starts a Dash server in debug mode.

## Important Conventions
- `config.json` is required and loaded at startup.
- Graph definitions in `config.json` should include `id`, `x`, `y`, `title`, and optionally `hover_data`, `x_range`, and `y_range`.
- `app.py` expects `table_config`, `category_styles`, and `baseline_config` sections in `config.json`.
- The DataFrame in `app.py` has an `id` string and `Category` columns used for selection, styling, and baseline regression.

## Agent Guidance
- Prefer updating `config.json` for dashboard changes such as adding graphs, customizing styles, or altering table pinning.
- For functional changes, modify `app.py` only when the behavior cannot be represented through `config.json`.
- Preserve the interactive patterns in `app.py`:
  - graph click updates table selection,
  - selected graph points sync to `selected-data-store`,
  - table row changes update graphs.
- Avoid removing or renaming the `id` or `Category` fields in the DataFrame, since they are used for selection and trace matching.

## Config Schema Notes
- `graphs`: an array of graph configuration objects.
- `table_config`: contains `locked_pinned_columns` and `default_pinned_columns`.
- `category_styles`: maps category names to marker styling values.
- `baseline_config`: controls whether a center regression line is shown and the style of limit lines.

## When in Doubt
- If you need more structure, update `AGENTS.md` rather than embedding large documentation in the code.
- Keep changes minimal and aligned with the existing Dash callback architecture.
