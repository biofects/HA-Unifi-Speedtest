import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity

from .const import DOMAIN, INTEGRATION_NAME, CONF_ENABLE_MULTI_WAN, DEFAULT_ENABLE_MULTI_WAN
from .api_base import UniFiAPIBase

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up UniFi Speed Test button entities."""
    api: UniFiAPIBase = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = []

    # Always add the "all WANs" button
    entities.append(StartSpeedTestAllButton(api, entry))

    # Check if multi-WAN is enabled
    enable_multi_wan = entry.options.get(CONF_ENABLE_MULTI_WAN, 
                                         entry.data.get(CONF_ENABLE_MULTI_WAN, DEFAULT_ENABLE_MULTI_WAN))

    # If we have recent data and multi-WAN is enabled, create per-WAN buttons
    coordinator = hass.data[DOMAIN].get(f"{entry.entry_id}_coordinator")
    created_keys: set[str] = set()

    if enable_multi_wan and coordinator and coordinator.data and isinstance(coordinator.data, dict):
        # Build status map to check which WANs are active
        try:
            wan_status_map = await hass.async_add_executor_job(api.get_wan_status_map)
        except Exception as e:
            _LOGGER.warning(f"Could not get WAN status map: {e}")
            wan_status_map = {}

        def _is_active(iface: str) -> bool:
            """Check if WAN interface is active."""
            st = wan_status_map.get(iface)
            if not st:
                return True  # Assume active if no status info
            return bool(st.get('up') and st.get('ip') and not str(st.get('ip')).startswith('0.'))

        for wan in coordinator.data.get('wan_interfaces', []):
            iface = wan.get('interface_name') or wan.get('interface')
            group = str(wan.get('wan_networkgroup') or 'WAN')
            if iface and _is_active(iface):
                key = f"{iface}_{group}"
                if key not in created_keys:
                    created_keys.add(key)
                    entities.append(StartSpeedTestWanButton(api, entry, iface, group))
                    _LOGGER.info(f"Created button for WAN: {group} ({iface})")

    async_add_entities(entities, True)
    _LOGGER.info(f"Added {len(entities)} button entities")

    # Dynamically add per-WAN buttons as new WANs are discovered by sensors
    if enable_multi_wan and coordinator:
        def _coordinator_listener():
            """Listen for new WANs discovered by coordinator."""
            data = coordinator.data
            if not data or not isinstance(data, dict):
                return
            new_entities: list[ButtonEntity] = []
            
            # Build status map
            try:
                wan_status_map = api.get_wan_status_map()
            except Exception:
                wan_status_map = {}
            
            def _is_active_listener(iface: str) -> bool:
                st = wan_status_map.get(iface)
                if not st:
                    return True
                return bool(st.get('up') and st.get('ip') and not str(st.get('ip')).startswith('0.'))
            
            for wan in data.get('wan_interfaces', []):
                iface = wan.get('interface_name') or wan.get('interface')
                group = str(wan.get('wan_networkgroup') or 'WAN')
                if not iface or not _is_active_listener(iface):
                    continue
                key = f"{iface}_{group}"
                if key not in created_keys:
                    _LOGGER.info(f"Discovered new WAN for button entity: {group} ({iface})")
                    created_keys.add(key)
                    new_entities.append(StartSpeedTestWanButton(api, entry, iface, group))
            if new_entities:
                async_add_entities(new_entities, True)
        
        coordinator.async_add_listener(_coordinator_listener)


class StartSpeedTestAllButton(ButtonEntity):
    """Button to start speed test on all WAN interfaces."""
    
    def __init__(self, api: UniFiAPIBase, entry: ConfigEntry):
        """Initialize the button."""
        self._api = api
        self._entry = entry
        self._attr_name = f"{INTEGRATION_NAME} Run Speedtest (All WANs)"
        self._attr_unique_id = f"{DOMAIN}_button_speedtest_all_{entry.entry_id}"
        self._attr_icon = "mdi:speedometer"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Button pressed: Start speedtest for all WANs")
        try:
            await self.hass.async_add_executor_job(self._api.start_speed_test)
            _LOGGER.info("Speed test started successfully")
            
            # Trigger coordinator refreshes to show results quickly
            coordinator = self.hass.data[DOMAIN].get(f"{self._entry.entry_id}_coordinator")
            if coordinator:
                async def _post_refreshes():
                    """Refresh coordinator at intervals after test starts."""
                    for t in (10, 30, 60, 120):
                        await asyncio.sleep(t)
                        _LOGGER.debug(f"Button-triggered refresh after {t}s")
                        await coordinator.async_request_refresh()
                self.hass.async_create_task(_post_refreshes())
                
        except Exception as e:
            _LOGGER.error(f"Failed to start speed test: {e}")
            raise


class StartSpeedTestWanButton(ButtonEntity):
    """Button to start speed test on a specific WAN interface."""
    
    def __init__(self, api: UniFiAPIBase, entry: ConfigEntry, interface_name: str, wan_group: str):
        """Initialize the button."""
        self._api = api
        self._entry = entry
        self._iface = interface_name
        self._group = wan_group
        self._attr_name = f"{INTEGRATION_NAME} Run Speedtest ({wan_group} - {interface_name})"
        self._attr_unique_id = f"{DOMAIN}_button_speedtest_{entry.entry_id}_{interface_name}_{wan_group}"
        self._attr_icon = "mdi:speedometer"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info(f"Button pressed: Start speedtest for {self._group} ({self._iface})")
        try:
            await self.hass.async_add_executor_job(self._api.start_speed_test, self._iface)
            _LOGGER.info(f"Speed test started successfully for {self._iface}")
            
            # Trigger coordinator refreshes to show results quickly
            coordinator = self.hass.data[DOMAIN].get(f"{self._entry.entry_id}_coordinator")
            if coordinator:
                async def _post_refreshes():
                    """Refresh coordinator at intervals after test starts."""
                    for t in (10, 30, 60, 120):
                        await asyncio.sleep(t)
                        _LOGGER.debug(f"Button-triggered refresh after {t}s for {self._iface}")
                        await coordinator.async_request_refresh()
                self.hass.async_create_task(_post_refreshes())
                
        except Exception as e:
            _LOGGER.error(f"Failed to start speed test for {self._iface}: {e}")
            raise
