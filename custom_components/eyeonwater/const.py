"""Constants for the Eye On Water integration."""
from datetime import timedelta

SCAN_INTERVAL = timedelta(minutes=5)
DEBOUNCE_COOLDOWN = 15*60  # Seconds

DATA_COORDINATOR = "coordinator"
DATA_SMART_METER = "smart_meter_data"

DOMAIN = "eyeonwater"

DEVICE_CLASS_WATER = "water"
