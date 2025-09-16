#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server using the official MCP SDK
"""
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from uuid import uuid4
import json

import mcp
from mcp.server import stdio
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize MCP
mcp = MCP("iCloud CalDAV MCP Server")

# Initialize CalDAV client
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# -----------------------
# MCP TOOLS
# -----------------------

@mcp.tool(description="Greet a user by name.")
def greet(name: str) -> str:
    logger.info(f"Called greet({name})")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

@mcp.tool(description="Check iCloud CalDAV connection.")
def get_connection_status() -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV"}
        calendars = caldav_client.get_calendars()
        return {
            "success": True,
            "status": "connected",
            "email": caldav_client.email,
            "calendars_found": len(calendars)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List iCloud calendars.")
def list_my_calendars() -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV"}
        calendars = caldav_client.get_calendars()
        return {"success": True, "calendars": calendars, "count": len(calendars)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List iCloud events.")
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV"}

        start_dt = ical_utils.parse_iso_datetime(start) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = ical_utils.parse_iso_datetime(end) or (datetime.now(timezone.utc) + timedelta(days=30))
        events = caldav_client.get_events(start_dt, end_dt, calendar_name)
        events.sort(key=lambda e: e.get("start") or "")
        if limit:
            events = events[:limit]
        return {"success": True, "events": events, "count": len(events)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="Create an iCloud event.")
def create_my_event(
    summary: str,
    start: str,
    end: str,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None
) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV"}
        cal = caldav_client.find_calendar(calendar_name)
        evt = IcsEvent()
        evt.add('uid', f"{uuid4()}@icloud")
        evt.add('summary', summary)
        evt.add('dtstamp', datetime.now(timezone.utc))
        if description:
            evt.add('description', description)
        if location:
            evt.add('location', location)
        evt.add('dtstart', ical_utils.parse_iso_datetime(start))
        evt.add('dtend', ical_utils.parse_iso_datetime(end))
        ics_cal = ical_utils.create_ics_calendar()
        ics_cal.add_component(evt)
        event_obj = cal.add_event(ics_cal.to_ical().decode('utf-8'))
        return {"success": True, "event_url": str(event_obj.url)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# -----------------------
# RUN SERVER
# -----------------------
if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting MCP server on {host}:{port}")
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
