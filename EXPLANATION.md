# The Exhaustive Guide to Recreating the Data Correlation Dashboard

This document provides a microscopic breakdown of the Data Correlation Dashboard. It explains the "why" and "how" behind every mathematical operation, library choice, and architectural decision. By reading this, you will understand exactly how to write this application from a blank text file.

---

## Part 1: The Core Technologies

Before writing code, you need to understand the tools:
1. **Python**: The programming language driving the logic.
2. **Pandas**: A data manipulation library used to read Excel files and organize data into tables (DataFrames).
3. **NumPy**: A numerical computing library used for advanced math (linear regression, standard deviation).
4. **Plotly**: A graphing library used to draw the scatter plots and trendlines.
5. **Dash**: A web framework that takes Plotly graphs and HTML components and serves them as an interactive website.
6. **Dash AG-Grid**: A highly advanced data table component for Dash, allowing user filtering and sorting.

---

## Part 2: The Math Engine (`baselines.py`)

This file is isolated from the web server. Its sole job is to take raw numbers and return the mathematical coordinates needed to draw trendlines and boundaries.

### 1. The `default_linear_baseline` Function
This function takes the "Baseline" subset of your data and calculates a line of best fit, along with upper and lower boundaries.

**Step 1: Filtering the Data**
```python
if 'Category' in df.columns:
    baseline_df = df[df['Category'] == 'Baseline'].dropna(subset=[x_col, y_col])
```
We look at the Pandas DataFrame (`df`). We filter it to only keep rows where the `Category` column equals `"Baseline"`. The `.dropna(subset=[x_col, y_col])` part ensures we throw away any rows that have missing (NaN) values in our X or Y columns, as math cannot be performed on missing data.

**Step 2: Extracting NumPy Arrays**
```python
x_base = baseline_df[x_col].values
y_base = baseline_df[y_col].values
```
`.values` strips away the Pandas table formatting and gives us raw, pure lists of numbers (NumPy arrays). This is required for the math functions.

**Step 3: Linear Regression (The Line of Best Fit)**
```python
m, c = np.polyfit(x_base, y_base, 1)
```
`np.polyfit` fits a polynomial equation to our data points. The `1` means a 1st-degree polynomial, which is a straight line. The mathematical equation for a straight line is **$y = mx + c$**.
- **$m$**: The slope (how steep the line is).
- **$c$**: The y-intercept (where the line crosses the vertical axis).
`polyfit` calculates the optimal $m$ and $c$ to minimize the distance between the line and all our data points.

**Step 4: Standard Deviation (The Boundaries)**
```python
predicted_y = (m * x_base) + c
residuals = y_base - predicted_y
std_dev = np.std(residuals)
```
We want to draw a shaded boundary around our trendline to show normal variance.
1. We calculate `predicted_y` by plugging our actual $x$ values into our new $y = mx + c$ equation.
2. We calculate `residuals`. A residual is the vertical distance between the *actual* data point and the *predicted* point on the line. 
3. `np.std(residuals)` calculates the Standard Deviation ($\sigma$) of these distances. It tells us the average amount by which points deviate from the trendline.

**Step 5: Generating the Coordinates for Plotly**
```python
x_range = np.linspace(df[x_col].min(), df[x_col].max(), 100)
y_trend = m * x_range + c
```
We need to tell Plotly *where* to draw the line. `np.linspace` generates 100 perfectly evenly-spaced X coordinates between the absolute minimum and maximum X values in our entire dataset. We then calculate the `y_trend` for these 100 points.

We return the center line (`y_trend`), the upper boundary (`y_trend + 2 * std_dev`), and the lower boundary (`y_trend - 2 * std_dev`). Mathematically, $\pm 2\sigma$ covers ~95% of normal variance.

### 2. The Registry Pattern
```python
BASELINE_STRATEGIES = {
    'default_linear': default_linear_baseline,
    'grouped_linear': grouped_linear_baseline
}
```
Why do this? In `config.json`, the user types `"baseline_mode": "default_linear"`. Python needs a way to translate that text string into an actual function call. This dictionary serves as a lookup table.

---

