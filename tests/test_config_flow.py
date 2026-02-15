"""Tests for the EyeOnWater config flow."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyonwater import EyeOnWaterAPIError, EyeOnWaterAuthError

from custom_components.eyeonwater.config_flow import (
    CannotConnect,
    InvalidAuth,
    get_hostname_for_country,
    validate_input,
)
from custom_components.eyeonwater.const import DOMAIN

from .conftest import MOCK_CONFIG, MOCK_PASSWORD, MOCK_USERNAME, _make_hass


# --------------- hostname helper ---------------


def test_hostname_returns_ca_for_canada() -> None:
    """Canadian country code should resolve to eyeonwater.ca."""
    hass = _make_hass()
    hass.config.country = "CA"
    assert get_hostname_for_country(hass) == "eyeonwater.ca"


def test_hostname_returns_com_for_us() -> None:
    """US country should resolve to eyeonwater.com."""
    hass = _make_hass()
    hass.config.country = "US"
    assert get_hostname_for_country(hass) == "eyeonwater.com"


def test_hostname_returns_com_for_none() -> None:
    """No country set should default to eyeonwater.com."""
    hass = _make_hass()
    hass.config.country = None
    assert get_hostname_for_country(hass) == "eyeonwater.com"


def test_hostname_returns_com_for_european() -> None:
    """European country code should still default to .com."""
    hass = _make_hass()
    hass.config.country = "DE"
    assert get_hostname_for_country(hass) == "eyeonwater.com"


# --------------- validate_input ---------------


@pytest.mark.asyncio
async def test_validate_input_success(patch_pyonwater) -> None:
    """Successful validation returns title with username."""
    hass = _make_hass()
    with patch(
        "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
    ):
        result = await validate_input(hass, MOCK_CONFIG)
    assert result == {"title": MOCK_USERNAME}


@pytest.mark.asyncio
async def test_validate_input_auth_error(mock_client, patch_pyonwater) -> None:
    """Auth failure raises InvalidAuth."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = EyeOnWaterAuthError("bad creds")
    with patch(
        "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
    ):
        with pytest.raises(InvalidAuth):
            await validate_input(hass, MOCK_CONFIG)


@pytest.mark.asyncio
async def test_validate_input_cannot_connect(mock_client, patch_pyonwater) -> None:
    """Timeout raises CannotConnect."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = asyncio.TimeoutError
    with patch(
        "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
    ):
        with pytest.raises(CannotConnect):
            await validate_input(hass, MOCK_CONFIG)


@pytest.mark.asyncio
async def test_validate_input_api_error(mock_client, patch_pyonwater) -> None:
    """API error raises CannotConnect."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = EyeOnWaterAPIError("server down")
    with patch(
        "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
    ):
        with pytest.raises(CannotConnect):
            await validate_input(hass, MOCK_CONFIG)
