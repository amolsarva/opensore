"""Zoom meeting records and participant data client."""

from __future__ import annotations

from app.services.zoom.client import ZoomClient, make_zoom_client

__all__ = ["ZoomClient", "make_zoom_client"]
