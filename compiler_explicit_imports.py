"""Explicit import surface for freeze/compile tools.

This module is imported at startup so packaging tools can statically detect
Dash core components, Dash add-ons, and Flask backend dependencies.
"""

import dash  # noqa: F401
import dash_ag_grid  # noqa: F401
import dash_bootstrap_components  # noqa: F401
import dash_mantine_components  # noqa: F401
from dash import (  # noqa: F401
    ALL,
    MATCH,
    Dash,
    Input,
    Output,
    Patch,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    page_container,
    page_registry,
)
from flask import Flask, Response, jsonify, request, send_file  # noqa: F401

__all__ = [
    "ALL",
    "MATCH",
    "Dash",
    "Input",
    "Output",
    "Patch",
    "State",
    "callback",
    "clientside_callback",
    "ctx",
    "dcc",
    "html",
    "no_update",
    "page_container",
    "page_registry",
    "Flask",
    "Response",
    "jsonify",
    "request",
    "send_file",
]
