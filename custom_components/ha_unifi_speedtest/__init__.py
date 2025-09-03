from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import logging

from .const import DOMAIN, INTEGRATION_NAME, SERVICE_START_SPEED_TEST, SERVICE_GET_SPEED_TEST_STATUS, CONF_SCHEDULE_INTERVAL, CONF_ENABLE_SCHEDULING, CONF_ENABLE_MULTI_WAN
from .api import UniFiAPI

_LOGGER = logging.getLogger(__name__)

# Service schema for start_speed_test
START_SPEED_TEST_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HA Unifi Speedtest integration from a config entry."""
    _LOGGER.info(f"Starting async_setup_entry for HA Unifi Speedtest integration: {entry.entry_id}")
    
    # Initialize data storage
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize the API
    enable_multi_wan = entry.options.get(CONF_ENABLE_MULTI_WAN, 
                                        entry.data.get(CONF_ENABLE_MULTI_WAN, True))
    
    api = UniFiAPI(
        entry.data["url"], 
        entry.data["username"], 
        entry.data["password"],
        site=entry.data.get("site", "default"),
        verify_ssl=entry.data.get("verify_ssl", False),
        controller_type=entry.data.get("controller_type", "udm"),
        enable_multi_wan=enable_multi_wan
    )
    _LOGGER.info(f"UniFiAPI instance created for site: {entry.data.get('site', 'default')}, controller_type: {entry.data.get('controller_type', 'udm')}, multi_wan: {enable_multi_wan}")
    
    # Test the connection and login
    try:
        await hass.async_add_executor_job(api.login)
        _LOGGER.info("API login completed successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to connect to UniFi controller: {e}")
        return False
    
    # Store the API instance
    hass.data[DOMAIN][entry.entry_id] = api
    _LOGGER.info("API instance stored in hass.data.")

    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _LOGGER.info("Forwarded entry setup to sensor platform.")

    # Register services (only register once for the domain)
    if not hass.services.has_service(DOMAIN, SERVICE_START_SPEED_TEST):
        async def start_speed_test(call: ServiceCall) -> None:
            """Handle the start speed test service call."""
            config_entry_id = call.data.get("config_entry_id")
            
            # If no specific config entry ID provided, use the first available
            if config_entry_id is None:
                if not hass.data[DOMAIN]:
                    _LOGGER.error("No UniFi Speed Test integrations configured")
                    return
                config_entry_id = next(iter(hass.data[DOMAIN].keys()))
                _LOGGER.info(f"No config_entry_id specified, using: {config_entry_id}")
            
            # Get the API instance
            if config_entry_id not in hass.data[DOMAIN]:
                _LOGGER.error(f"Config entry {config_entry_id} not found")
                return
                
            api_instance = hass.data[DOMAIN][config_entry_id]
            
            # Debug logging to identify the issue
            _LOGGER.debug(f"Retrieved API instance type: {type(api_instance)}")
            _LOGGER.debug(f"API instance: {api_instance}")
            
            # Validate that we have the correct API instance
            if not hasattr(api_instance, 'start_speed_test'):
                _LOGGER.error(f"Invalid API instance retrieved. Type: {type(api_instance)}, Value: {api_instance}")
                _LOGGER.error(f"Available data keys: {list(hass.data[DOMAIN].keys())}")
                return
            
            # Get the tracker if it exists
            tracker_key = f"{config_entry_id}_tracker"
            tracker = hass.data[DOMAIN].get(tracker_key)
            
            _LOGGER.info(f"Manual speed test requested for config entry: {config_entry_id}")
            
            try:
                # Record attempt if tracker exists (manual = False for automated parameter)
                if tracker:
                    tracker.record_attempt(automated=False)
                
                # Start the speed test
                await hass.async_add_executor_job(api_instance.start_speed_test)
                
                # Record success if tracker exists
                if tracker:
                    tracker.record_success(automated=False)
                    await tracker.async_save()  # Save after recording
                
                _LOGGER.info("Manual speed test started successfully")
                
            except Exception as e:
                # Record failure if tracker exists
                if tracker:
                    tracker.record_failure(automated=False)
                    await tracker.async_save()  # Save after recording
                    
                _LOGGER.error(f"Failed to start manual speed test: {e}")
                raise

        async def get_speed_test_status(call: ServiceCall) -> None:
            """Handle the get speed test status service call."""
            config_entry_id = call.data.get("config_entry_id")
            
            # If no specific config entry ID provided, use the first available
            if config_entry_id is None:
                if not hass.data[DOMAIN]:
                    _LOGGER.error("No UniFi Speed Test integrations configured")
                    return
                config_entry_id = next(iter(hass.data[DOMAIN].keys()))
            
            # Get the API instance
            if config_entry_id not in hass.data[DOMAIN]:
                _LOGGER.error(f"Config entry {config_entry_id} not found")
                return
                
            api_instance = hass.data[DOMAIN][config_entry_id]
            
            _LOGGER.info(f"Speed test status requested for config entry: {config_entry_id}")
            try:
                status = await hass.async_add_executor_job(api_instance.get_speed_test_status)
                hass.states.async_set("sensor.unifi_speed_test_status", status)
                _LOGGER.info(f"Speed test status retrieved: {status}")
            except Exception as e:
                _LOGGER.error(f"Failed to get speed test status: {e}")

        # Register the services
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_SPEED_TEST,
            start_speed_test,
            schema=START_SPEED_TEST_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_SPEED_TEST_STATUS,
            get_speed_test_status,
            schema=START_SPEED_TEST_SCHEMA,  # Same schema for consistency
        )
        _LOGGER.info("Services registered: start_speed_test, get_speed_test_status")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading config entry for HA Unifi Speedtest integration: {entry.entry_id}")
    
    # Cancel any scheduled listeners
    scheduled_listener_key = f"{entry.entry_id}_scheduled_listener"
    if scheduled_listener_key in hass.data[DOMAIN]:
        remove_listener = hass.data[DOMAIN][scheduled_listener_key]
        if callable(remove_listener):
            remove_listener()
        del hass.data[DOMAIN][scheduled_listener_key]
        _LOGGER.info("Removed scheduled speed test listener")
    
    initial_listener_key = f"{entry.entry_id}_initial_listener"
    if initial_listener_key in hass.data[DOMAIN]:
        remove_listener = hass.data[DOMAIN][initial_listener_key]
        if callable(remove_listener):
            remove_listener()
        del hass.data[DOMAIN][initial_listener_key]
        _LOGGER.info("Removed initial speed test listener")
    
    # Unload the sensors
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    if unload_ok:
        # Clean up stored data for this specific entry
        if entry.entry_id in hass.data[DOMAIN]:
            del hass.data[DOMAIN][entry.entry_id]
        
        # Clean up tracker data for this entry
        tracker_key = f"{entry.entry_id}_tracker"
        if tracker_key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][tracker_key]
        
        # Remove services only if this was the last config entry
        remaining_entries = [key for key in hass.data[DOMAIN].keys() 
                           if not key.endswith('_tracker') and not key.endswith('_listener')]
        if not remaining_entries:  # If no more config entries
            if hass.services.has_service(DOMAIN, SERVICE_START_SPEED_TEST):
                hass.services.async_remove(DOMAIN, SERVICE_START_SPEED_TEST)
            if hass.services.has_service(DOMAIN, SERVICE_GET_SPEED_TEST_STATUS):
                hass.services.async_remove(DOMAIN, SERVICE_GET_SPEED_TEST_STATUS)
            _LOGGER.info("Removed services: start_speed_test, get_speed_test_status")
        
        _LOGGER.info("Integration data removed from hass.data.")
    else:
        _LOGGER.warning("Failed to unload sensor platform.")
    
    return unload_ok
