#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
Full MCP SDK server providing calendar operations for iCloud via CalDAV.
"""
import os
import sys
import json
import logging
from datetime import datetime, date, timezone, timedelta
from uuid import uuid4
from typing import Optional, Dict

from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

import mcp

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp_server = mcp.MCP(name="iCloud CalDAV MCP Server")

# Initialize CalDAV client
caldav_client = CalDAVClient()
ical_utils = ICalUtils()


# =========================================
# MCP TOOLS
# =========================================

@mcp_server.tool(description="Greet a user by name.")
def greet(name: str) -> str:
    logger.info(f"🔧 TOOL CALL: greet(name='{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."


@mcp_server.tool(description="Get basic server info.")
def get_server_info() -> dict:
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": sys.version.split()[0]
    }


@mcp_server.tool(description="Test connection to iCloud CalDAV.")
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


@mcp_server.tool(description="List your iCloud calendars.")
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


@mcp_server.tool(description="List events from iCloud calendars.")
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
                except Exception:
                    continue

        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]

        return {"success": True, "events": all_events, "count": len(all_events)}

    except Exception as e:
        logger.error(f"❌ list_my_events failed: {e}")
        return {"success": False, "error": str(e)}


@mcp_server.tool(description="Create a new iCloud calendar event.")
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
            start_date = date.fromisoformat(start.strip())
            end_date = date.fromisoformat(end.strip())

        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        evt.add('summary', summary)
        evt.add('dtstamp', datetime.now(timezone.utc))
        if description:
            evt.add('description', description)
        if location:
            evt.add('location', location)

        if all_day:
            evt.add('dtstart', start_date)
            evt.add('dtend', end_date)
        else:
            evt.add('dtstart', start_dt)
            evt.add('dtend', end_dt)

        if rrule:
            evt.add('rrule', rrule)

        # Handle alarms
        if alarm_configs:
            try:
                parsed_alarm_configs = json.loads(alarm_configs)
                for alarm_config in parsed_alarm_configs:
                    alarm = ical_utils.create_alarm(
                        alarm_config.get("minutes_before", 15),
                        alarm_config.get("description", "Reminder"),
                        alarm_config.get("action", "DISPLAY"),
                        alarm_config.get("related", "START")
                    )
                    evt.add_component(alarm)
            except Exception:
                pass
        elif alarm_minutes_before is not None and alarm_minutes_before >= 0:
            alarm = ical_utils.create_alarm(alarm_minutes_before)
            evt.add_component(alarm)

        ics_cal.add_component(evt)
        try:
            ics_cal.add_missing_timezones()
        except Exception:
            pass

        created = cal.add_event(ics_cal.to_ical().decode('utf-8'))
        event_url = str(getattr(created, 'url', None)) if created else None
        return {"success": True, "event_url": event_url or "", "summary": summary, "start": start, "end": end}

    except Exception as e:
        logger.error(f"❌ create_my_event failed: {e}")
        return {"success": False, "error": str(e)}


@mcp_server.tool(description="Update an existing event by URL or UID.")
def update_my_event(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone_name: Optional[str] = None,
    rrule: Optional[str] = None
) -> Dict[str, object]:
    logger.info(f"🔧 TOOL CALL: update_my_event(event_url='{event_url}', uid='{uid}', summary='{summary}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        if not event_url and not uid:
            return {"success": False, "error": "Provide event_url or uid"}

        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        event_obj = caldav_client.get_event_by_url_or_uid(cal, event_url, uid)
        original_cal = IcsCalendar.from_ical(ical_utils.get_event_ics_bytes(event_obj))
        original_event = next(original_cal.walk("vevent"))

        new_cal = ical_utils.create_ics_calendar()
        new_event = IcsEvent()
        new_event.add("uid", original_event.get("uid"))
        new_event.add("dtstamp", original_event.get("dtstamp").dt)

        new_event.add("dtstart", ical_utils.parse_iso_datetime(start, timezone_name) if start else original_event.get("dtstart").dt)
        new_event.add("dtend", ical_utils.parse_iso_datetime(end, timezone_name) if end else original_event.get("dtend").dt)
        new_event.add("summary", summary if summary else str(original_event.get("summary")))
        new_event.add("description", description if description else str(original_event.get("description")))
        new_event.add("location", location if location else str(original_event.get("location")))
        if rrule:
            new_event.add("rrule", rrule)
        elif original_event.get("rrule"):
            new_event.add("rrule", str(original_event.get("rrule")))
        new_event.add("sequence", ical_utils.get_sequence_number(original_event))

        # Copy alarms
        for a in original_event.walk("valarm"):
            new_event.add_component(a)

        new_cal.add_component(new_event)
        try:
            new_cal.add_missing_timezones()
        except Exception:
            pass

        event_obj.data = new_cal.to_ical().decode("utf-8")
        event_obj.save()
        return {"success": True, "event_url": event_url or "", "uid": uid or ""}

    except Exception as e:
        logger.error(f"❌ update_my_event failed: {e}")
        return {"success": False, "error": str(e)}


@mcp_server.tool(description="Delete an event by its CalDAV URL.")
def delete_my_event(event_url: str) -> Dict[str, object]:
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


@mcp_server.tool(description="List VALARMs for an event by URL or UID.")
def list_event_alarms(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    calendar_name: Optional[str] = None
) -> Dict[str, object]:
    logger.info(f"🔧 TOOL CALL: list_event_alarms(event_url='{event_url}', uid='{uid}')")
    try:
        if not caldav_client.connect():
            return {"success": False, "error": "Failed to connect to CalDAV server"}
        if not event_url and not uid:
            return {"success": False, "error": "Provide event_url or uid"}

        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        event_obj = caldav_client.get_event_by_url_or_uid(cal, event_url, uid)
        cal_ics = IcsCalendar.from_ical(ical_utils.get_event_ics_bytes(event_obj))
        alarms = []

        for comp in cal_ics.walk("valarm"):
            trigger_prop = comp.get("trigger")
            minutes_before = None
            related = None
            if trigger_prop:
                try:
                    value = getattr(trigger_prop, "dt", trigger_prop)
                    rel_params = getattr(trigger_prop, "params", {})
                    related = str(rel_params.get("RELATED", "START")) if rel_params else "START"
                    if isinstance(value, timedelta):
                        minutes_before = int(abs(value.total_seconds()) // 60)
                except Exception:
                    pass
            alarms.append({
                "uid": str(comp.get("uid")) if comp.get("uid") else None,
                "x_wr_alarmuid": str(comp.get("X-WR-ALARMUID")) if comp.get("X-WR-ALARMUID") else None,
                "minutes_before": minutes_before,
                "related": related,
                "action": str(comp.get("action")) if comp.get("action") else None,
                "description": str(comp.get("description")) if comp.get("description") else None
            })

        return {"success": True, "alarms": alarms, "count": len(alarms)}

    except Exception as e:
        logger.error(f"❌ list_event_alarms failed: {e}")
        return {"success": False, "error": str(e)}


# =========================================
# RUN MCP SERVER
# =========================================

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting MCP Server on http://{host}:{port}/mcp")

    # HTTP server (persistent)
    mcp_server.run(transport="http", host=host, port=port, stateless_http=False)
