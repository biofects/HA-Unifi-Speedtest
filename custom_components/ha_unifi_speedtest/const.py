"""Constants for HA UniFi Speedtest integration."""

DOMAIN = "ha_unifi_speedtest"
INTEGRATION_NAME = "HA Unifi Speedtest"

# Configuration keys
CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_SITE = "site"
CONF_VERIFY_SSL = "verify_ssl"
CONF_HAS_ADMIN = "has_admin_access"  # Whether user has admin privileges
CONF_ENABLE_SCHEDULING = "enable_scheduling"
CONF_SCHEDULE_INTERVAL = "schedule_interval"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_ENABLE_MULTI_WAN = "enable_multi_wan"  # New configuration for multi-WAN support
CONF_SHOW_INACTIVE_WAN = "show_inactive_wans"
CONF_RUN_SPEEDTEST_ON_STARTUP = "run_speedtest_on_startup"  # Run initial speedtest after HA starts

# Service names
SERVICE_START_SPEED_TEST = "start_speed_test"
SERVICE_GET_SPEED_TEST_STATUS = "get_speed_test_status"
SERVICE_GET_WAN_INTERFACES = "get_wan_interfaces"

# Default values - Conservative settings to prevent 403 errors
DEFAULT_HAS_ADMIN = True  # Assume admin access by default for backward compatibility
DEFAULT_SCHEDULE_INTERVAL = 90  # 90 minutes (conservative to avoid rate limiting)
DEFAULT_ENABLE_SCHEDULING = True
DEFAULT_POLLING_INTERVAL = 30  # 30 minutes (auto-calculated when not specified)
DEFAULT_ENABLE_MULTI_WAN = True  # Enable multi-WAN detection by default
DEFAULT_SHOW_INACTIVE_WAN = False
DEFAULT_RUN_SPEEDTEST_ON_STARTUP = False  # Don't run speedtest on startup by default to improve load time

# Rate limiting constants
MIN_SCHEDULE_INTERVAL = 15  # Minimum 15 minutes between speed tests
MAX_SCHEDULE_INTERVAL = 1440  # Maximum 24 hours
MIN_POLLING_INTERVAL = 10  # Minimum 10 minutes between data polling
MAX_POLLING_INTERVAL = 240  # Maximum 4 hours

# Error codes for better user experience
ERROR_MESSAGES = {
    "cannot_connect": "Unable to connect to UniFi Controller. Check URL and network connectivity.",
    "access_denied": "Access denied (403). This often indicates rate limiting or incorrect permissions. Try increasing intervals or check credentials.",
    "timeout": "Connection timeout. Check if the controller is accessible and responsive.",
    "unknown_error": "An unexpected error occurred. Check logs for details.",
    "polling_too_frequent": "Data polling interval must be less than the speed test interval to avoid conflicts and rate limiting."
}
