# Dummy baseline module. The actual implementation will be provided by the user later.

def linear(*args, **kwargs):
    # Returning empty list because app.py expects a lineset of rows like:
    # (x1, x2, y1, y2, lineid)
    return []

def ignore(*args, **kwargs):
    return []
