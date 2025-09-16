#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
A FastMCP server that provides calendar operations for iCloud using CalDAV.
Fully compatible with MCP SDK v2+ and Render deployments.
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict, List
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp import Tool

from icalendar import Calendar as IcsCalendar, Event as IcsEvent
from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# ==============================
# Logging configuration
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==============================
# Initialize clients
# ==============================
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# ==============================
# Tool registration
# ==============================
tools: List[Tool] = []

def tool(func=None, *, description=""):
    """Decorator to register tools with required inputSchema for MCP SDK v2+"""
    def decorator(f):
        params = f.__annotations__
        if not params:
            input_schema = {"type": "object", "properties": {}}
        else:
            props = {}
            for k, v in params.items():
                props[k] = {"type": "string"}  # default to string
            input_schema = {"type": "object", "properties": props, "required": list(props.keys())}
        tools.append(
            Tool(
                name=f.__name__,
                func=f,
                description=description,
                inputSchema=input_schema
            )
        )
        return f
    if func:
        return decorator(func)
    return decorator

# ==============================
# MCP Tools
# ==============================

@tool(description="Greet a user by name with a welcome message.")
def greet(name: str) -> str:
    logger.info(f"🔧 TOOL CALL: greet(name='{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

@tool(description="Get server info and HTTP request guidance.")
def get_server_info() -> Dict[str, object]:
    logger.info("🔧 TOOL CALL: get_server_info()")
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": sys.version.split()[0],
        "note": "All MCP tools require JSON-RPC 2.0 format."
    }

@tool(description="Test iCloud CalDAV connection status.")
def get_connection_status() -> Dict[str, object]:
    logger.info("🔧 TOOL CALL: get_connection_status()")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        calendars = caldav_client.get_calendars()
        return {
            "success": True,
            "status": "connected",
            "email": caldav_client.email,
            "calendars_found": len(calendars),
            "server_url": "https://caldav.icloud.com"
        }
    except Exception as e:
        logger.error(f"❌ get_connection_status failed: {e}")
        return {"success": False, "error": str(e)}

@tool(description="List iCloud calendars.")
def list_my_calendars() -> Dict[str, object]:
    logger.info("🔧 TOOL CALL: list_my_calendars()")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        calendars = caldav_client.get_calendars()
        return {"success": True, "calendars": calendars, "count": len(calendars)}
    except Exception as e:
        logger.error(f"❌ list_my_calendars failed: {e}")
        return {"success": False, "error": str(e)}

@tool(description="List events from iCloud calendars.")
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[str] = None
) -> Dict[str, object]:
    logger.info(f"🔧 TOOL CALL: list_my_events(calendar_name='{calendar_name}', start='{start}', end='{end}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}

        start_dt = ical_utils.parse_iso_datetime(start, timezone_name) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name) or (datetime.now(timezone.utc) + timedelta(days=30))
        all_events = []

        if calendar_name:
            cal = caldav_client.find_calendar(calendar_name=calendar_name)
            events = cal.date_search(start_dt, end_dt)
            for ev in events:
                event_data = ical_utils.parse_event_from_ics(ev)
                event_data["calendar_name"] = calendar_name
                all_events.append(event_data)
        else:
            calendars = caldav_client.principal.calendars()
            for cal in calendars:
                cal_name = caldav_client._get_calendar_display_name(cal)
                try:
                    events = cal.date_search(start_dt, end_dt)
                    for ev in events:
                        event_data = ical_utils.parse_event_from_ics(ev)
                        event_data["calendar_name"] = cal_name
                        all_events.append(event_data)
                except Exception as e:
                    logger.warning(f"Failed to search calendar '{cal_name}': {e}")
                    continue

        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit:
            all_events = all_events[:max(0, int(limit))]

        return {"success": True, "events": all_events, "count": len(all_events),
                "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}}
    except Exception as e:
        logger.error(f"❌ list_my_events failed: {e}")
        return {"success": False, "error": str(e)}

@tool(description="Create an event in iCloud calendar.")
def create_my_event(
    summary: str,
    start: str,
    end: str,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    all_day: Optional[str] = None,
    timezone_name: Optional[str] = None,
    rrule: Optional[str] = None,
    alarm_minutes_before: Optional[str] = None,
    alarm_configs: Optional[str] = None
) -> Dict[str, object]:
    logger.info(f"🔧 TOOL CALL: create_my_event(summary='{summary}', start='{start}', end='{end}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}

        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        start_dt = ical_utils.parse_iso_datetime(start, timezone_name)
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name)
        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        evt.add('summary', summary)
        evt.add('dtstamp', datetime.now(timezone.utc))
        if description: evt.add('description', description)
        if location: evt.add('location', location)
        if all_day == "true":
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            evt.add('dtstart', start_date)
            evt.add('dtend', end_date)
        else:
            evt.add('dtstart', start_dt)
            evt.add('dtend', end_dt)
        if rrule: evt.add('rrule', rrule)
        ics_cal.add_component(evt)
        try:
            ics_cal.add_missing_timezones()
        except Exception:
            pass
        ics_text = ics_cal.to_ical().decode('utf-8')
        created = cal.add_event(ics_text)
        event_url = str(getattr(created, 'url', None)) if created else None
        return {"success": True, "event_url": event_url or "", "summary": summary, "start": start, "end": end}
    except Exception as e:
        logger.error(f"❌ create_my_event failed: {e}")
        return {"success": False, "error": str(e)}

# ==============================
# START MCP SERVER
# ==============================
if __name__ == "__main__":
    server = FastMCP(name="iCloud CalDAV MCP Server", tools=tools)
    server.run()
