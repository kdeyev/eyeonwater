"""Tests for the EyeOnWater config flow."""

import asyncio
from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest
from pyonwater import EyeOnWaterAPIError, EyeOnWaterAuthError

from custom_components.eyeonwater.config_flow import (
    CannotConnect,
    ConfigFlow,
    InvalidAuth,
    get_hostname_for_country,
    validate_input,
)

from .conftest import MOCK_CONFIG, MOCK_USERNAME, _make_hass

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
@pytest.mark.usefixtures("patch_pyonwater")
async def test_validate_input_success() -> None:
    """Successful validation returns title with username."""
    hass = _make_hass()
    with patch(
        "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
    ):
        result = await validate_input(hass, MOCK_CONFIG)
    assert result == {"title": MOCK_USERNAME}


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_validate_input_auth_error(mock_client) -> None:
    """Auth failure raises InvalidAuth."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = EyeOnWaterAuthError("bad creds")
    with (
        patch(
            "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
        ),
        pytest.raises(InvalidAuth),
    ):
        await validate_input(hass, MOCK_CONFIG)


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_validate_input_cannot_connect(mock_client) -> None:
    """Timeout raises CannotConnect."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = asyncio.TimeoutError
    with (
        patch(
            "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
        ),
        pytest.raises(CannotConnect),
    ):
        await validate_input(hass, MOCK_CONFIG)


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_validate_input_api_error(mock_client) -> None:
    """API error raises CannotConnect."""
    hass = _make_hass()
    mock_client.authenticate.side_effect = EyeOnWaterAPIError("server down")
    with (
        patch(
            "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
        ),
        pytest.raises(CannotConnect),
    ):
        await validate_input(hass, MOCK_CONFIG)


# --------------- reauth ---------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_reauth_confirm_shows_form() -> None:
    """Reauth starts by asking for the password only."""
    flow = ConfigFlow()
    flow.hass = _make_hass()
    entry = MagicMock()
    entry.data = dict(MOCK_CONFIG)

    with patch.object(ConfigFlow, "_get_reauth_entry", return_value=entry):
        result = await flow.async_step_reauth(MappingProxyType(entry.data))

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == MOCK_USERNAME


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_reauth_confirm_updates_entry_on_success() -> None:
    """A valid password updates the entry and reloads it."""
    flow = ConfigFlow()
    flow.hass = _make_hass()
    entry = MagicMock()
    entry.data = dict(MOCK_CONFIG)

    with (
        patch.object(ConfigFlow, "_get_reauth_entry", return_value=entry),
        patch.object(
            ConfigFlow,
            "async_update_reload_and_abort",
            return_value={"type": "abort", "reason": "reauth_successful"},
        ) as mock_update,
        patch(
            "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
        ),
    ):
        result = await flow.async_step_reauth_confirm({"password": "new-password"})

    assert result["reason"] == "reauth_successful"
    assert mock_update.call_args.kwargs["data_updates"] == {"password": "new-password"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_pyonwater")
async def test_reauth_confirm_reports_invalid_auth(mock_client) -> None:
    """A rejected password re-shows the form with an invalid_auth error."""
    flow = ConfigFlow()
    flow.hass = _make_hass()
    entry = MagicMock()
    entry.data = dict(MOCK_CONFIG)
    mock_client.authenticate.side_effect = EyeOnWaterAuthError("nope")

    with (
        patch.object(ConfigFlow, "_get_reauth_entry", return_value=entry),
        patch(
            "custom_components.eyeonwater.config_flow.aiohttp_client.async_get_clientsession",
        ),
    ):
        result = await flow.async_step_reauth_confirm({"password": "still-wrong"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
