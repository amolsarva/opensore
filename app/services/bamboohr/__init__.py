"""BambooHR HRIS API client for employee directory and org chart lookups."""

from __future__ import annotations

from app.services.bamboohr.client import BambooHRClient, make_bamboohr_client

__all__ = ["BambooHRClient", "make_bamboohr_client"]
