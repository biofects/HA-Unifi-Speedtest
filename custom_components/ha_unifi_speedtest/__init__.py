from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_current_platform

from .api import UniFiAPI
from .const import DOMAIN, INTEGRATION_NAME

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HA Unifi Speedtest integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    api = UniFiAPI(
        entry.data["url"], 
        entry.data["username"], 
        entry.data["password"],
        site=entry.data.get("site", "default"),  # Default to 'default' if not specified
        verify_ssl=entry.data.get("verify_ssl", False)  # Default to False for backward compatibility
    )
    await hass.async_add_executor_job(api.login)
    hass.data[DOMAIN][entry.entry_id] = api

    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Register services
    async def start_speed_test(call):
        await hass.async_add_executor_job(api.start_speed_test)

    async def get_speed_test_status(call):
        status = await hass.async_add_executor_job(api.get_speed_test_status)
        hass.states.async_set("sensor.unifi_speed_test_status", status)

    hass.services.async_register(DOMAIN, "start_speed_test", start_speed_test)
    hass.services.async_register(DOMAIN, "get_speed_test_status", get_speed_test_status)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the sensors
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    # Remove the data from hass.data
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    
    return unload_ok
