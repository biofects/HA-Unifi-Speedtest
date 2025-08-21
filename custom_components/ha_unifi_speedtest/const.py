"""Constants for HA UniFi Speedtest integration."""

DOMAIN = "ha_unifi_speedtest"
INTEGRATION_NAME = "HA Unifi Speedtest"
DEFAULT_NAME = "HA Unifi Speedtest"

# Platforms supported by this integration
PLATFORMS = ["sensor"]

# Configuration keys
CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SITE = "site"
CONF_VERIFY_SSL = "verify_ssl"
CONF_CONTROLLER_TYPE = "controller_type"
CONF_ENABLE_SCHEDULING = "enable_scheduling"
CONF_SCHEDULE_INTERVAL = "schedule_interval"
CONF_POLLING_INTERVAL = "polling_interval"

# Service names
SERVICE_START_SPEED_TEST = "start_speed_test"
SERVICE_GET_SPEED_TEST_STATUS = "get_speed_test_status"

# Default values - Conservative settings to prevent 403 errors
DEFAULT_SCHEDULE_INTERVAL = 90  # 90 minutes (conservative to avoid rate limiting)
DEFAULT_ENABLE_SCHEDULING = True
DEFAULT_POLLING_INTERVAL = 30  # 30 minutes (auto-calculated when not specified)

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

# Polling interval calculation presets based on speed test frequency
def get_polling_calculation_info(schedule_interval: int) -> dict:
    """Get information about how polling interval is calculated."""
    if schedule_interval <= 30:
        calculated = max(10, schedule_interval // 3)
        description = "Very frequent speed tests - minimal polling to prevent conflicts"
    elif schedule_interval <= 60:
        calculated = max(15, schedule_interval // 2) 
        description = "Moderate frequency - balanced polling interval"
    else:
        calculated = max(20, schedule_interval // 3)
        description = "Conservative frequency - optimized polling interval"
    
    return {
        "calculated_interval": calculated,
        "description": description,
        "ratio": f"1:{schedule_interval//calculated if calculated > 0 else 1}"
    }

# Recommended interval presets for different use cases
INTERVAL_PRESETS = {
    "conservative": {
        "schedule": 120,  # 2 hours
        "description": "Conservative settings to minimize API calls and avoid rate limiting",
        "use_case": "24/7 monitoring with minimal controller load"
    },
    "balanced": {
        "schedule": 60,   # 1 hour  
        "description": "Balanced settings for regular monitoring with reasonable API usage",
        "use_case": "Regular monitoring during business hours"
    },
    "frequent": {
        "schedule": 30,   # 30 minutes
        "description": "More frequent monitoring - may trigger rate limiting on some controllers",
        "use_case": "Active troubleshooting or performance monitoring"
    },
    "debug": {
        "schedule": 15,   # 15 minutes
        "description": "For debugging only - likely to trigger rate limiting",
        "use_case": "Short-term testing and debugging only"
    }
}

# Auto-calculation examples for user reference
POLLING_EXAMPLES = {
    15: {"polling": 10, "note": "Minimum intervals - debug use only"},
    30: {"polling": 15, "note": "Frequent monitoring - watch for rate limits"},
    60: {"polling": 20, "note": "Balanced approach - good for regular use"},
    90: {"polling": 30, "note": "Conservative default - reliable operation"},
    120: {"polling": 40, "note": "Conservative monitoring - minimal controller load"},
    180: {"polling": 60, "note": "Very conservative - minimal impact"}
}
