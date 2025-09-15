#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server (FastMCP native)
All tools are stateless HTTP compatible for Poke.
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from uuid import uuid4
from typing import Optional, Dict

from fastmcp import FastMCP
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("iCloudMCP")

# -------------------------
# Initialize MCP
# -------------------------
mcp = FastMCP("iCloud CalDAV MCP Server")

# CalDAV client
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# -------------------------
# Tools
# -------------------------

@mcp.tool(description="Greet user to verify server connectivity.")
def greet(name: str) -> str:
    logger.info(f"🔧 TOOL CALL: greet({name})")
    return f"Hello, {name}! MCP server is running."

@mcp.tool(description="Get MCP server info and environment.")
def get_server_info() -> dict:
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
            }
        }
    }

@mcp.tool(description="Test iCloud CalDAV connection.")
def get_connection_status() -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}
        calendars = caldav_client.get_calendars()
        return {
            "success": True,
            "email": caldav_client.email,
            "calendars_found": len(calendars)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List your iCloud calendars.")
def list_my_calendars() -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}
        calendars = caldav_client.get_calendars()
        return {"success": True, "count": len(calendars), "calendars": calendars}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List events from your iCloud calendars.")
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}

        start_dt = ical_utils.parse_iso_datetime(start) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = ical_utils.parse_iso_datetime(end) or (datetime.now(timezone.utc) + timedelta(days=30))

        all_events = []

        if calendar_name:
            cal = caldav_client.find_calendar(calendar_name)
            events = cal.date_search(start_dt, end_dt)
            for ev in events:
                data = ical_utils.parse_event_from_ics(ev)
                data["calendar_name"] = calendar_name
                all_events.append(data)
        else:
            calendars = caldav_client.principal.calendars()
            for cal in calendars:
                cal_name = caldav_client._get_calendar_display_name(cal)
                try:
                    events = cal.date_search(start_dt, end_dt)
                    for ev in events:
                        data = ical_utils.parse_event_from_ics(ev)
                        data["calendar_name"] = cal_name
                        all_events.append(data)
                except Exception:
                    continue

        all_events.sort(key=lambda e: e.get("start") or "")
        if limit:
            all_events = all_events[:limit]

        return {"success": True, "count": len(all_events), "events": all_events}

    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="Create an event in iCloud calendar.")
def create_my_event(
    summary: str,
    start: str,
    end: str,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    all_day: bool = False
) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}

        cal = caldav_client.find_calendar(calendar_name)
        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add("uid", f"{uuid4()}@icloud-mcp")
        evt.add("summary", summary)
        evt.add("dtstamp", datetime.now(timezone.utc))
        if description:
            evt.add("description", description)
        if location:
            evt.add("location", location)

        if all_day:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            evt.add("dtstart", start_date)
            evt.add("dtend", end_date)
        else:
            evt.add("dtstart", ical_utils.parse_iso_datetime(start))
            evt.add("dtend", ical_utils.parse_iso_datetime(end))

        ics_cal.add_component(evt)
        created = cal.add_event(ics_cal.to_ical().decode("utf-8"))
        return {"success": True, "event_url": str(getattr(created, "url", ""))}

    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="Delete an event by its CalDAV URL.")
def delete_my_event(event_url: str) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}
        import caldav
        ev = caldav.Event(client=caldav_client.client, url=event_url)
        ev.delete()
        return {"success": True, "event_url": event_url}
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool(description="List alarms (VALARMs) for an event by URL or UID.")
def list_event_alarms(event_url: Optional[str] = None, uid: Optional[str] = None,
                      calendar_name: Optional[str] = None) -> Dict[str, object]:
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Cannot connect to CalDAV"}
        if not event_url and not uid:
            return {"success": False, "error": "Provide either event_url or uid"}
        cal = caldav_client.find_calendar(calendar_name)
        event_obj = caldav_client.get_event_by_url_or_uid(cal, event_url, uid)
        cal_ics = IcsCalendar.from_ical(ical_utils.get_event_ics_bytes(event_obj))

        alarms = []
        for comp in cal_ics.walk("valarm"):
            trigger = comp.get("trigger")
            minutes_before = None
            if trigger is not None:
                try:
                    from datetime import timedelta
                    value = getattr(trigger, "dt", trigger)
                    if isinstance(value, timedelta):
                        minutes_before = int(abs(value.total_seconds()) // 60)
                except Exception:
                    pass
            alarms.append({
                "uid": str(comp.get("uid")),
                "x_wr_alarmuid": str(comp.get("X-WR-ALARMUID")),
                "minutes_before": minutes_before,
                "action": str(comp.get("action")),
                "description": str(comp.get("description"))
            })
        return {"success": True, "count": len(alarms), "alarms": alarms}

    except Exception as e:
        return {"success": False, "error": str(e)}

# -------------------------
# Run server
# -------------------------
if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting MCP server at http://{host}:{port}/mcp")
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
