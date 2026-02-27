"""Tests for eyeonwater system_health module."""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from custom_components.eyeonwater.system_health import (
    async_register,
    system_health_info,
)


class TestAsyncRegister:
    """Test system health callback registration."""

    def test_registers_info_callback(self):
        """async_register must call register.async_register_info with system_health_info."""
        _hass = MagicMock()
        register = MagicMock()

        async_register(_hass, register)

        register.async_register_info.assert_called_once_with(system_health_info)

    def test_register_is_callback_decorated(self):
        """async_register must be decorated with @callback (sync function)."""
        # @callback marks the function but it remains a regular function, not a coro.
        assert not inspect.iscoroutinefunction(
            async_register
        ), "async_register should be a @callback (sync) function"


class TestSystemHealthInfo:
    """Test system_health_info return value."""

    @pytest.mark.asyncio
    async def test_returns_api_endpoint_reachable_key(self):
        """system_health_info must return a dict with 'api_endpoint_reachable'."""
        hass = MagicMock()

        with (
            patch(
                "custom_components.eyeonwater.system_health.get_hostname_for_country",
                return_value="mywater.com",
            ),
            patch(
                "homeassistant.components.system_health.async_check_can_reach_url",
                new=MagicMock(return_value="reachable"),
            ),
        ):
            result = await system_health_info(hass)

        assert "api_endpoint_reachable" in result

    @pytest.mark.asyncio
    async def test_uses_hostname_from_config(self):
        """system_health_info calls get_hostname_for_country with the hass instance."""
        hass = MagicMock()
        mock_hostname = MagicMock(return_value="eyeonwater.com")

        with (
            patch(
                "custom_components.eyeonwater.system_health.get_hostname_for_country",
                mock_hostname,
            ),
            patch(
                "homeassistant.components.system_health.async_check_can_reach_url",
                new=MagicMock(return_value="reachable"),
            ),
        ):
            await system_health_info(hass)

        mock_hostname.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_url_contains_hostname(self):
        """The reachability check receives a URL containing the configured hostname."""
        hass = MagicMock()
        mock_check = MagicMock(return_value=MagicMock())

        with (
            patch(
                "custom_components.eyeonwater.system_health.get_hostname_for_country",
                return_value="mywater.example.com",
            ),
            patch(
                "homeassistant.components.system_health.async_check_can_reach_url",
                mock_check,
            ),
        ):
            await system_health_info(hass)

        # Verify the mock was called once and the URL contains the hostname
        mock_check.assert_called_once()
        call_args = mock_check.call_args[0]  # positional args
        assert len(call_args) == 2
        assert "mywater.example.com" in call_args[1]
        assert call_args[1].startswith("https://")
