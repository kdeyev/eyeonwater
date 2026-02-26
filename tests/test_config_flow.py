"""Tests for configuration flow."""

from unittest.mock import MagicMock

from pyonwater import Account

from custom_components.eyeonwater import config_flow
from custom_components.eyeonwater.config_flow import (
    ConfigFlow,
    create_account_from_config,
    get_hostname_for_country,
)


def test_can_import_config_flow_module():
    """Test that config_flow module can be imported."""
    assert hasattr(config_flow, "ConfigFlow")


def test_can_import_config_flow_class():
    """Test ConfigFlow class exists."""
    assert ConfigFlow is not None


class TestGetHostnameForCountry:
    """Test get_hostname_for_country function."""

    def test_canada_returns_ca_hostname(self):
        """Country CA resolves to the .ca domain."""
        hass = MagicMock()
        hass.config.country = "CA"
        result = get_hostname_for_country(hass)
        assert result == "eyeonwater.ca"

    def test_us_returns_com_hostname(self):
        """Country US resolves to the .com domain."""
        hass = MagicMock()
        hass.config.country = "US"
        result = get_hostname_for_country(hass)
        assert result == "eyeonwater.com"

    def test_other_country_returns_com_hostname(self):
        """Any non-CA country resolves to the .com domain."""
        hass = MagicMock()
        hass.config.country = "DE"
        result = get_hostname_for_country(hass)
        assert result == "eyeonwater.com"

    def test_none_country_returns_com_hostname(self):
        """None/unset country resolves to the .com domain."""
        hass = MagicMock()
        hass.config.country = None
        result = get_hostname_for_country(hass)
        assert result == "eyeonwater.com"


class TestCreateAccountFromConfig:
    """Test create_account_from_config function."""

    def test_returns_account_instance(self):
        """create_account_from_config returns a pyonwater Account object."""
        hass = MagicMock()
        hass.config.country = "US"
        data = {"username": "user@test.com", "password": "s3cret"}
        result = create_account_from_config(hass, data)
        assert isinstance(result, Account)

    def test_account_has_correct_credentials(self):
        """Account is constructed with the username and password from config."""
        hass = MagicMock()
        hass.config.country = "US"
        data = {"username": "user@test.com", "password": "s3cret"}
        result = create_account_from_config(hass, data)
        assert result.username == "user@test.com"
        assert result.password == "s3cret"

    def test_account_hostname_from_hass_country(self):
        """Account eow_hostname reflects the HA country setting."""
        hass_ca = MagicMock()
        hass_ca.config.country = "CA"
        data = {"username": "u", "password": "p"}
        ca_result = create_account_from_config(hass_ca, data)
        assert ca_result.eow_hostname == "eyeonwater.ca"

        hass_us = MagicMock()
        hass_us.config.country = "US"
        us_result = create_account_from_config(hass_us, data)
        assert us_result.eow_hostname == "eyeonwater.com"
