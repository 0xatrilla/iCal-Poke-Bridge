#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
Using the official MCP SDK for Python (https://pypi.org/project/mcp/)
"""
import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict
from uuid import uuid4

from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from mcp.server import http  # Correct MCP SDK import
from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# ==========================
# Logging configuration
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==========================
# CalDAV client setup
# ==========================
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# ==========================
# MCP Tools
# ==========================

def greet(name: str) -> str:
    """Simple greeting tool."""
    logger.info(f"Tool call: greet(name='{name}')")
    return f"Hello, {name}! Welcome to iCloud CalDAV MCP."

def get_server_info() -> dict:
    """Return basic server info."""
    logger.info("Tool call: get_server_info()")
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": sys.version.split()[0],
        "http_request_format": {
            "method": "POST",
            "endpoint": "/mcp",
            "required_headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            "json_body_format": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "tool_name_here",
                    "arguments": {"param1": "value1"}
                }
            }
        }
    }

def get_connection_status() -> Dict[str, object]:
    """Check connection to iCloud CalDAV."""
    logger.info("Tool call: get_connection_status()")
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
        logger.error(f"get_connection_status failed: {e}")
        return {"success": False, "error": str(e)}

def list_my_calendars() -> Dict[str, object]:
    """List iCloud calendars."""
    logger.info("Tool call: list_my_calendars()")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        
        calendars = caldav_client.get_calendars()
        return {"success": True, "calendars": calendars, "count": len(calendars)}
    except Exception as e:
        logger.error(f"list_my_calendars failed: {e}")
        return {"success": False, "error": str(e)}

def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
    """List events from iCloud calendars."""
    logger.info(f"Tool call: list_my_events(calendar_name='{calendar_name}', start='{start}', end='{end}')")
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
                data = ical_utils.parse_event_from_ics(ev)
                data["calendar_name"] = calendar_name
                all_events.append(data)
        else:
            for cal in caldav_client.principal.calendars():
                cal_name = caldav_client._get_calendar_display_name(cal)
                try:
                    events = cal.date_search(start_dt, end_dt)
                    for ev in events:
                        data = ical_utils.parse_event_from_ics(ev)
                        data["calendar_name"] = cal_name
                        all_events.append(data)
                except Exception as e:
                    logger.warning(f"Failed to search calendar '{cal_name}': {e}")
        
        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]
        
        return {"success": True, "events": all_events, "count": len(all_events),
                "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}}
    except Exception as e:
        logger.error(f"list_my_events failed: {e}")
        return {"success": False, "error": str(e)}

# Additional tools (create/update/delete events, alarms) would be added here following the same pattern.

# ==========================
# MCP Tools Registry
# ==========================
tools = {
    "greet": greet,
    "get_server_info": get_server_info,
    "get_connection_status": get_connection_status,
    "list_my_calendars": list_my_calendars,
    "list_my_events": list_my_events,
    # Add create_my_event, update_my_event, delete_my_event, list_event_alarms here
}

# ==========================
# Start MCP HTTP server
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    logger.info("🚀 Starting iCloud CalDAV MCP Server")
    logger.info(f"🚀 Server URL: http://{host}:{port}")
    logger.info(f"🚀 MCP Endpoint: http://{host}:{port}/mcp")

    http.http_server(tools, host=host, port=port)
