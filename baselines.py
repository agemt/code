# Outputs a matrix of [x1, x2, y1, y2, id] for each line to be traced
#

def linear(df, bl, config, id, x_col, y_col):
    import numpy as np
    try:
        std_mod = 3
        
        xp = bl[x_col]
        yp = bl[y_col]
        
        slope, intercept = np.polyfit(xp, yp, deg=1)
        
        y_pred = slope * xp + intercept
        std = np.std(yp - y_pred, ddof=1)
        
        minxp = bl[x_col].min()
        maxxp = bl[x_col].max()
        
        y1 = slope * minxp + intercept
        y2 = slope * maxxp + intercept
        
        y1_up = y1 + (std_mod * std)
        y2_up = y2 + (std_mod * std)
        
        y1_low = y1 - (std_mod * std)
        y2_low = y2 - (std_mod * std)
        
        return np.array([
            [minxp, maxxp, y1, y2, 0],
            [minxp, maxxp, y1_up, y2_up, 1],
            [minxp, maxxp, y1_low, y2_low, 1],
        ])
    except Exception:
        return None

def ignore(df, bl, config, id, x_col, y_col):
    return None