## Part 3: Styling the Dashboard (`assets/style.css`)

Dash automatically detects any folder named `assets` in your project directory and serves the CSS files inside it to the browser.

### CSS Variables
```css
:root {
    --bg-color: #f4f6f9;
    --card-bg: #ffffff;
}
```
We define colors as variables in `:root`. This allows us to use `var(--bg-color)` later. If we ever want to build a dark mode, we just change the variables in `:root` and the whole site updates.

### The CSS Grid
```css
.graph-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px;
}
```
This is the modern way to align items. `repeat(3, minmax(0, 1fr))` means "create exactly 3 columns. Each column should take up 1 fraction (`1fr`) of the available space, but never shrink below 0". 

### The Override Class
```css
.graph-card.maximized {
    grid-column: 1 / -1;
    height: 80vh;
}
```
When a graph is maximized, we use Python to inject the class `.maximized` into the HTML element. `grid-column: 1 / -1` is a CSS Grid trick that tells the element to stretch from the very first grid line to the very last grid line, effectively forcing it to take up the entire width of the screen. `80vh` means 80% of the Viewport Height.

---

## Part 4: The Main Application (`app.py`)

This file ties the math, the CSS, and the UI together.

### 1. Data Processing and Setup
**`load_config(path)`**: Uses Python's built-in `json.load()` to parse the `config.json` text file into a Python Dictionary.

**`hex_to_rgba(hex_color, alpha)`**: Plotly requires colors to be in `rgba(red, green, blue, alpha)` format to draw transparent shapes (like the boundary shading). This function takes a string like `"#FF0000"`, strips the `#`, splits it into 2-character chunks, and converts them from Base-16 (Hexadecimal) to Base-10 integers using `int(chunk, 16)`.

**`load_data(config)`**: Uses `pd.read_excel()` to load the data into memory. We loop through the columns and forcefully round all numbers (`np.number`) to 3 decimal places using `df.round(3)` so our data table looks clean. We also assign default string categories (`'First'`, `'Recent'`, `'Baseline'`, `'Regular'`) based on the row's index position so we can color-code the scatter points.

**`build_column_defs(df, table_config)`**: AG-Grid requires a "Column Definition" dictionary for every column it displays. We loop over `df.columns`. If a column is listed in the `locked_pinned_columns` config, we add `'pinned': 'left'` and `'lockPinned': True` to its dictionary. This tells the Javascript AG-Grid library to freeze that column on the left side of the screen.

### 2. Building the Plotly Figure (`build_graph_figure`)
This function creates the actual chart.
```python
fig = go.Figure()
```
`go.Figure()` creates an empty canvas.

**Adding Boundaries and Trendlines**
We retrieve the coordinates generated by `baselines.py`.
To draw the boundaries, we add two `go.Scatter` traces:
1. The **Lower Bound**: We draw an invisible line (`mode='none'`) along the bottom edge.
2. The **Upper Bound**: We draw another invisible line along the top edge, but we add `fill='tonexty'` and `fillcolor=rgba(...)`. Plotly will mathematically fill the area between this trace and the *previously drawn trace* (the lower bound) with color.

**Adding Scatter Points**
```python
for category, group in df.groupby('Category', sort=False):
```
Instead of drawing one giant scatter plot, we group the DataFrame by Category. We add a separate `go.Scatter(mode='markers')` trace for each category. This allows us to assign different colors and shapes to the 'Baseline' points vs the 'Recent' points.

**Highlighting Active Rows (`selectedpoints`)**
If the user filters the data table, `active_ids` is passed into this function. We calculate the integer indices of the active IDs. By passing `selectedpoints=[1, 4, 5]`, Plotly knows to keep those points fully opaque. We define `unselected={'marker': {'opacity': 0.2}}`, which tells Plotly to automatically fade all *other* points to 20% opacity.

