# pyrefly: ignore [missing-import]
import numpy as np
import pandas as pd

def default_linear_baseline(df: pd.DataFrame, x_col: str, y_col: str, **kwargs) -> dict | None:
    """
    Calculates a linear baseline fit and standard deviation bounds.
    
    This is used to plot a trend line and bounds (shading/dashed lines) on the graphs.
    It fits a line to the 'Baseline' data points using linear regression (y = mx + c).
    
    Parameters:
    - df: The pandas DataFrame containing the data.
    - x_col: Name of the column for the X-axis.
    - y_col: Name of the column for the Y-axis.
    
    Returns:
    A dictionary containing:
    - 'x': X-coordinates for the trend lines.
    - 'y_trend': Y-coordinates for the center trend line.
    - 'y_upper': Y-coordinates for the +2 standard deviation upper bound.
    - 'y_lower': Y-coordinates for the -2 standard deviation lower bound.
    Returns None if there aren't enough data points (at least 2 required).
    """
    # 1. Filter dataset to find baseline points.
    # If the 'Category' column exists, we look for rows marked as 'Baseline'.
    if 'Category' in df.columns:
        baseline_df = df[df['Category'] == 'Baseline'].dropna(subset=[x_col, y_col])
    else:
        # Fallback: if there's no Category, assume the oldest 10 points (at the bottom/tail) are baseline.
        baseline_df = df.tail(10).dropna(subset=[x_col, y_col])
        
    # If we don't have enough baseline points at the tail, try the head (top 10 rows).
    if len(baseline_df) < 2:
        baseline_df = df.head(10).dropna(subset=[x_col, y_col])
        
    # If we still have fewer than 2 points, we cannot calculate a line (requires at least 2 points).
    if len(baseline_df) < 2:
        return None
        
    # Extract coordinate values as numpy arrays for mathematical calculation.
    x_base = baseline_df[x_col].values
    y_base = baseline_df[y_col].values
    
    # 2. Linear Regression Calculation
    # np.polyfit(X, Y, 1) fits a polynomial of degree 1 (a straight line: y = mx + c)
    # It returns: m (slope) and c (y-intercept)
    m, c = np.polyfit(x_base, y_base, 1)
    
    # 3. Standard Deviation of Residuals
    # Residuals are the vertical distance between the actual Y points and the predicted Y points (mx + c)
    predicted_y = (m * x_base) + c
    residuals = y_base - predicted_y
    std_dev = np.std(residuals)
    
    # 4. Generate Trend Line Points
    # Create 100 evenly spaced X-coordinates spanning the full range of the X dataset
    x_range = np.linspace(df[x_col].min(), df[x_col].max(), 100)
    
    # Compute the trendline and bounds (+/- 2 standard deviations) across this X-range
    y_trend = m * x_range + c
    
    return {
        'x': x_range,
        'y_trend': y_trend,
        'y_upper': y_trend + (2 * std_dev),
        'y_lower': y_trend - (2 * std_dev)
    }

def grouped_linear_baseline(df: pd.DataFrame, x_col: str, y_col: str, **kwargs) -> list[dict] | None:
    """
    Calculates separate linear baselines for each unique group in a specified column.
    
    By default, it looks for groups in the 'abc' column (can be overridden via baseline_kwargs).
    This function behaves like default_linear_baseline, but partitions the data first.
    """
    # Get the column used to group the data, defaulting to 'abc'
    group_col = kwargs.get('group_col', 'abc')
    
    # If the group column is not in the data, fallback to the single baseline calculation
    if group_col not in df.columns:
        val = default_linear_baseline(df, x_col, y_col, **kwargs)
        return [val] if val is not None else None
        
    baselines = []
    # Loop over every unique group value (e.g. different batches or product IDs)
    for group_name in df[group_col].unique():
        group_df = df[df[group_col] == group_name]
        
        # Take the oldest 10 points of this group as the baseline
        baseline_df = group_df.head(10).dropna(subset=[x_col, y_col])
        
        if len(baseline_df) < 2:
            continue
            
        x_base = baseline_df[x_col].values
        y_base = baseline_df[y_col].values
        
        try:
            # Linear Fit: y = mx + c
            m, c = np.polyfit(x_base, y_base, 1)
            
            # Standard Deviation of residuals
            residuals = y_base - (m * x_base + c)
            std_dev = np.std(residuals)
            
            # Generate trend line points
            x_range = np.linspace(df[x_col].min(), df[x_col].max(), 100)
            y_trend = m * x_range + c
            
            baselines.append({
                'group': group_name,
                'x': x_range,
                'y_trend': y_trend,
                'y_upper': y_trend + (2 * std_dev),
                'y_lower': y_trend - (2 * std_dev)
            })
        except Exception:
            # Ignore groups with math errors (e.g. vertical line, singular matrix)
            continue
            
    return baselines if baselines else None

# --- REGISTRY ---
# A mapping of baseline mode names to their corresponding function implementations.
# To add a custom baseline method:
# 1. Write your baseline function above.
# 2. Add it to this dictionary.
# 3. Refer to it by key in config.json's "baseline_mode" fields.
BASELINE_STRATEGIES = {
    'default_linear': default_linear_baseline,
    'grouped_linear': grouped_linear_baseline
}