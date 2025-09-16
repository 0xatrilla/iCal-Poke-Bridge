#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
Uses the official MCP SDK to expose iCloud calendar operations via MCP tools.
"""
import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict
from uuid import uuid4

import mcp  # Official MCP SDK
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize CalDAV client
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# =============================================================================
# MCP TOOLS
# =============================================================================

def greet(name: str) -> str:
    """Simple greeting function for testing MCP connectivity."""
    logger.info(f"🔧 TOOL CALL: greet(name='{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

def get_server_info() -> dict:
    """Returns basic information about the MCP server."""
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": os.sys.version.split()[0],
        "note": "Use JSON-RPC 2.0 format with Accept: text/event-stream for all calls"
    }

def get_connection_status() -> Dict[str, object]:
    """Test the iCloud CalDAV connection."""
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

def list_my_calendars() -> Dict[str, object]:
    """List iCloud calendars."""
    logger.info("🔧 TOOL CALL: list_my_calendars()")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        calendars = caldav_client.get_calendars()
        return {"success": True, "calendars": calendars, "count": len(calendars)}
    except Exception as e:
        logger.error(f"❌ list_my_calendars failed: {e}")
        return {"success": False, "error": str(e)}

def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
    """List events in iCloud calendars."""
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
                    continue

        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]
        return {"success": True, "events": all_events, "count": len(all_events),
                "date_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}}
    except Exception as e:
        logger.error(f"❌ list_my_events failed: {e}")
        return {"success": False, "error": str(e)}

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
    """Create an event in iCloud."""
    logger.info(f"🔧 TOOL CALL: create_my_event(summary='{summary}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        cal = caldav_client.find_calendar(calendar_name=calendar_name)

        # Parse dates
        start_dt = ical_utils.parse_iso_datetime(start, timezone_name)
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name)
        if all_day:
            start_date = date.fromisoformat(start.strip())
            end_date = date.fromisoformat(end.strip())
        else:
            if start_dt is None or end_dt is None:
                return {"success": False, "error": "Start and end must be valid ISO-8601 datetimes"}

        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        evt.add('summary', summary)
        evt.add('dtstamp', datetime.now(timezone.utc))
        if description: evt.add('description', description)
        if location: evt.add('location', location)
        if all_day:
            evt.add('dtstart', start_date)
            evt.add('dtend', end_date)
        else:
            if start_dt.tzinfo is None: start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None: end_dt = end_dt.replace(tzinfo=timezone.utc)
            evt.add('dtstart', start_dt)
            evt.add('dtend', end_dt)
        if rrule: evt.add('rrule', rrule)

        # Alarms
        if alarm_configs:
            try:
                parsed = json.loads(alarm_configs)
                for a in parsed:
                    alarm = ical_utils.create_alarm(a.get('minutes_before', 15),
                                                    a.get('description', 'Reminder'),
                                                    a.get('action', 'DISPLAY'),
                                                    a.get('related', 'START'))
                    evt.add_component(alarm)
            except Exception:
                pass
        elif alarm_minutes_before is not None:
            alarm = ical_utils.create_alarm(alarm_minutes_before)
            evt.add_component(alarm)

        ics_cal.add_component(evt)
        try: ics_cal.add_missing_timezones()
        except Exception: pass

        ics_text = ics_cal.to_ical().decode('utf-8')
        created = cal.add_event(ics_text)
        event_url = str(getattr(created, 'url', None)) if created else None
        return {"success": True, "event_url": event_url or "", "summary": summary, "start": start, "end": end}
    except Exception as e:
        logger.error(f"❌ create_my_event failed: {e}")
        return {"success": False, "error": str(e)}

def delete_my_event(event_url: str) -> Dict[str, object]:
    """Delete an event by URL."""
    logger.info(f"🔧 TOOL CALL: delete_my_event(event_url='{event_url}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        import caldav
        ev = caldav.Event(client=caldav_client.client, url=event_url)
        ev.delete()
        return {"success": True, "event_url": event_url}
    except Exception as e:
        logger.error(f"❌ delete_my_event failed: {e}")
        return {"success": False, "error": str(e)}

# You can add update_my_event and list_event_alarms here similarly...

# =============================================================================
# MCP TOOL REGISTRATION
# =============================================================================

tools = {
    "greet": greet,
    "get_server_info": get_server_info,
    "get_connection_status": get_connection_status,
    "list_my_calendars": list_my_calendars,
    "list_my_events": list_my_events,
    "create_my_event": create_my_event,
    "delete_my_event": delete_my_event,
    # add update_my_event, list_event_alarms here if needed
}

# =============================================================================
# RUN MCP SERVER
# =============================================================================

if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting MCP server at http://{host}:{port}/mcp")
    mcp.http_server(tools=tools, host=host, port=port, stateless=True)