**Layout Overrides**
- `uirevision: graph_config['id']`: This is a magic Plotly property. Normally, when you update a graph with new data, Plotly resets the user's zoom and pan. By setting `uirevision` to a constant string, we tell Plotly "preserve the user's camera state even when the data inside the graph changes."
- `plot_bgcolor` & `paper_bgcolor`: Set to `'#ffffff'` (solid white). This makes sure the plot has a clean, solid background when downloaded/exported as an image (preventing transparent backgrounds that are hard to read on dark image viewers), while blending seamlessly with the white `.graph-card` in the web application UI.
- Title and Margin Spacing: The title is positioned with `yref='container'`, `y=1`, `yanchor='top'`, and `pad={'t': 15}` (giving it a fixed 15px top margin). The plot margin top `t` is set to `75` pixels. Because both boundaries are defined in absolute pixels, they never scale or stretch proportionally when the graph is maximized to `80vh`, maintaining a neat, compact spacing layout in both views.

### 3. The Dash Architecture
```python
app = Dash(__name__)
app.layout = html.Div([ ... components ... ])
```
A Dash app is a tree of Python objects (`html.Div`, `dcc.Graph`) that Dash compiles into raw HTML/React.js code and serves to the browser.

**Customizing Graph Download Settings (`config`)**
In `build_graph_cards`, we instantiate the `dcc.Graph` components with custom export settings in the `config` dictionary:
- `displaylogo: False`: Hides the default Plotly logo.
- `modeBarButtonsToRemove`: Disables the lasso and rectangle select tools to prevent UI clutter.
- `toImageButtonOptions`: Configures the behavior of the "Download plot as a png" camera button:
  - `format: 'png'`: Exports the graph as a PNG image.
  - `filename`: Names the file dynamically after the graph title.
  - `width: 1920` and `height: 1080`: Defines the target dimensions.
  - `scale: 2`: Multiplies the output resolution of all elements (text labels, points, lines) by `2`, producing a super-sharp **3840x2160** (4K resolution) final image.

### 4. Interactivity: The Callbacks
Callbacks are functions wrapped in the `@app.callback` decorator. Dash listens to the browser. When an `Input` changes, Dash sends the new data to the Python function, runs the function, and pushes the `Output` back to the browser.

**Pattern Matching Callbacks (`ALL`)**
Normally, an Input looks like `Input('my-button', 'n_clicks')`. But our graphs are generated dynamically from a config file; we don't know how many buttons there are!
We assign IDs as dictionaries: `id={'type': 'max-btn', 'index': 'graph-1'}`.
By writing `Input({'type': 'max-btn', 'index': ALL}, 'n_clicks')`, Dash will trigger the callback if *any* component with the type `'max-btn'` is clicked.

**Callback 1: `update_max_states`**
* **Goal**: Keep track of which graph is maximized.
* **Mechanism**: 
  1. We check `dash.callback_context.triggered_id`. This tells us exactly *which* dictionary ID triggered the callback (e.g., the button for `'graph-2'`).
  2. We read `clicked_id = triggered_id.get('index')`.
  3. We return a boolean list. If the index matches `clicked_id`, we flip its state (`not state`). All other graphs are forced to `False`.

**Callback 2: `apply_maximize_state`**
* **Goal**: Apply CSS to resize the graph.
* **Mechanism**: It takes the boolean list generated above. For `True` items, it returns the string `'graph-card maximized'`. For `False` items, it returns `'graph-card'`. Dash injects these strings directly into the HTML `class="..."` attribute, triggering the CSS Grid rules we defined earlier.

**Callback 3: `sync_graphs`**
* **Goal**: Dim points on the graph when they are filtered out of the AG-Grid data table.
* **Mechanism**: 
  1. The AG-Grid component exposes a property called `virtualRowData`. This contains the data currently visible on the screen after the user types in a filter box.
  2. Dash triggers this callback whenever `virtualRowData` changes.
  3. We extract the `'id'` of every visible row into a list (`active_ids`).
  4. We loop over every graph configuration, call `build_graph_figure(df, graph, config, active_ids)`, and return the brand-new Plotly figures. Dash seamlessly swaps them in the browser.

### 5. Running the Application
```python
if __name__ == '__main__':
    app.run(debug=True)
```
This starts the Flask web server. `debug=True` enables Hot-Reloading, meaning if you edit `app.py` or `style.css` and save the file, the browser will automatically refresh instantly.
