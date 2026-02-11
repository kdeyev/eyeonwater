"""Constants for the EyeOnWater integration."""

from datetime import timedelta

SCAN_INTERVAL = timedelta(minutes=15)
DEBOUNCE_COOLDOWN = 60 * 60  # Seconds

DATA_COORDINATOR = "coordinator"
DATA_SMART_METER = "smart_meter_data"

DOMAIN = "eyeonwater"
WATER_METER_NAME = "Water Meter"

IMPORT_HISTORICAL_DATA_SERVICE_NAME = "import_historical_data"
IMPORT_HISTORICAL_DATA_DAYS_NAME = "days"
IMPORT_HISTORICAL_DATA_DAYS_DEFAULT = 365

# Single-sensor mode configuration
USE_SINGLE_SENSOR_MODE = "use_single_sensor_mode"
USE_SINGLE_SENSOR_MODE_DEFAULT = False  # Default: use legacy two-sensor mode
