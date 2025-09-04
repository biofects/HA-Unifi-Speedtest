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

from .const import DOMAIN, INTEGRATION_NAME, CONF_SCHEDULE_INTERVAL, CONF_ENABLE_SCHEDULING, CONF_POLLING_INTERVAL, CONF_ENABLE_MULTI_WAN
from .api import UniFiAPI

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
    _LOGGER.info("Setting up UniFi Speed Test sensors.")
    # Retrieve the API instance from hass.data
    api = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.info(f"API instance retrieved: {api}")

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
            
            return await hass.async_add_executor_job(api.get_speed_test_status)
            
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
    enable_scheduling = config_entry.options.get(CONF_ENABLE_SCHEDULING, 
                                               config_entry.data.get(CONF_ENABLE_SCHEDULING, True))
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
        _LOGGER.info(f"Setting up automatic speed tests for {api.controller_type} controller every {schedule_interval} minutes")
        _LOGGER.info(f"Data will be polled every {polling_interval} minutes")
        
        # Schedule the speed test at user-defined interval
        interval = timedelta(minutes=schedule_interval)
        remove_scheduled_listener = async_track_time_interval(hass, run_scheduled_speedtest, interval)
        _LOGGER.info(f"Speed test scheduled every {schedule_interval} minutes")

        # Store the listener removal function so we can clean it up later
        hass.data[DOMAIN][f"{config_entry.entry_id}_scheduled_listener"] = remove_scheduled_listener

        # Store intervals in data for reference
        hass.data[DOMAIN][f"{config_entry.entry_id}_schedule_interval"] = schedule_interval
        hass.data[DOMAIN][f"{config_entry.entry_id}_polling_interval"] = polling_interval
    else:
        _LOGGER.info(f"Automatic speed test scheduling disabled for {api.controller_type} controller")
        _LOGGER.info(f"Data will be polled every {polling_interval} minutes")

    _LOGGER.info("Coordinator created, refreshing config entry.")
    await coordinator.async_config_entry_first_refresh()

    # Check if multi-WAN is enabled and create appropriate sensors
    enable_multi_wan = config_entry.options.get(CONF_ENABLE_MULTI_WAN, 
                                               config_entry.data.get(CONF_ENABLE_MULTI_WAN, True))
    
    sensors = []
    
    if enable_multi_wan:
        # Check if we have multi-WAN data
        coordinator_data = coordinator.data
        if (coordinator_data and 
            isinstance(coordinator_data, dict) and 
            'multi_wan_enabled' in coordinator_data and 
            coordinator_data.get('wan_interfaces')):
            
            # Create sensors for each WAN interface
            wan_interfaces = coordinator_data['wan_interfaces']
            _LOGGER.info(f"Creating sensors for {len(wan_interfaces)} WAN interface(s)")
            
            for i, wan_interface in enumerate(wan_interfaces, 1):
                interface_name = wan_interface.get('interface_name', f'wan{i}')
                wan_group = wan_interface.get('wan_networkgroup', f'WAN{i}')
                
                sensors.extend([
                    UniFiSpeedTestSensorMultiWAN(coordinator, f"Download Speed {wan_group}", "download", interface_name, wan_group, i-1),
                    UniFiSpeedTestSensorMultiWAN(coordinator, f"Upload Speed {wan_group}", "upload", interface_name, wan_group, i-1),
                    UniFiSpeedTestSensorMultiWAN(coordinator, f"Ping {wan_group}", "ping", interface_name, wan_group, i-1),
                ])
        else:
            # Fallback to legacy sensors if no multi-WAN data available
            _LOGGER.info("Multi-WAN enabled but no multi-WAN data found, creating legacy sensors")
            sensors.extend([
                UniFiSpeedTestSensor(coordinator, "Download Speed", "download"),
                UniFiSpeedTestSensor(coordinator, "Upload Speed", "upload"),
                UniFiSpeedTestSensor(coordinator, "Ping", "ping"),
            ])
    else:
        # Create legacy sensors
        _LOGGER.info("Multi-WAN disabled, creating legacy sensors")
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
        _LOGGER.debug(f"Getting state for {self._name}: {value}")
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
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class for the sensor."""
        if self._data_key in ["download", "upload"]:
            return SensorDeviceClass.DATA_RATE
        elif self._data_key == "ping":
            return SensorDeviceClass.DURATION
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
    
    def __init__(self, coordinator, name, data_key, interface_name, wan_group, wan_index):
        super().__init__(coordinator)
        self._name = name
        self._data_key = data_key
        self._interface_name = interface_name
        self._wan_group = wan_group
        self._wan_index = wan_index
        self._state = None
        _LOGGER.info(f"Multi-WAN Sensor initialized: {self._name} ({self._data_key}) for {interface_name}/{wan_group}")

    @property
    def name(self) -> str:
        return f"UniFi Speed Test {self._name}"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._data_key}_{self._interface_name}_{self._wan_group}"

    @property
    def state(self) -> StateType:
        """Get the state from multi-WAN data structure."""
        if not self.coordinator.data:
            return None
            
        # Handle multi-WAN data structure
        if ('wan_interfaces' in self.coordinator.data and 
            self._wan_index < len(self.coordinator.data['wan_interfaces'])):
            wan_data = self.coordinator.data['wan_interfaces'][self._wan_index]
            value = wan_data.get(self._data_key)
            _LOGGER.debug(f"Getting multi-WAN state for {self._name}: {value}")
            return value
            
        # Fallback to legacy data structure
        value = self.coordinator.data.get(self._data_key)
        _LOGGER.debug(f"Getting fallback state for {self._name}: {value}")
        return value

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement following Home Assistant standards."""
        if self._data_key in ["download", "upload"]:
            return "Mbit/s"
        elif self._data_key == "ping":
            return "ms"
        return None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class for the sensor."""
        if self._data_key in ["download", "upload"]:
            return SensorDeviceClass.DATA_RATE
        elif self._data_key == "ping":
            return SensorDeviceClass.DURATION
        return None

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class for long-term statistics."""
        return SensorStateClass.MEASUREMENT

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision."""
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
        
        # Add additional WAN interface data if available
        if (self.coordinator.data and 
            'wan_interfaces' in self.coordinator.data and 
            self._wan_index < len(self.coordinator.data['wan_interfaces'])):
            wan_data = self.coordinator.data['wan_interfaces'][self._wan_index]
            
            attributes.update({
                "total_wan_interfaces": self.coordinator.data.get('total_interfaces', 1),
                "is_primary_wan": self._determine_is_primary_wan(wan_data),
                "timestamp": wan_data.get('timestamp'),
                "status": wan_data.get('status', 'unknown')
            })
        
        return attributes

    def _determine_is_primary_wan(self, wan_data):
        """Determine if this WAN interface is the primary one using improved logic."""
        if not self.coordinator.data:
            return False
            
        # Get the primary WAN identifier from coordinator data
        primary_wan = self.coordinator.data.get('primary_wan')
        if not primary_wan:
            return False
        
        # Method 1: Direct key match
        current_wan_key = f"{self._interface_name}_{self._wan_group}"
        if current_wan_key == primary_wan:
            return True
            
        # Method 2: Interface name match (backward compatibility)
        interface_name = wan_data.get('interface_name', self._interface_name)
        primary_interface = primary_wan.split('_')[0] if '_' in primary_wan else primary_wan
        
        if interface_name == primary_interface:
            return True
            
        # Method 3: Check if this is the first WAN and no clear primary was determined
        wan_interfaces = self.coordinator.data.get('wan_interfaces', [])
        if (len(wan_interfaces) > 0 and 
            self._wan_index == 0 and 
            primary_wan == list(self.coordinator.data.get('wan_interfaces', [{}]))[0].get('interface_name')):
            return True
            
        return False

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, f"unifi_speedtest_{self._wan_group}")},
            "name": f"{INTEGRATION_NAME} {self._wan_group}",
            "manufacturer": "UniFi",
            "model": f"WAN Interface {self._interface_name}",
            "via_device": (DOMAIN, "unifi_speedtest")
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
    
    def __init__(self, api: UniFiAPI, name: str):
        self._api = api
        self._name = name
        self._attr_unique_id = f"{DOMAIN}_api_health"
        self._attr_name = f"UniFi {name}"

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
            controller_info = self._api.get_controller_info()
            return {
                **health,
                "controller_type": controller_info.get('type'),
                "controller_site": controller_info.get('site'),
                "rate_limit_backoff": controller_info.get('rate_limit_backoff', 0)
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
