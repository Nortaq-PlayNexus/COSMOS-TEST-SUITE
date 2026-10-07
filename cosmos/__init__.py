"""
COSMOS TEST SUITE

An Independent Computational Observatory for Testing the Biggest Questions
in Cosmology and Fundamental Physics.

Core principle: DO NOT TRY TO PROVE A THEORY. Try to find out whether the data
can disprove it.
"""

from __future__ import annotations

from . import config, database, statistics, simulations
from .config import settings
from .database import SessionLocal, get_db

__version__ = "0.1.0.dev0"
__author__ = "COSMOS"
__license__ = "GPL-3.0-only"

__all__ = [
    "SessionLocal",
    "__author__",
    "__license__",
    "__version__",
    "config",
    "database",
    "get_db",
    "settings",
    "simulations",
    "statistics",
]
