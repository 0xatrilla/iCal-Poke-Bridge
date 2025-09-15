#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
A FastMCP server that provides calendar operations for iCloud using CalDAV.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from uuid import uuid4

from fastmcp import FastMCP
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

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
# Initialize FastMCP and clients
# -----------------------
mcp = FastMCP("iCloud CalDAV MCP Server")
caldav_client = CalDAVClient()
ical_utils = ICalUtils()

# -----------------------
# MCP Tools
# -----------------------
@mcp.tool(description="Greet a user by name for testing MCP connectivity.")
def greet(name: str) -> str:
    logger.info(f"Tool Call: greet('{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."

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

    try:
        test_result = caldav_client.test_connection()
        if test_result.get("success"):
            logger.info(f"Connected to iCloud: {test_result.get('email')}, calendars found: {test_result.get('calendars_found')}")
        else:
            logger.warning(f"⚠ Connection test warning: {test_result.get('error')}")
    except Exception as e:
        logger.warning(f"⚠ Could not test connection: {e}")

    logger.info("="*80)

    # Run FastMCP in stateless HTTP mode (works for Poke JSON requests)
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
