import numpy as np
import pandas as pd

def linear_oldest_engines(df, x_col, y_col, date_col="Date_tested", engine_col="Engine", n_engines=20):
    """
    Fits a linear regression line on records belonging to the N oldest unique engines.
    1. Drops rows where x_col or y_col is N/A.
    2. Identifies the oldest n_engines based on their earliest date_col.
    3. Gathers all records for these engines.
    4. Computes linear fit Y = m*X + c and standard deviation of residuals.
    """
    # Filter N/As
    clean_df = df.dropna(subset=[x_col, y_col]).copy()
    if clean_df.empty:
        return None
        
    # Get unique engines and their earliest test dates
    engine_dates = clean_df.groupby(engine_col)[date_col].min().reset_index()
    engine_dates = engine_dates.sort_values(date_col)
    
    oldest_engines = engine_dates[engine_col].head(n_engines).tolist()
    if not oldest_engines:
        return None
        
    # Subset records
    baseline_subset = clean_df[clean_df[engine_col].isin(oldest_engines)]
    if len(baseline_subset) < 3:
        # Fallback to all clean data if subset is too small
        baseline_subset = clean_df
        
    X_base = pd.to_numeric(baseline_subset[x_col]).values
    Y_base = pd.to_numeric(baseline_subset[y_col]).values
    
    try:
        m, c = np.polyfit(X_base, Y_base, 1)
        Y_pred = m * X_base + c
        residuals = Y_base - Y_pred
        sigma = np.std(residuals)
        
        # Calculate evaluation limits
        X_all = pd.to_numeric(clean_df[x_col]).values
        X_fit = np.linspace(float(np.min(X_all)), float(np.max(X_all)), 100)
        Y_fit = m * X_fit + c
        
        return {
            "x_fit": X_fit,
            "y_fit": Y_fit,
            "sigma": sigma,
            "m": m,
            "c": c
        }
    except Exception:
        return None

# Registry of available baseline algorithms
BASELINE_ALGORITHMS = {
    "linear": linear_oldest_engines,
    "ignore": lambda *args, **kwargs: None
}
