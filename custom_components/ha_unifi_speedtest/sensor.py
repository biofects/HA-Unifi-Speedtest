from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.typing import StateType
from datetime import timedelta
import logging

from .const import DOMAIN, INTEGRATION_NAME
from .api import UniFiAPI

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up the UniFi Speed Test sensors."""
    _LOGGER.info("Setting up UniFi Speed Test sensors.")
    # Retrieve the API instance from hass.data
    api = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.info(f"API instance retrieved: {api}")

    async def async_update_data():
        """Fetch data from API."""
        _LOGGER.info("Fetching data from API for sensor update.")
        return await hass.async_add_executor_job(api.get_speed_test_status)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=5)  # Adjust as needed
    )

    _LOGGER.info("Coordinator created, refreshing config entry.")
    await coordinator.async_config_entry_first_refresh()

    sensors = [
        UniFiSpeedTestSensor(coordinator, "Download Speed", "download"),
        UniFiSpeedTestSensor(coordinator, "Upload Speed", "upload"),
        UniFiSpeedTestSensor(coordinator, "Ping", "ping")
    ]
    _LOGGER.info(f"Sensors created: {sensors}")
    async_add_entities(sensors)
    _LOGGER.info("Entities added to Home Assistant.")
    return True

class UniFiSpeedTestSensor(CoordinatorEntity):
    def __init__(self, coordinator, name, data_key):
        super().__init__(coordinator)
        self._name = name
        self._data_key = data_key
        self._state = None
        _LOGGER.info(f"Sensor initialized: {self._name} ({self._data_key})")

    @property
    def name(self) -> str:
        return f"UniFi Speed Test {self._name}"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._data_key}"

    @property
    def state(self) -> StateType:
        value = self.coordinator.data.get(self._data_key) if self.coordinator.data else None
        _LOGGER.info(f"Getting state for {self._name}: {value}")
        return value

    @property
    def unit_of_measurement(self) -> str:
        if self._data_key in ["download", "upload"]:
            return "Mbps"
        elif self._data_key == "ping":
            return "ms"
        return None

    @property
    def device_info(self):
        """Return device information about this entity."""
        info = {
            "identifiers": {(DOMAIN, "unifi_speedtest")},
            "name": INTEGRATION_NAME,
            "manufacturer": "UniFi"
        }
        _LOGGER.info(f"Device info for {self._name}: {info}")
        return info
