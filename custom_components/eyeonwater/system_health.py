"""Provide info to system health."""

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .config_flow import get_hostname_for_country


@callback
def async_register(
    _: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, object]:
    """Get info for the info page."""
    eow_hostname = get_hostname_for_country(hass)

    return {
        "api_endpoint_reachable": system_health.async_check_can_reach_url(
            hass,
            f"https://{eow_hostname}",
        ),
    }
