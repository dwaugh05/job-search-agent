"""Live job-feed adapters.

Every adapter here talks to a real ATS API at scan time and returns canonical
Posting objects. Nothing in this package may read from a cached search index --
hitting the live feed IS the liveness check.
"""

from .registry import ADAPTERS, fetch_company, probe

__all__ = ["ADAPTERS", "fetch_company", "probe"]
