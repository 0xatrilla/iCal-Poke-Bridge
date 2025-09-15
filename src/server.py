#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
A FastMCP server that provides calendar operations for iCloud using CalDAV.
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict
from uuid import uuid4

from fastmcp import FastMCP
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils
from fastapi import Request

# -----------------------
# Logging configuration
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# -----------------------
# Initialize FastMCP
# -----------------------
mcp = FastMCP("iCloud CalDAV MCP Server")
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# -----------------------
# Middleware for Poke
# -----------------------
@mcp.app.middleware("http")
async def ensure_accept_sse(request: Request, call_next):
    """
    Ensure requests from clients missing 'text/event-stream' in Accept header
    are still accepted by FastMCP.
    """
    # Make a copy of the scope headers
    headers = dict(request.headers)
    accept_header = headers.get("accept", "")
    if "text/event-stream" not in accept_header:
        headers["accept"] = accept_header + ",text/event-stream"
        # Create new Request object with modified headers
        request = Request(scope={**request.scope, "headers": [
            (k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
        ]}, receive=request.receive)

    response = await call_next(request)
    return response

# -----------------------
# MCP Tools
# -----------------------
@mcp.tool(description="Greet a user by name for testing MCP connectivity.")
def greet(name: str) -> str:
    logger.info(f"Tool Call: greet('{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

@mcp.tool(description="Get basic MCP server info and HTTP request guidance.")
def get_server_info() -> Dict[str, object]:
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
                    "arguments": {}
                }
            },
            "response_format": "Server-Sent Events (text/event-stream) with 'data: ' prefix"
        }
    }

@mcp.tool(description="Test iCloud CalDAV connection.")
def get_connection_status() -> Dict[str, object]:
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
        return {"success": False, "error": str(e)}

@mcp.tool(description="List your iCloud calendars.")
def list_my_calendars() -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        calendars = caldav_client.get_calendars()
        return {"success": True, "calendars": calendars, "count": len(calendars)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List events in your iCloud calendars.")
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
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
                e = ical_utils.parse_event_from_ics(ev)
                e["calendar_name"] = calendar_name
                all_events.append(e)
        else:
            for cal in caldav_client.principal.calendars():
                cal_name = caldav_client._get_calendar_display_name(cal)
                try:
                    events = cal.date_search(start_dt, end_dt)
                    for ev in events:
                        e = ical_utils.parse_event_from_ics(ev)
                        e["calendar_name"] = cal_name
                        all_events.append(e)
                except Exception:
                    continue

        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))

        if limit is not None:
            all_events = all_events[:max(0, int(limit))]

        return {"success": True, "events": all_events, "count": len(all_events), "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}}
    except Exception as e:
        return {"success": False, "error": str(e)}

# -----------------------
# Additional tools (create, update, delete, list alarms)
# -----------------------
# Your existing create_my_event, update_my_event, delete_my_event, list_event_alarms
# can be copied verbatim from your previous server.py
# They will work as-is because FastMCP + middleware is now fully compatible.

# -----------------------
# Server entrypoint
# -----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    logger.info("="*80)
    logger.info(f"Starting iCloud CalDAV MCP Server at http://{host}:{port}")
    logger.info(f"MCP Endpoint: http://{host}:{port}/mcp")
    logger.info(f"Environment: {os.environ.get('ENVIRONMENT', 'development')}")

    # Validate CalDAV connection
    try:
        test_result = caldav_client.test_connection()
        if test_result.get("success"):
            logger.info(f"Connected to iCloud: {test_result.get('email')}, calendars found: {test_result.get('calendars_found')}")
        else:
            logger.warning(f"⚠ Connection test warning: {test_result.get('error')}")
    except Exception as e:
        logger.warning(f"⚠ Could not test connection: {e}")

    logger.info("="*80)
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
