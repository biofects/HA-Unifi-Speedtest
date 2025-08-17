from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.event import async_track_time_interval
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
        update_interval=timedelta(minutes=5)  # Check for updates every 5 minutes
    )

    # Only set up automatic speed tests for traditional UniFi Controller (not UDM)
    if api.controller_type != 'udm':
        async def run_hourly_speedtest(now):
            """Run speed test every hour"""
            _LOGGER.info("Running automatic hourly speed test")
            try:
                await hass.async_add_executor_job(api.start_speed_test)
                _LOGGER.info("Hourly speed test started successfully")
            except Exception as e:
                _LOGGER.error(f"Failed to start hourly speed test: {e}")

        # Schedule the hourly speed test (runs every 1 hour)
        async_track_time_interval(hass, run_hourly_speedtest, timedelta(hours=1))
        _LOGGER.info("Hourly speed test scheduled for traditional UniFi Controller")

        # Run an initial speed test on startup (after 1 minute delay to allow system to settle)
        async def run_initial_speedtest(now):
            """Run initial speed test on startup"""
            _LOGGER.info("Running initial speed test on startup")
            try:
                await hass.async_add_executor_job(api.start_speed_test)
                _LOGGER.info("Initial speed test started successfully")
            except Exception as e:
                _LOGGER.error(f"Failed to start initial speed test: {e}")

        # Schedule initial speed test 1 minute after startup
        async_track_time_interval(hass, run_initial_speedtest, timedelta(minutes=1))
    else:
        _LOGGER.info("UDM Pro detected - automatic speed tests disabled. Please set up scheduled speed tests in the UniFi Network web interface.")

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
        """Return the unit of measurement following Home Assistant standards."""
        if self._data_key in ["download", "upload"]:
            return "Mbit/s"  # Changed from "Mbps" to "Mbit/s" to match HA standards
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
