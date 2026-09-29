"""pimlint — validador de feeds de produto por canal.

Uso rápido:
    python -m pimlint produtos.csv --channel amazon
    python -m pimlint produtos.csv --channel shopify --format json
"""

from .report import render_report
from .schema import Attribute, ChannelSchema, Severity, load_schemas
from .validator import (
    Finding,
    LineReport,
    ValidationReport,
    validate_file,
    validate_row,
)

__all__ = [
    "Attribute",
    "ChannelSchema",
    "Finding",
    "LineReport",
    "Severity",
    "ValidationReport",
    "load_schemas",
    "render_report",
    "validate_file",
    "validate_row",
]

__version__ = "0.1.0"
