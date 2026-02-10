"""Provide info to system health."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .config_flow import get_hostname_for_country

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class _SystemHealthRegistration(Protocol):
    def async_register_info(
        self,
        info_callback: Callable[[HomeAssistant], Awaitable[dict[str, Any]]],
        manage_url: str | None = None,
    ) -> None:
        """Register a system health info callback."""


@callback
def async_register(
    _: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register system health callbacks."""
    register_typed = cast("_SystemHealthRegistration", register)
    register_typed.async_register_info(system_health_info, None)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the info page."""
    eow_hostname = get_hostname_for_country(hass)

    return {
        "api_endpoint_reachable": await system_health.async_check_can_reach_url(
            hass,
            f"https://{eow_hostname}",
        ),
    }
