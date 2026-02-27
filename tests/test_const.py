"""Tests for eyeonwater constants."""

from datetime import timedelta

from custom_components.eyeonwater import const


def test_scan_interval():
    """Test scan interval is set correctly."""
    assert const.SCAN_INTERVAL == timedelta(minutes=15)
    assert isinstance(const.SCAN_INTERVAL, timedelta)


def test_debounce_cooldown():
    """Test debounce cooldown is set correctly."""
    assert const.DEBOUNCE_COOLDOWN == 3600  # 60 * 60 seconds
    assert isinstance(const.DEBOUNCE_COOLDOWN, int)


def test_domain():
    """Test domain constant."""
    assert const.DOMAIN == "eyeonwater"
    assert isinstance(const.DOMAIN, str)


def test_water_meter_name():
    """Test water meter name constant."""
    assert const.WATER_METER_NAME == "Water Meter"


def test_service_names():
    """Test service name constants."""
    assert const.IMPORT_HISTORICAL_DATA_SERVICE_NAME == "import_historical_data"
    assert const.REPLAY_SCENARIO_SERVICE_NAME == "replay_scenario"
    assert const.VALIDATE_MONOTONIC_SERVICE_NAME == "validate_statistics_monotonic"
    assert const.RESET_STATISTICS_SERVICE_NAME == "reset_statistics"


def test_import_historical_defaults():
    """Test import historical data defaults."""
    assert const.IMPORT_HISTORICAL_DATA_DAYS_NAME == "days"
    assert const.IMPORT_HISTORICAL_DATA_DAYS_DEFAULT == 365


def test_statistics_validation_limits():
    """Test statistics validation constants."""
    assert const.STATISTICS_VALIDATION_BATCH_SIZE == 1000
    assert const.MAX_VIOLATION_LOG_DISPLAY == 10


def test_client_timeout():
    """Test client timeout configuration."""
    timeout = const.CLIENT_TIMEOUT
    assert timeout.total == 30
    assert timeout.connect == 10
    assert timeout.sock_read == 20
