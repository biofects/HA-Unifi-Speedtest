from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import logging
import asyncio

from .const import DOMAIN, INTEGRATION_NAME, SERVICE_START_SPEED_TEST, SERVICE_GET_SPEED_TEST_STATUS, SERVICE_GET_WAN_INTERFACES, CONF_SCHEDULE_INTERVAL, CONF_ENABLE_SCHEDULING, CONF_ENABLE_MULTI_WAN, CONF_HAS_ADMIN, CONF_URL, CONF_API_KEY, CONF_SITE, CONF_VERIFY_SSL, CONF_CONTROLLER_TYPE, CONF_USERNAME, CONF_PASSWORD
from .api_factory import create_unifi_api

_LOGGER = logging.getLogger(__name__)

# Service schema for start_speed_test
START_SPEED_TEST_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
    vol.Optional("interface_name"): cv.string,
})

# Service schema for get_wan_interfaces
GET_WAN_INTERFACES_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HA Unifi Speedtest integration from a config entry."""
    _LOGGER.debug(f"Starting async_setup_entry for HA Unifi Speedtest integration: {entry.entry_id}")
    _LOGGER.info(f"Starting async_setup_entry for HA Unifi Speedtest integration: {entry.entry_id}")
    
    # Initialize data storage
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize the API
    enable_multi_wan = entry.options.get(CONF_ENABLE_MULTI_WAN, 
                                        entry.data.get(CONF_ENABLE_MULTI_WAN, True))
    
    # Detect controller type from saved config or infer from available credentials
    controller_type = entry.data.get(CONF_CONTROLLER_TYPE)
    if not controller_type:
        # Auto-detect based on which credentials are available
        if CONF_API_KEY in entry.data:
            controller_type = "udm"
            _LOGGER.info("Controller type not set, detected 'udm' from API key presence")
        elif CONF_USERNAME in entry.data and CONF_PASSWORD in entry.data:
            controller_type = "controller"
            _LOGGER.info("Controller type not set, detected 'controller' from username/password presence")
        else:
            # Fallback to controller (self-hosted) as it's more common
            controller_type = "controller"
            _LOGGER.warning("Controller type not set and credentials ambiguous, defaulting to 'controller'")
    
    # Prepare credentials based on controller type
    if controller_type == "udm":
        if CONF_API_KEY not in entry.data:
            _LOGGER.error("Controller type is 'udm' but API key is missing from configuration")
            return False
        api = create_unifi_api(
            url=entry.data[CONF_URL],
            controller_type=controller_type,
            api_key=entry.data[CONF_API_KEY],
            site=entry.data.get(CONF_SITE, "default"),
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
            enable_multi_wan=enable_multi_wan
        )
    else:  # software controller
        if CONF_USERNAME not in entry.data or CONF_PASSWORD not in entry.data:
            _LOGGER.error("Controller type is 'controller' but username/password is missing from configuration")
            return False
        api = create_unifi_api(
            url=entry.data[CONF_URL],
            controller_type=controller_type,
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            site=entry.data.get(CONF_SITE, "default"),
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
            enable_multi_wan=enable_multi_wan
        )
    _LOGGER.info(f"UniFi API instance created for site: {entry.data.get('site', 'default')}, controller_type: {controller_type}, multi_wan: {enable_multi_wan}")
    
    # Optionally test the connection once during setup
    ok = await hass.async_add_executor_job(api.test_connection)
    if not ok:
        if controller_type == "udm":
            _LOGGER.error("Failed to validate connection to UniFi controller with provided API key")
        else:
            _LOGGER.error("Failed to validate connection to UniFi controller with provided username/password")
        # We still proceed; sensors will show unavailable until corrected

    # Store the API instance
    hass.data[DOMAIN][entry.entry_id] = api
    _LOGGER.info("API instance stored in hass.data.")

    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    _LOGGER.info("Forwarded entry setup to sensor and button platforms.")

    # Register services (only register once for the domain)
    if not hass.services.has_service(DOMAIN, SERVICE_START_SPEED_TEST):
        async def start_speed_test(call: ServiceCall) -> dict:
            """Handle the start speed test service call."""
            config_entry_id = call.data.get("config_entry_id")
            interface_name = call.data.get("interface_name")  # Optional WAN interface parameter
            
            # If no specific config entry ID provided, find the API instance
            if config_entry_id is None:
                if not hass.data[DOMAIN]:
                    _LOGGER.error("No UniFi Speed Test integrations configured")
                    return {"error": "No UniFi Speed Test integrations configured"}
                # Find the first actual config entry (not a tracker or listener)
                for key, value in hass.data[DOMAIN].items():
                    if not key.endswith('_tracker') and not key.endswith('_listener') and not key.endswith('_wan_interfaces') and hasattr(value, 'start_speed_test'):
                        config_entry_id = key
                        break
                if config_entry_id is None:
                    _LOGGER.error("No valid UniFi API instance found")
                    return {"error": "No valid UniFi API instance found"}
                _LOGGER.info(f"No config_entry_id specified, using: {config_entry_id}")
            
            # Get the API instance
            if config_entry_id not in hass.data[DOMAIN]:
                _LOGGER.error(f"Config entry {config_entry_id} not found")
                return {"error": f"Config entry {config_entry_id} not found"}
                
            api_instance = hass.data[DOMAIN][config_entry_id]
            
            # Check if user has admin access before allowing speed test trigger
            config_entry = hass.config_entries.async_get_entry(config_entry_id)
            if config_entry:
                has_admin = config_entry.options.get(CONF_HAS_ADMIN, config_entry.data.get(CONF_HAS_ADMIN, True))
                if not has_admin:
                    _LOGGER.warning("Speed test service called but user does not have admin access")
                    return {
                        "success": False,
                        "error": "Administrator privileges required to trigger speed tests. Enable 'Has Administrator Access' in integration settings."
                    }
            
            # Debug logging to identify the issue
            _LOGGER.debug(f"Retrieved API instance type: {type(api_instance)}")
            _LOGGER.debug(f"API instance: {api_instance}")
            
            # Validate that we have the correct API instance
            if not hasattr(api_instance, 'start_speed_test'):
                _LOGGER.error(f"Invalid API instance retrieved. Type: {type(api_instance)}, Value: {api_instance}")
                _LOGGER.error(f"Available data keys: {list(hass.data[DOMAIN].keys())}")
                return {"error": "Invalid API instance"}
            
            # Get the tracker if it exists
            tracker_key = f"{config_entry_id}_tracker"
            tracker = hass.data[DOMAIN].get(tracker_key)
            
            interface_msg = f" on interface {interface_name}" if interface_name else " on all WAN interfaces"
            _LOGGER.info(f"Manual speed test requested for config entry: {config_entry_id}{interface_msg}")
            
            try:
                # Record attempt if tracker exists (manual = False for automated parameter)
                if tracker:
                    tracker.record_attempt(automated=False)
                
                # Start the speed test with optional interface parameter
                result = await hass.async_add_executor_job(api_instance.start_speed_test, interface_name)
                
                # Record success if tracker exists
                if tracker:
                    tracker.record_success(automated=False)
                    await tracker.async_save()  # Save after recording
                
                _LOGGER.info(f"Manual speed test started successfully{interface_msg}")
                
                # After starting a test, schedule a few coordinator refreshes to populate entities
                coordinator = hass.data[DOMAIN].get(f"{config_entry_id}_coordinator")
                if coordinator:
                    async def _post_manual_refreshes():
                        for t in (20, 60, 120):
                            await asyncio.sleep(t)
                            _LOGGER.debug(f"Post-manual-test refresh after {t}s")
                            await coordinator.async_request_refresh()
                    if config_entry:
                        config_entry.async_create_background_task(
                            hass,
                            _post_manual_refreshes(),
                            f"{DOMAIN} service speedtest refreshes",
                        )
                    else:
                        hass.async_create_background_task(
                            _post_manual_refreshes(),
                            f"{DOMAIN} service speedtest refreshes",
                        )

                # Return success response
                return {
                    "success": True,
                    "message": f"Speed test started successfully{interface_msg}",
                    "config_entry_id": config_entry_id,
                    "interface": interface_name if interface_name else "all WANs",
                    "result": result if result else "Test initiated"
                }
                
            except Exception as e:
                # Record failure if tracker exists
                if tracker:
                    tracker.record_failure(automated=False)
                    await tracker.async_save()  # Save after recording
                    
                _LOGGER.error(f"Failed to start manual speed test{interface_msg}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to start speed test{interface_msg}"
                }

        async def get_speed_test_status(call: ServiceCall) -> dict:
            """Handle the get speed test status service call."""
            config_entry_id = call.data.get("config_entry_id")
            
            # If no specific config entry ID provided, find the API instance
            if config_entry_id is None:
                if not hass.data[DOMAIN]:
                    _LOGGER.error("No UniFi Speed Test integrations configured")
                    return {"error": "No UniFi Speed Test integrations configured"}
                # Find the first actual config entry (not a tracker or listener)
                for key, value in hass.data[DOMAIN].items():
                    if not key.endswith('_tracker') and not key.endswith('_listener') and not key.endswith('_wan_interfaces') and hasattr(value, 'get_speed_test_status'):
                        config_entry_id = key
                        break
                if config_entry_id is None:
                    _LOGGER.error("No valid UniFi API instance found")
                    return {"error": "No valid UniFi API instance found"}
            
            # Get the API instance
            if config_entry_id not in hass.data[DOMAIN]:
                _LOGGER.error(f"Config entry {config_entry_id} not found")
                return {"error": f"Config entry {config_entry_id} not found"}
                
            api_instance = hass.data[DOMAIN][config_entry_id]
            
            _LOGGER.info(f"Speed test status requested for config entry: {config_entry_id}")
            try:
                status = await hass.async_add_executor_job(api_instance.get_speed_test_status)
                # Always set a short string as the state
                if isinstance(status, dict):
                    if 'error' in status and status['error']:
                        state = "error"
                    elif 'wan_interfaces' in status and status.get('total_interfaces', 0) > 0:
                        state = "ok"
                    elif all(k in status for k in ("download", "upload", "ping")):
                        if all(status.get(k) is not None for k in ("download", "upload", "ping")):
                            state = "ok"
                        else:
                            state = "unavailable"
                    else:
                        state = "unknown"
                else:
                    state = str(status)[:32]  # fallback, truncate if needed

                # Only put the full status in attributes, never in state
                hass.states.async_set(
                    "sensor.unifi_speed_test_status",
                    state,
                    attributes=status if isinstance(status, dict) else {}
                )
                _LOGGER.info(f"Speed test status retrieved: {status}")
                return {
                    "success": True,
                    "status": status,
                    "config_entry_id": config_entry_id
                }
            except Exception as e:
                _LOGGER.error(f"Failed to get speed test status: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }

        # Register the services
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_SPEED_TEST,
            start_speed_test,
            schema=START_SPEED_TEST_SCHEMA,
            supports_response=True,
        )
        
        async def get_wan_interfaces(call: ServiceCall) -> dict:
            """Handle the get WAN interfaces service call."""
            config_entry_id = call.data.get("config_entry_id")
            
            # If no specific config entry ID provided, find the API instance
            if config_entry_id is None:
                if not hass.data[DOMAIN]:
                    _LOGGER.error("No UniFi Speed Test integrations configured")
                    return {"error": "No UniFi Speed Test integrations configured"}
                # Find the first actual config entry (not a tracker or listener)
                for key, value in hass.data[DOMAIN].items():
                    if not key.endswith('_tracker') and not key.endswith('_listener') and not key.endswith('_wan_interfaces') and hasattr(value, 'get_wan_interfaces'):
                        config_entry_id = key
                        break
                if config_entry_id is None:
                    _LOGGER.error("No valid UniFi API instance found")
                    return {"error": "No valid UniFi API instance found"}
            
            # Get the API instance
            if config_entry_id not in hass.data[DOMAIN]:
                _LOGGER.error(f"Config entry {config_entry_id} not found")
                return {"error": f"Config entry {config_entry_id} not found"}
                
            api_instance = hass.data[DOMAIN][config_entry_id]
            
            try:
                # Get WAN interfaces
                wan_interfaces = await hass.async_add_executor_job(api_instance.get_wan_interfaces)
                
                _LOGGER.info(f"WAN Interfaces for config entry {config_entry_id}:")
                wan_list = []
                for idx, wan in enumerate(wan_interfaces, 1):
                    network_name = wan.get('network_name', wan['name'])
                    interface = wan['name']
                    wan_type = wan.get('type', 'unknown')
                    network_group = wan.get('network_group', 'unknown')
                    
                    _LOGGER.info(f"  {idx}. {network_name}: {interface} (type: {wan_type}, group: {network_group})")
                    wan_list.append(f"{network_name} ({interface}, {network_group})")
                
                # Store in hass.data for access by other components if needed
                hass.data[DOMAIN][f"{config_entry_id}_wan_interfaces"] = wan_interfaces
                
                # Return the WAN interface information for display in the UI
                return {
                    "wan_count": len(wan_interfaces),
                    "wan_interfaces": wan_list,
                    "details": wan_interfaces
                }
                
            except Exception as e:
                _LOGGER.error(f"Failed to get WAN interfaces: {e}")
                return {"error": str(e)}
        
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WAN_INTERFACES,
            get_wan_interfaces,
            schema=GET_WAN_INTERFACES_SCHEMA,
            supports_response=True,
        )
        
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_SPEED_TEST_STATUS,
            get_speed_test_status,
            schema=START_SPEED_TEST_SCHEMA,  # Same schema for consistency
            supports_response=True,
        )
        
        _LOGGER.info("Services registered: start_speed_test, get_speed_test_status, get_wan_interfaces")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading config entry for HA Unifi Speedtest integration: {entry.entry_id}")
    
    # Clean up entities and devices for inactive WANs if show_inactive_wans is False
    try:
        from homeassistant.helpers import entity_registry as er, device_registry as dr
        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)
        show_inactive_wans = entry.options.get("show_inactive_wans", False)
        
        _LOGGER.debug(f"Unload: show_inactive_wans = {show_inactive_wans}")
        
        if not show_inactive_wans:
            # Get coordinator to check WAN status
            coord_key = f"{entry.entry_id}_coordinator"
            if coord_key in hass.data.get(DOMAIN, {}):
                coordinator = hass.data[DOMAIN][coord_key]
                if coordinator and coordinator.data:
                    wan_interfaces = coordinator.data.get("wan_interfaces", [])
                    
                    # Build set of active WAN interfaces (those with speedtest data)
                    active_wans = set()
                    for wan in wan_interfaces:
                        interface_name = wan.get('interface_name') or wan.get('interface')
                        download = wan.get('download', 0)
                        upload = wan.get('upload', 0)
                        if interface_name and ((download is not None and download > 0) or (upload is not None and upload > 0)):
                            active_wans.add(interface_name)
                    
                    _LOGGER.debug(f"Active WANs: {active_wans}")
                    
                    # Get all entities for this integration
                    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
                    devices_to_check = set()
                    
                    for entity in entities:
                        # Extract WAN interface from unique_id (format: ha_unifi_speedtest_download_eth9_WAN)
                        # Look for eth followed by a number
                        wan_interface = None
                        parts = entity.unique_id.split("_")
                        for part in parts:
                            if part.startswith("eth") and any(c.isdigit() for c in part):
                                wan_interface = part
                                break
                        
                        if wan_interface and wan_interface not in active_wans:
                            _LOGGER.info(f"Removing inactive WAN entity: {entity.entity_id} (interface: {wan_interface})")
                            if entity.device_id:
                                devices_to_check.add(entity.device_id)
                            entity_registry.async_remove(entity.entity_id)
                    
                    # Clean up devices that no longer have any entities
                    for device_id in devices_to_check:
                        device_entities = er.async_entries_for_device(entity_registry, device_id, include_disabled_entities=True)
                        if not device_entities:
                            _LOGGER.info(f"Removing device with no entities: {device_id}")
                            device_registry.async_remove_device(device_id)
    except Exception as e:
        _LOGGER.error(f"Error cleaning up inactive WAN entities: {e}")
    
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
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])

    if unload_ok:
        # Clean up stored data for this specific entry
        if entry.entry_id in hass.data[DOMAIN]:
            del hass.data[DOMAIN][entry.entry_id]
        
        # Clean up tracker data for this entry
        tracker_key = f"{entry.entry_id}_tracker"
        if tracker_key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][tracker_key]
        
        # Clean up coordinator reference
        coord_key = f"{entry.entry_id}_coordinator"
        if coord_key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][coord_key]

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
