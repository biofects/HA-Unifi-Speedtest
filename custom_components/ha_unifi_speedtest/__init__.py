from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_current_platform
import logging

from .api import UniFiAPI
from .const import DOMAIN, INTEGRATION_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HA Unifi Speedtest integration from a config entry."""
    _LOGGER.info("Starting async_setup_entry for HA Unifi Speedtest integration.")
    hass.data.setdefault(DOMAIN, {})
    api = UniFiAPI(
        entry.data["url"], 
        entry.data["username"], 
        entry.data["password"],
        site=entry.data.get("site", "default"),  # Default to 'default' if not specified
        verify_ssl=entry.data.get("verify_ssl", False),  # Default to False for backward compatibility
        controller_type=entry.data.get("controller_type", "udm")  # Default to 'udm' for existing users
    )
    _LOGGER.info(f"UniFiAPI instance created for site: {entry.data.get('site', 'default')}, controller_type: {entry.data.get('controller_type', 'udm')}")
    await hass.async_add_executor_job(api.login)
    _LOGGER.info("API login completed.")
    hass.data[DOMAIN][entry.entry_id] = api
    _LOGGER.info("API instance stored in hass.data.")

    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _LOGGER.info("Forwarded entry setup to sensor platform.")

    # Register services
    async def start_speed_test(call):
        _LOGGER.info("Service call: start_speed_test")
        await hass.async_add_executor_job(api.start_speed_test)

    async def get_speed_test_status(call):
        _LOGGER.info("Service call: get_speed_test_status")
        status = await hass.async_add_executor_job(api.get_speed_test_status)
        hass.states.async_set("sensor.unifi_speed_test_status", status)
        _LOGGER.info(f"Speed test status set: {status}")

    hass.services.async_register(DOMAIN, "start_speed_test", start_speed_test)
    hass.services.async_register(DOMAIN, "get_speed_test_status", get_speed_test_status)
    _LOGGER.info("Services registered.")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading config entry for HA Unifi Speedtest integration.")
    # Unload the sensors
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    # Remove the data from hass.data
    if unload_ok:
        hass.data.pop(DOMAIN, None)
        _LOGGER.info("Integration data removed from hass.data.")
    else:
        _LOGGER.warning("Failed to unload sensor platform.")
    
    return unload_ok