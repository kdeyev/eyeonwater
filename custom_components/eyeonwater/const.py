"""Constants for the Eye On Water integration."""
from datetime import timedelta

SCAN_INTERVAL = timedelta(minutes=15)
DEBOUNCE_COOLDOWN = 1800  # Seconds

DATA_COORDINATOR = "coordinator"
DATA_SMART_METER = "smart_meter_data"

DOMAIN = "eyeonwater"

METER_NUMBER = "meter_number"
ESIID = "electric_service_identifier"
LAST_UPDATE = "last_updated"
WATER_METER = "Water Meter"
