"""Constants for the MojeKino integration."""

from datetime import timedelta

DOMAIN = "mojekino"
MANUFACTURER = "Ticketware"

CONF_CLIENT_ID = "client_id"
CONF_CINEMA_ID = "cinema_id"
CONF_PROGRAM_ID = "program_id"
CONF_BASE_URL = "base_url"
CONF_LANGUAGE = "language"

SCAN_INTERVAL = timedelta(hours=3)
KEEP_PAST = timedelta(days=7)
"""How long screenings stay in the calendar after they started.

Film pages only list upcoming screenings, so past ones are kept from earlier
updates (until Home Assistant restarts).
"""

MAX_LISTED = 40
"""Upcoming screenings listed in the program sensor's attributes."""
