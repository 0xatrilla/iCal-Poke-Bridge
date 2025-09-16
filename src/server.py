#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
A MCP server that provides calendar operations for iCloud using CalDAV.
Uses the official MCP SDK with stdio_server.
"""
import os
import json
import logging
import sys
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Optional
from uuid import uuid4

import mcp
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize CalDAV client and ICS utils
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# =============================================================================
# MCP TOOLS
# =============================================================================

tools = []

def tool(func=None, *, description=""):
    """Helper to register tools for MCP SDK."""
    def decorator(f):
        tools.append(mcp.Tool(name=f.__name__, func=f, description=description))
        return f
    if func:
        return decorator(func)
    return decorator

@tool(description="Greet a user by name with a welcome message.")
def greet(name: str) -> str:
    logger.info(f"🔧 TOOL CALL: greet(name='{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

@tool(description="Get MCP server info.")
def get_server_info() -> dict:
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": sys.version.split()[0]
    }

@tool(description="Test the iCloud CalDAV connection.")
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

@tool(description="List your iCloud calendars.")
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

@tool(description="List events from your iCloud calendars.")
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
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
            for cal in caldav_client.principal.calendars():
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
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]

        return {"success": True, "events": all_events, "count": len(all_events),
                "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}}
    except Exception as e:
        logger.error(f"❌ list_my_events failed: {e}")
        return {"success": False, "error": str(e)}

@tool(description="Create an event in your iCloud calendar.")
def create_my_event(
    summary: str,
    start: str,
    end: str,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    all_day: bool = False,
    timezone_name: Optional[str] = None,
    rrule: Optional[str] = None,
    alarm_minutes_before: Optional[int] = None,
    alarm_configs: Optional[str] = None
) -> Dict[str, object]:
    logger.info(f"🔧 TOOL CALL: create_my_event(summary='{summary}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}

        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        start_dt = ical_utils.parse_iso_datetime(start, timezone_name)
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name)

        if all_day:
            if len(start.strip()) != 10 or len(end.strip()) != 10:
                return {"success": False, "error": "For all_day events, start and end must be YYYY-MM-DD."}
            start_date = date.fromisoformat(start.strip())
            end_date = date.fromisoformat(end.strip())
        else:
            if start_dt is None or end_dt is None:
                return {"success": False, "error": "Start and end must be valid ISO-8601 datetimes."}

        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add("uid", f"{uuid4()}@icloud-caldav-mcp")
        evt.add("summary", summary)
        evt.add("dtstamp", datetime.now(timezone.utc))
        if description:
            evt.add("description", description)
        if location:
            evt.add("location", location)
        if all_day:
            evt.add("dtstart", start_date)
            evt.add("dtend", end_date)
        else:
            evt.add("dtstart", start_dt.replace(tzinfo=timezone.utc))
            evt.add("dtend", end_dt.replace(tzinfo=timezone.utc))
        if rrule:
            evt.add("rrule", rrule)

        # Handle alarms
        if alarm_configs:
            try:
                parsed_alarm_configs = json.loads(alarm_configs)
                for alarm_config in parsed_alarm_configs:
                    minutes_before = alarm_config.get("minutes_before", 15)
                    description_ = alarm_config.get("description", "Reminder")
                    action = alarm_config.get("action", "DISPLAY")
                    related = alarm_config.get("related", "START")
                    alarm = ical_utils.create_alarm(minutes_before, description_, action, related)
                    evt.add_component(alarm)
            except Exception:
                pass
        elif alarm_minutes_before is not None:
            alarm = ical_utils.create_alarm(alarm_minutes_before)
            evt.add_component(alarm)

        ics_cal.add_component(evt)
        try:
            ics_cal.add_missing_timezones()
        except Exception:
            pass

        ics_text = ics_cal.to_ical().decode("utf-8")
        created = cal.add_event(ics_text)
        event_url = str(getattr(created, "url", None)) if created else None

        return {"success": True, "event_url": event_url or "", "summary": summary, "start": start, "end": end}

    except Exception as e:
        logger.error(f"❌ create_my_event failed: {e}")
        return {"success": False, "error": str(e)}

# (Other tools: update_my_event, delete_my_event, list_event_alarms can be added in the same style)

# =============================================================================
# START MCP STDIO SERVER
# =============================================================================
if __name__ == "__main__":
    logger.info(f"🚀 Starting MCP server at stdio (stdin/stdout)")
    mcp.stdio_server(tools)
