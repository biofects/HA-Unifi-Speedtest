import asyncio
import logging
import random
from datetime import timedelta, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from .const import DOMAIN, INTEGRATION_NAME, CONF_SCHEDULE_INTERVAL, CONF_ENABLE_SCHEDULING, CONF_POLLING_INTERVAL, CONF_ENABLE_MULTI_WAN, CONF_HAS_ADMIN, CONF_RUN_SPEEDTEST_ON_STARTUP
from .api_base import UniFiAPIBase

_LOGGER = logging.getLogger(__name__)

def calculate_polling_interval(schedule_interval: int) -> int:
    """Calculate optimal polling interval based on speed test schedule."""
    if schedule_interval <= 30:
        return max(10, schedule_interval // 3)  # Very frequent speed tests
    elif schedule_interval <= 60:
        return max(15, schedule_interval // 2)  # Moderate frequency
    else:
        return max(20, schedule_interval // 3)  # Conservative frequency

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up the UniFi Speed Test sensors."""
    _LOGGER.debug("Setting up UniFi Speed Test sensors")
    # Retrieve the API instance from hass.data
    api: UniFiAPIBase = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug(f"API instance retrieved: {api}")

    # Create a tracker for speed test runs with persistence
    store = Store(hass, 1, f"{DOMAIN}_{config_entry.entry_id}_tracker")
    speed_test_tracker = SpeedTestTracker(store)
    await speed_test_tracker.async_load()
    hass.data[DOMAIN][f"{config_entry.entry_id}_tracker"] = speed_test_tracker

    async def async_update_data():
        """Fetch data from API with enhanced error handling."""
        _LOGGER.debug("Fetching data from API for sensor update.")
        try:
            # Check API health before making requests
            health = await hass.async_add_executor_job(api.get_health_status)
            
            if health.get('in_cooldown', False):
                _LOGGER.warning(f"API in cooldown until {health.get('cooldown_until', 'unknown')}, using cached data")
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}
            
            if health.get('consecutive_403s', 0) > 5:
                _LOGGER.warning(f"Too many 403 errors ({health.get('consecutive_403s')}), skipping API call")
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}
            
            # Fetch speed test status
            speed_test_data = await hass.async_add_executor_job(api.get_speed_test_status)
            
            # Also update WAN status map for availability checking (UDM only)
            if api.controller_type == 'udm':
                try:
                    wan_status = await hass.async_add_executor_job(api.get_wan_status_map)
                    hass.data[DOMAIN][f"{config_entry.entry_id}_wan_status"] = wan_status
                except Exception as e:
                    _LOGGER.debug(f"Could not update WAN status map: {e}")
            
            return speed_test_data
            
        except Exception as e:
            error_str = str(e).lower()
            if "403" in error_str or "forbidden" in error_str:
                _LOGGER.warning("API returned 403 - using cached data and backing off")
                # Return cached data instead of failing
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}
            elif "rate limit" in error_str:
                _LOGGER.warning("API rate limit detected - using cached data")
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}
            elif "timeout" in error_str:
                _LOGGER.warning("API timeout - using cached data")
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}
            else:
                _LOGGER.error(f"Error fetching speed test data: {e}")
                # Still return cached data instead of raising
                return coordinator.data if coordinator.data else {'download': None, 'upload': None, 'ping': None}

    # Get scheduling configuration from config entry options or data
    has_admin = config_entry.options.get(CONF_HAS_ADMIN,
                                        config_entry.data.get(CONF_HAS_ADMIN, True))
    enable_scheduling = config_entry.options.get(CONF_ENABLE_SCHEDULING, 
                                               config_entry.data.get(CONF_ENABLE_SCHEDULING, True))
    # Multi-WAN enable
    enable_multi_wan = config_entry.options.get(CONF_ENABLE_MULTI_WAN,
                                               config_entry.data.get(CONF_ENABLE_MULTI_WAN, True))
    show_inactive_wans = config_entry.options.get('show_inactive_wans',
                                                 config_entry.data.get('show_inactive_wans', False))

    # Disable scheduling if user doesn't have admin access
    if not has_admin and enable_scheduling:
        _LOGGER.warning("Automatic speed tests disabled: Administrator privileges required to trigger speed tests")
        enable_scheduling = False
    
    schedule_interval = config_entry.options.get(CONF_SCHEDULE_INTERVAL, 
                                               config_entry.data.get(CONF_SCHEDULE_INTERVAL, 90))

    # Calculate or get polling interval
    polling_interval = config_entry.options.get(CONF_POLLING_INTERVAL, 
                                              config_entry.data.get(CONF_POLLING_INTERVAL))
    
    # If no polling interval set, calculate it automatically
    if polling_interval is None:
        polling_interval = calculate_polling_interval(schedule_interval) if enable_scheduling else 30
        _LOGGER.info(f"Auto-calculated polling interval: {polling_interval} minutes")
    else:
        _LOGGER.info(f"Using configured polling interval: {polling_interval} minutes")
    
    # Additional validation: Ensure polling is reasonable compared to speed test interval
    if enable_scheduling and polling_interval >= schedule_interval:
        # Auto-adjust if somehow the validation was bypassed
        new_polling = calculate_polling_interval(schedule_interval)
        _LOGGER.warning(f"Adjusting polling interval from {polling_interval} to {new_polling} minutes to avoid conflicts with speed test schedule ({schedule_interval} minutes)")
        polling_interval = new_polling

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=polling_interval)
    )

    # Expose coordinator for services to trigger refreshes after manual tests
    hass.data[DOMAIN][f"{config_entry.entry_id}_coordinator"] = coordinator

    async def run_scheduled_speedtest(now=None):
        """Run speed test and track execution with enhanced error handling"""
        _LOGGER.info(f"Running scheduled speed test at {datetime.now()}")
        try:
            # Check API health before attempting speed test
            health = await hass.async_add_executor_job(api.get_health_status)
            
            if health.get('in_cooldown', False):
                _LOGGER.warning(f"API in cooldown, skipping scheduled speed test until {health.get('cooldown_until', 'unknown')}")
                speed_test_tracker.record_failure(automated=True, reason="API in cooldown")
                await speed_test_tracker.async_save()
                return
            
            if health.get('consecutive_403s', 0) > 3:
                _LOGGER.warning(f"Too many 403 errors ({health.get('consecutive_403s')}), skipping scheduled speed test")
                speed_test_tracker.record_failure(automated=True, reason="Too many 403 errors")
                await speed_test_tracker.async_save()
                return
            
            # Add some randomization to avoid all instances hitting at the same time
            delay = random.randint(0, 60)  # 0-60 second random delay
            if delay > 0:
                _LOGGER.debug(f"Adding {delay} second randomization delay")
                await asyncio.sleep(delay)
            
            speed_test_tracker.record_attempt(automated=True)
            await hass.async_add_executor_job(api.start_speed_test)
            speed_test_tracker.record_success(automated=True)
            await speed_test_tracker.async_save()
            _LOGGER.info("Scheduled speed test started successfully")
            
            # Post-test: schedule a few refreshes to populate data quickly
            async def _post_test_refreshes():
                for t in (20, 60, 120):
                    await asyncio.sleep(t)
                    _LOGGER.debug(f"Post-test refresh after {t}s")
                    await coordinator.async_request_refresh()
            hass.async_create_task(_post_test_refreshes())

        except Exception as e:
            error_str = str(e).lower()
            if "403" in error_str or "forbidden" in error_str:
                reason = "403 Forbidden - possible rate limiting"
                _LOGGER.warning(f"Scheduled speed test failed with 403 error: {e}")
            elif "cooldown" in error_str:
                reason = "API in cooldown period"
                _LOGGER.warning(f"Scheduled speed test skipped due to cooldown: {e}")
            else:
                reason = f"Error: {str(e)[:100]}"  # Truncate long error messages
                _LOGGER.error(f"Failed to start scheduled speed test: {e}")
            
            speed_test_tracker.record_failure(automated=True, reason=reason)
            await speed_test_tracker.async_save()

    # Set up automatic speed tests if enabled
    if enable_scheduling:
        _LOGGER.info(f"[SCHEDULER] Setting up automatic speed tests for {api.controller_type} controller every {schedule_interval} minutes")
        _LOGGER.info(f"Setting up automatic speed tests for {api.controller_type} controller every {schedule_interval} minutes")
        _LOGGER.info(f"Data will be polled every {polling_interval} minutes")
        
        # Schedule the speed test at user-defined interval
        interval = timedelta(minutes=schedule_interval)
        remove_scheduled_listener = async_track_time_interval(hass, run_scheduled_speedtest, interval)
        _LOGGER.info(f"[SCHEDULER] Speed test scheduled every {schedule_interval} minutes - SCHEDULER ACTIVE!")
        _LOGGER.info(f"Speed test scheduled every {schedule_interval} minutes")

        # Store the listener removal function so we can clean it up later
        hass.data[DOMAIN][f"{config_entry.entry_id}_scheduled_listener"] = remove_scheduled_listener

        # Store intervals in data for reference
        hass.data[DOMAIN][f"{config_entry.entry_id}_schedule_interval"] = schedule_interval
        hass.data[DOMAIN][f"{config_entry.entry_id}_polling_interval"] = polling_interval

        # Check if user wants to run speedtest on startup
        run_speedtest_on_startup = config_entry.options.get(
            CONF_RUN_SPEEDTEST_ON_STARTUP,
            config_entry.data.get(CONF_RUN_SPEEDTEST_ON_STARTUP, False)
        )

        # Optionally trigger one initial speed test soon after startup to seed data
        if run_speedtest_on_startup:
            async def _initial_seed():
                seed_delay = random.randint(10, 45)
                _LOGGER.info(f"Scheduling initial seed speed test in ~{seed_delay}s (user enabled)")
                await asyncio.sleep(seed_delay)
                await run_scheduled_speedtest()
            hass.async_create_task(_initial_seed())
        else:
            _LOGGER.info("Skipping initial seed speed test (disabled by user) - will use last available data")
    else:
        _LOGGER.info(f"Automatic speed test scheduling disabled for {api.controller_type} controller")
        _LOGGER.info(f"Data will be polled every {polling_interval} minutes")

    # Request initial refresh in background without blocking startup
    _LOGGER.info("Coordinator created, scheduling initial data refresh.")
    hass.async_create_task(coordinator.async_refresh())

    # Track created WAN sensor keys to avoid duplicates and enable dynamic additions
    created_wan_keys: set[str] = set()
    hass.data[DOMAIN][f"{config_entry.entry_id}_created_wans"] = created_wan_keys

    # Clean up entities that shouldn't exist based on current configuration
    # IMPORTANT: Only do this if we have data, otherwise we'll create zombie entities
    from homeassistant.helpers import entity_registry as er
    entity_reg = er.async_get(hass)
    
    # Get all entities for this integration
    entities = er.async_entries_for_config_entry(entity_reg, config_entry.entry_id)
    
    # Only cleanup if we have coordinator data to work with
    # If data isn't available yet, skip cleanup to avoid removing valid entities
    if coordinator.data and isinstance(coordinator.data, dict):
        # Determine which WAN interfaces should exist
        should_exist_wans = set()
        if coordinator.data.get('wan_interfaces'):
            for wan in coordinator.data['wan_interfaces']:
                interface_name = wan.get('interface_name') or wan.get('interface')
                if interface_name:
                    # Check if this WAN should have entities based on show_inactive_wans setting
                    if show_inactive_wans:
                        should_exist_wans.add(interface_name)
                    else:
                        # Only include if it has actual speedtest data
                        download = wan.get('download')
                        upload = wan.get('upload')
                        if (download is not None and download > 0) or (upload is not None and upload > 0):
                            should_exist_wans.add(interface_name)
        
        _LOGGER.info(f"WANs that should exist: {should_exist_wans}")
        
        # Remove entities for WANs that shouldn't exist
        for entity in entities:
            # Check if this is a WAN-specific entity (has eth in unique_id)
            if entity.platform == "sensor" and "_eth" in entity.unique_id:
                # Extract interface name from unique_id (format: ha_unifi_speedtest_download_eth9_WAN)
                parts = entity.unique_id.split("_")
                for i, part in enumerate(parts):
                    if part.startswith("eth"):
                        interface_name = part
                        if interface_name not in should_exist_wans:
                            _LOGGER.debug(f"Removing entity {entity.entity_id} for inactive WAN {interface_name}")
                            entity_reg.async_remove(entity.entity_id)
                        break
    else:
        _LOGGER.debug("Skipping entity cleanup - no coordinator data available yet (will cleanup on next update)")

    # Helper to build a canonical WAN key
    def _wan_key(interface_name: str, wan_group: str) -> str:
        return f"{interface_name}_{wan_group}"

    # Create sensors based on controller type and actual/pre-discovered WAN connections
    sensors: list[SensorEntity] = []
    coordinator_data = coordinator.data

    if api.controller_type == 'udm' and enable_multi_wan:
        _LOGGER.info("UDM controller detected with Multi-WAN enabled - sensors will appear after first speed test")

        # Initialize empty WAN status map, will be populated by coordinator updates
        wan_status_map = {}
        hass.data[DOMAIN][f"{config_entry.entry_id}_wan_status"] = {}
        
        # Fetch WAN status in background to avoid blocking startup
        async def _fetch_wan_status_background():
            """Fetch WAN status map in background."""
            try:
                wan_status_map = await hass.async_add_executor_job(api.get_wan_status_map)
                hass.data[DOMAIN][f"{config_entry.entry_id}_wan_status"] = wan_status_map
                _LOGGER.debug(f"WAN status map fetched: {wan_status_map}")
                for iface, status in wan_status_map.items():
                    _LOGGER.debug(f"  Interface {iface}: up={status.get('up')}, ip={status.get('ip')}, speed={status.get('speed')}, rx_bytes={status.get('rx_bytes')}, tx_bytes={status.get('tx_bytes')}, is_active={status.get('is_active')}")
            except Exception as e:
                _LOGGER.debug(f"Failed to get WAN status map: {e}")
        
        hass.async_create_task(_fetch_wan_status_background())

        # Helper to create multi-wan sensors for a given interface
        def _create_multiwan_sensors(interface_name: str, wan_group: str, ordinal_index: int) -> list[SensorEntity]:
            key = _wan_key(interface_name, wan_group)
            if key in created_wan_keys:
                return []
            created_wan_keys.add(key)
            _LOGGER.info(f"Creating Multi-WAN sensors for {wan_group} ({interface_name})")
            pretty_group = wan_group
            return [
                UniFiSpeedTestSensorMultiWAN(coordinator, f"Download Speed {pretty_group}", "download", interface_name, wan_group, ordinal_index, show_inactive_wans, config_entry.entry_id),
                UniFiSpeedTestSensorMultiWAN(coordinator, f"Upload Speed {pretty_group}", "upload", interface_name, wan_group, ordinal_index, show_inactive_wans, config_entry.entry_id),
                UniFiSpeedTestSensorMultiWAN(coordinator, f"Ping {pretty_group}", "ping", interface_name, wan_group, ordinal_index, show_inactive_wans, config_entry.entry_id),
            ]

        def _is_wan_active(interface_name: str) -> bool:
            """Check if WAN should have sensors created based on show_inactive_wans setting.
            
            When show_inactive_wans=True: Always return True (create all sensors, availability handles status)
            When show_inactive_wans=False: Only return True for active WANs (don't create inactive sensors)
            """
            if show_inactive_wans:
                # Create sensors for all WANs - availability property will handle marking inactive ones
                return True
            
            if not interface_name:
                return False  # Don't create sensors for unknown interfaces
            
            st = wan_status_map.get(interface_name)
            
            # If we have status map data, use it
            if st:
                # Use the is_active flag if available (considers link, IP, speed, and traffic)
                if "is_active" in st:
                    return st["is_active"]
                
                # Fallback to old logic: Only create sensor if WAN has link up AND valid IP
                if st.get('up') and (st.get('ip') and not str(st.get('ip')).startswith('0.') ):
                    return True
                return False
            
            # No status map data - check if this WAN has actual speedtest results
            # Find this WAN in coordinator data and check if it has real data
            if coordinator_data and isinstance(coordinator_data, dict):
                wan_interfaces = coordinator_data.get('wan_interfaces', [])
                for wan in wan_interfaces:
                    wan_iface = wan.get('interface_name') or wan.get('interface')
                    if wan_iface == interface_name:
                        # Check if it has actual speedtest data (not None/null and not 0)
                        download = wan.get('download')
                        upload = wan.get('upload')
                        # Only create sensor if it has real speed test data (non-zero values)
                        if (download is not None and download > 0) or (upload is not None and upload > 0):
                            return True
                        return False
            
            # Unknown status and no speedtest data - don't create to be safe
            return False

        # 1) If coordinator already has data with wan_interfaces, create sensors now
        if (coordinator_data and isinstance(coordinator_data, dict) and coordinator_data.get('wan_interfaces')):
            _LOGGER.debug(f"Found {len(coordinator_data['wan_interfaces'])} WAN interfaces in coordinator data")
            for idx, wan_interface in enumerate(coordinator_data['wan_interfaces']):
                interface_name = wan_interface.get('interface_name') or wan_interface.get('interface') or 'unknown'
                wan_group = wan_interface.get('wan_networkgroup') or 'WAN'
                download = wan_interface.get('download')
                upload = wan_interface.get('upload')
                _LOGGER.debug(f"Checking WAN interface: {interface_name} ({wan_group}) - download={download}, upload={upload}")
                if not _is_wan_active(interface_name):
                    _LOGGER.debug(f"Skipping inactive/unassigned WAN interface: {interface_name}")
                    continue
                _LOGGER.info(f"Creating sensors for active WAN interface: {interface_name}")
                sensors.extend(_create_multiwan_sensors(interface_name, str(wan_group), idx))


        # Register a coordinator listener to dynamically add new WAN sensors when discovered later
        def _coordinator_listener():
            data = coordinator.data
            if not data or not isinstance(data, dict):
                return
            wan_list = data.get('wan_interfaces') or []
            new_entities: list[SensorEntity] = []
            for idx, wan_interface in enumerate(wan_list):
                i_name = wan_interface.get('interface_name') or wan_interface.get('interface')
                if not i_name:
                    continue
                if not _is_wan_active(i_name):
                    continue
                w_group = wan_interface.get('wan_networkgroup') or 'WAN'
                key = _wan_key(i_name, str(w_group))
                if key not in created_wan_keys:
                    new_entities.extend(_create_multiwan_sensors(i_name, str(w_group), idx))
            if new_entities:
                _LOGGER.info(f"Discovered new active WAN interfaces at runtime, adding {len(new_entities)} entities")
                async_add_entities(new_entities)

        # Attach listener
        coordinator.async_add_listener(_coordinator_listener)

    else:
        # Traditional controller or multi-wan disabled - single WAN
        _LOGGER.info("Traditional controller or multi-WAN disabled - creating single WAN device")
        sensors.extend([
            UniFiSpeedTestSensor(coordinator, "Download Speed", "download"),
            UniFiSpeedTestSensor(coordinator, "Upload Speed", "upload"),
            UniFiSpeedTestSensor(coordinator, "Ping", "ping"),
        ])
    
    # Add common sensors
    sensors.extend([
        SpeedTestRunsSensor(speed_test_tracker, "Speed Test Runs"),
        UniFiAPIHealthSensor(api, "API Health")
    ])
    
    _LOGGER.info(f"Sensors created: {[s.name for s in sensors]}")
    async_add_entities(sensors)
    _LOGGER.info("Entities added to Home Assistant.")
    return True


class SpeedTestTracker:
    """Track speed test execution statistics with persistence and failure reasons."""
    
    def __init__(self, store: Store):
        self._store = store
        self.total_attempts = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.automated_attempts = 0
        self.manual_attempts = 0
        self.automated_successes = 0
        self.manual_successes = 0
        self.automated_failures = 0
        self.manual_failures = 0
        self.last_run_time = None
        self.last_success_time = None
        self.last_failure_time = None
        self.last_automated_run = None
        self.last_manual_run = None
        self.last_failure_reason = None
        self.failure_reasons = []  # Keep track of recent failure reasons
    
    async def async_load(self):
        """Load data from storage."""
        try:
            data = await self._store.async_load()
            if data:
                self.total_attempts = data.get('total_attempts', 0)
                self.successful_runs = data.get('successful_runs', 0)
                self.failed_runs = data.get('failed_runs', 0)
                self.automated_attempts = data.get('automated_attempts', 0)
                self.manual_attempts = data.get('manual_attempts', 0)
                self.automated_successes = data.get('automated_successes', 0)
                self.manual_successes = data.get('manual_successes', 0)
                self.automated_failures = data.get('automated_failures', 0)
                self.manual_failures = data.get('manual_failures', 0)
                self.last_failure_reason = data.get('last_failure_reason')
                self.failure_reasons = data.get('failure_reasons', [])
                
                # Parse datetime strings back to datetime objects
                for field in ['last_run_time', 'last_success_time', 'last_failure_time', 
                             'last_automated_run', 'last_manual_run']:
                    time_str = data.get(field)
                    if time_str:
                        setattr(self, field, datetime.fromisoformat(time_str))
                
                _LOGGER.info(f"Loaded speed test tracker data: {self.total_attempts} total attempts ({self.automated_attempts} automated, {self.manual_attempts} manual), {self.successful_runs} successful")
        except Exception as e:
            _LOGGER.warning(f"Failed to load speed test tracker data: {e}")
    
    async def async_save(self):
        """Save data to storage."""
        try:
            data = {
                'total_attempts': self.total_attempts,
                'successful_runs': self.successful_runs,
                'failed_runs': self.failed_runs,
                'automated_attempts': self.automated_attempts,
                'manual_attempts': self.manual_attempts,
                'automated_successes': self.automated_successes,
                'manual_successes': self.manual_successes,
                'automated_failures': self.automated_failures,
                'manual_failures': self.manual_failures,
                'last_failure_reason': self.last_failure_reason,
                'failure_reasons': self.failure_reasons[-10:],  # Keep only last 10 failure reasons
            }
            
            # Convert datetime objects to ISO format strings
            for field in ['last_run_time', 'last_success_time', 'last_failure_time', 
                         'last_automated_run', 'last_manual_run']:
                dt_value = getattr(self, field)
                data[field] = dt_value.isoformat() if dt_value else None
                
            await self._store.async_save(data)
            _LOGGER.debug("Speed test tracker data saved successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to save speed test tracker data: {e}")
    
    def record_attempt(self, automated=False):
        """Record a speed test attempt."""
        self.total_attempts += 1
        self.last_run_time = datetime.now()
        
        if automated:
            self.automated_attempts += 1
            self.last_automated_run = datetime.now()
            _LOGGER.info(f"Automated speed test attempt recorded. Total automated attempts: {self.automated_attempts}")
        else:
            self.manual_attempts += 1
            self.last_manual_run = datetime.now()
            _LOGGER.info(f"Manual speed test attempt recorded. Total manual attempts: {self.manual_attempts}")
            
        _LOGGER.info(f"Total speed test attempts: {self.total_attempts}")
    
    def record_success(self, automated=False):
        """Record a successful speed test."""
        self.successful_runs += 1
        self.last_success_time = datetime.now()
        
        if automated:
            self.automated_successes += 1
            _LOGGER.info(f"Automated speed test success recorded. Total automated successes: {self.automated_successes}")
        else:
            self.manual_successes += 1
            _LOGGER.info(f"Manual speed test success recorded. Total manual successes: {self.manual_successes}")
            
        _LOGGER.info(f"Total successful speed tests: {self.successful_runs}")
    
    def record_failure(self, automated=False, reason=None):
        """Record a failed speed test."""
        self.failed_runs += 1
        self.last_failure_time = datetime.now()
        self.last_failure_reason = reason
        
        if reason:
            self.failure_reasons.append({
                'time': datetime.now().isoformat(),
                'reason': reason,
                'automated': automated
            })
        
        if automated:
            self.automated_failures += 1
            _LOGGER.info(f"Automated speed test failure recorded. Total automated failures: {self.automated_failures}")
        else:
            self.manual_failures += 1
            _LOGGER.info(f"Manual speed test failure recorded. Total manual failures: {self.manual_failures}")
            
        _LOGGER.info(f"Total failed speed tests: {self.failed_runs}")
    
    @property
    def success_rate(self):
        """Calculate success rate as percentage."""
        if self.total_attempts == 0:
            return 0
        return round((self.successful_runs / self.total_attempts) * 100, 1)
    
    @property
    def automated_success_rate(self):
        """Calculate automated success rate as percentage."""
        if self.automated_attempts == 0:
            return 0
        return round((self.automated_successes / self.automated_attempts) * 100, 1)


class UniFiSpeedTestSensor(CoordinatorEntity, SensorEntity):
    """Sensor for UniFi Speed Test measurements with long-term statistics support."""
    
    def __init__(self, coordinator, name, data_key):
        super().__init__(coordinator)
        self._name = name
        self._data_key = data_key
        self._state = None
        
        # Validate data_key to prevent unit_of_measurement errors
        if data_key not in ["download", "upload", "ping"]:
            _LOGGER.error(f"INVALID data_key '{data_key}' for sensor {name}! Must be 'download', 'upload', or 'ping'")
        
        _LOGGER.info(f"Sensor initialized: {self._name} ({self._data_key})")

    @property
    def name(self) -> str:
        return f"UniFi Speed Test {self._name}"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._data_key}"

    @property
    def state(self) -> StateType:
        data = self.coordinator.data or {}
        interfaces = data.get("wan_interfaces", [])

        value = interfaces[0].get(self._data_key) if interfaces else data.get(self._data_key)
        _LOGGER.debug(f"Getting state for {self._name}: {value}")
        return value

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement following Home Assistant standards."""
        # CRITICAL: Must return valid unit when device_class is set (HA 2025.x requirement)
        # NEVER return None to prevent KeyError in HA 2025.x unit conversion
        if self._data_key in ["download", "upload"]:
            return "Mbit/s"  # Changed from "Mbps" to "Mbit/s" to match HA standards
        elif self._data_key == "ping":
            return "ms"
        
        # Should never reach here if sensors are created correctly
        _LOGGER.error(f"Sensor {self._name} with data_key '{self._data_key}' has no unit defined!")
        _LOGGER.error(f"This indicates a bug - sensor was created with invalid data_key")
        # Return a default to prevent HA 2025.x errors - do NOT return None!
        return "Mbit/s"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class for the sensor."""
        # Only set device_class when we have a valid unit to avoid HA 2025.x errors
        if self._data_key in ["download", "upload"]:
            return SensorDeviceClass.DATA_RATE
        # Do not set device_class for ping (ms) to avoid unit conversion to seconds
        return None

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class for long-term statistics."""
        # All speed test measurements should be tracked for statistics
        return SensorStateClass.MEASUREMENT

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision."""
        if self._data_key in ["download", "upload"]:
            return 2  # Show 2 decimal places for speed measurements
        elif self._data_key == "ping":
            return 1  # Show 1 decimal place for ping
        return None

    @property
    def device_info(self):
        """Return device information about this entity."""
        info = {
            "identifiers": {(DOMAIN, "unifi_speedtest")},
            "name": INTEGRATION_NAME,
            "manufacturer": "UniFi"
        }
        _LOGGER.debug(f"Device info for {self._name}: {info}")
        return info


class UniFiSpeedTestSensorMultiWAN(CoordinatorEntity, SensorEntity):
    """Sensor for UniFi Speed Test measurements with multi-WAN support."""
    
    def __init__(self, coordinator, name, data_key, interface_name, wan_group, wan_index, show_inactive_wans=False, config_entry_id=None):
        super().__init__(coordinator)
        self._name = name
        self._data_key = data_key
        self._interface_name = interface_name
        self._wan_group = str(wan_group)
        self._wan_index = wan_index  # Used only for ordinal display when explicit order unknown
        self._state = None
        self._wan_key = f"{self._interface_name}_{self._wan_group}"
        self._show_inactive_wans = show_inactive_wans
        self._config_entry_id = config_entry_id

        # Validate data_key to prevent unit_of_measurement errors
        if data_key not in ["download", "upload", "ping"]:
            _LOGGER.error(f"INVALID data_key '{data_key}' for Multi-WAN sensor {name}! Must be 'download', 'upload', or 'ping'")
        
        _LOGGER.info(f"Multi-WAN Sensor initialized: {self._name} ({self._data_key}) for {interface_name}/{wan_group}")

    def _find_my_wan_data(self):
        """Find the WAN data dict matching this sensor's interface/group in coordinator data."""
        data = self.coordinator.data
        if not data or 'wan_interfaces' not in data:
            return None, None
        for idx, wan in enumerate(data['wan_interfaces']):
            i_name = wan.get('interface_name') or wan.get('interface')
            w_group = str(wan.get('wan_networkgroup') or 'WAN')
            if i_name and f"{i_name}_{w_group}" == self._wan_key:
                return wan, idx
        # Fallback: try matching by interface only
        for idx, wan in enumerate(data['wan_interfaces']):
            if (wan.get('interface_name') or wan.get('interface')) == self._interface_name:
                return wan, idx
        return None, None

    def _determine_is_primary_wan(self, wan_data):
        """Determine if this WAN interface is the primary one using improved logic."""
        if not self.coordinator.data:
            return False
        primary_wan = self.coordinator.data.get('primary_wan')
        if not primary_wan:
            return False
        # Direct key comparison first
        if primary_wan == self._wan_key:
            return True
        # Backward compat: if primary is just interface name
        primary_interface = primary_wan.split('_')[0] if '_' in str(primary_wan) else primary_wan
        return primary_interface == self._interface_name

    @property
    def name(self) -> str:
        # Compact name: UniFi Speed Test Primary [WANx - ethX] DL/UL/Ping
        wan_data, _ = self._find_my_wan_data()
        group = self._wan_group
        iface = self._interface_name
        metric_suffix = {
            "download": "DL",
            "upload": "UL",
            "ping": "Ping",
        }.get(self._data_key, self._data_key)
        role = None
        if wan_data is not None:
            role = "Primary" if self._determine_is_primary_wan(wan_data) else "Secondary"
        prefix = f"UniFi Speed Test {role} " if role else "UniFi Speed Test "
        return f"{prefix}[{group} - {iface}] {metric_suffix}"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._data_key}_{self._interface_name}_{self._wan_group}"

    @property
    def state(self) -> StateType:
        """Get the state from multi-WAN data structure by matching interface/group, not by index."""
        data = self.coordinator.data
        if not data:
            return None
        # Prefer matching WAN by key
        wan_data, _ = self._find_my_wan_data()
        if wan_data is not None:
            value = wan_data.get(self._data_key)
            _LOGGER.debug(f"Getting multi-WAN state for {self._name}: {value}")
            return value
        # Fallback to legacy data structure
        value = data.get(self._data_key)
        _LOGGER.debug(f"Getting fallback state for {self._name}: {value}")
        return value

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement following Home Assistant standards."""
        if self._data_key in ["download", "upload"]:
            return "Mbit/s"
        elif self._data_key == "ping":
            return "ms"
        _LOGGER.error(f"Multi-WAN Sensor {self._name} with data_key '{self._data_key}' has no unit defined!")
        return "Mbit/s"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        if self._data_key in ["download", "upload"]:
            return SensorDeviceClass.DATA_RATE
        # Do not set device_class for ping since unit is ms, not seconds
        return None

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return True if entity is available (coordinator has data and WAN is active)."""
        # First check if coordinator has data
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return False
        
        # Always check WAN status regardless of show_inactive_wans setting
        # When show_inactive_wans=False, sensors won't be created for inactive WANs
        # When show_inactive_wans=True, all sensors are created but inactive ones show as unavailable
        
        # Get WAN status map from hass.data if available
        try:
            from homeassistant.core import HomeAssistant
            hass: HomeAssistant = self.hass
            wan_status_map = hass.data.get(DOMAIN, {}).get(f"{self._config_entry_id}_wan_status", {})
        except Exception:
            # If we can't get status map, assume available to avoid hiding legitimate WANs
            return True
        
        # Check if this WAN interface is active
        st = wan_status_map.get(self._interface_name)
        if not st:
            # Unknown status - assume available to avoid hiding legitimate WANs
            return True
        
        # Use the is_active flag if available (considers link, IP, speed, and traffic)
        if "is_active" in st:
            return st["is_active"]
        
        # Fallback: Active when link is up AND IP is present (not 0.x.x.x)
        if st.get('up') and (st.get('ip') and not str(st.get('ip')).startswith('0.')):
            return True
        
        # WAN is inactive/unassigned - mark as unavailable
        return False

    @property
    def suggested_display_precision(self) -> int | None:
        if self._data_key in ["download", "upload"]:
            return 2
        elif self._data_key == "ping":
            return 1
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes for multi-WAN sensors."""
        attributes = {
            "interface_name": self._interface_name,
            "wan_networkgroup": self._wan_group,
            "wan_number": self._wan_index + 1,
        }
        data = self.coordinator.data
        if data and 'wan_interfaces' in data:
            wan_data, idx = self._find_my_wan_data()
            if wan_data is not None:
                attributes.update({
                    "total_wan_interfaces": data.get('total_interfaces', len(data.get('wan_interfaces', [])) or 1),
                    "is_primary_wan": self._determine_is_primary_wan(wan_data),
                    "timestamp": wan_data.get('timestamp'),
                    "status": wan_data.get('status', 'unknown'),
                    "wan_index": (idx + 1) if idx is not None else self._wan_index + 1,
                })
        return attributes

    @property
    def device_info(self):
        """Return device information about this entity."""
        data = self.coordinator.data
        group = self._wan_group
        iface = self._interface_name
        device_name = f"{INTEGRATION_NAME} {group} ({iface})"
        if data and 'wan_interfaces' in data:
            wan_data, _ = self._find_my_wan_data()
            if wan_data is not None:
                is_primary = self._determine_is_primary_wan(wan_data)
                role = 'Primary WAN' if is_primary else 'Secondary WAN'
                device_name = f"{INTEGRATION_NAME} {role} [{group} - {iface}]"
        return {
            "identifiers": {(DOMAIN, f"unifi_speedtest_{iface}_{group}")},
            "name": device_name,
            "manufacturer": "UniFi",
            "model": f"WAN Interface {iface}"
        }


class SpeedTestRunsSensor(SensorEntity):
    """Sensor to track speed test execution statistics."""
    
    def __init__(self, tracker: SpeedTestTracker, name: str):
        self._tracker = tracker
        self._name = name
        self._attr_unique_id = f"{DOMAIN}_speedtest_runs"
        self._attr_name = f"UniFi {name}"

    @property
    def state(self) -> StateType:
        """Return the total number of speed test attempts."""
        return self._tracker.total_attempts

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "runs"

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class for long-term statistics."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        return "mdi:speedometer"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "successful_runs": self._tracker.successful_runs,
            "failed_runs": self._tracker.failed_runs,
            "success_rate": self._tracker.success_rate,
            "automated_attempts": self._tracker.automated_attempts,
            "manual_attempts": self._tracker.manual_attempts,
            "automated_successes": self._tracker.automated_successes,
            "manual_successes": self._tracker.manual_successes,
            "automated_failures": self._tracker.automated_failures,
            "manual_failures": self._tracker.manual_failures,
            "automated_success_rate": self._tracker.automated_success_rate,
            "last_run_time": self._tracker.last_run_time.isoformat() if self._tracker.last_run_time else None,
            "last_success_time": self._tracker.last_success_time.isoformat() if self._tracker.last_success_time else None,
            "last_failure_time": self._tracker.last_failure_time.isoformat() if self._tracker.last_failure_time else None,
            "last_automated_run": self._tracker.last_automated_run.isoformat() if self._tracker.last_automated_run else None,
            "last_manual_run": self._tracker.last_manual_run.isoformat() if self._tracker.last_manual_run else None,
            "last_failure_reason": self._tracker.last_failure_reason,
            "recent_failures": self._tracker.failure_reasons[-5:] if self._tracker.failure_reasons else []  # Last 5 failures
        }

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, "unifi_speedtest")},
            "name": INTEGRATION_NAME,
            "manufacturer": "UniFi"
        }


class UniFiAPIHealthSensor(SensorEntity):
    """Sensor to monitor UniFi API health and rate limiting status."""
    
    def __init__(self, api: UniFiAPIBase, name: str):
        self._api = api
        self._name = name
        self._attr_unique_id = f"{DOMAIN}_api_health"
        self._attr_name = f"UniFi {name}"
        # Cache controller info at init to avoid blocking calls in properties
        self._controller_type = api.controller_type
        self._controller_site = api.site

    @property
    def state(self) -> StateType:
        """Return the API health status."""
        try:
            health = self._api.get_health_status()
            if health.get('in_cooldown', False):
                return "cooldown"
            elif health.get('consecutive_403s', 0) > 3:
                return "rate_limited"
            elif health.get('can_connect', True):
                return "healthy"
            else:
                return "unhealthy"
        except Exception:
            return "error"

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        state = self.state
        if state == "healthy":
            return "mdi:check-circle"
        elif state == "cooldown":
            return "mdi:clock-alert"
        elif state == "rate_limited":
            return "mdi:speedometer-slow"
        else:
            return "mdi:alert-circle"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        try:
            health = self._api.get_health_status()
            # Use cached controller info instead of calling get_controller_info()
            # which may make blocking HTTP requests for some controller types
            return {
                **health,
                "controller_type": self._controller_type,
                "controller_site": self._controller_site,
                "rate_limit_backoff": 0
            }
        except Exception as e:
            return {"error": str(e)}

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, "unifi_speedtest")},
            "name": INTEGRATION_NAME,
            "manufacturer": "UniFi"
        }
