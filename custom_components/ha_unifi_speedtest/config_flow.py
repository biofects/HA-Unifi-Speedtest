from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol
import logging

from .const import (
    DOMAIN, 
    INTEGRATION_NAME,
    CONF_URL, 
    CONF_USERNAME, 
    CONF_PASSWORD, 
    CONF_SITE, 
    CONF_VERIFY_SSL,
    CONF_CONTROLLER_TYPE,
    CONF_ENABLE_SCHEDULING,
    CONF_SCHEDULE_INTERVAL,
    CONF_POLLING_INTERVAL,
    DEFAULT_SCHEDULE_INTERVAL,
    DEFAULT_ENABLE_SCHEDULING,
    DEFAULT_POLLING_INTERVAL
)
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

class UniFiSpeedTestConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Unifi Speedtest."""
    VERSION = 1
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return UniFiSpeedTestOptionsFlow(config_entry)
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        _LOGGER.info("Starting config flow: async_step_user")
        
        if user_input is not None:
            _LOGGER.info(f"User input received: {user_input}")
            try:
                schedule_interval = user_input.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
                enable_scheduling = user_input.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
                
                # Auto-calculate polling interval
                polling_interval = calculate_polling_interval(schedule_interval) if enable_scheduling else 30
                
                # Attempt to login and validate credentials
                api = UniFiAPI(
                    user_input[CONF_URL], 
                    user_input[CONF_USERNAME], 
                    user_input[CONF_PASSWORD],
                    site=user_input.get(CONF_SITE, 'default'),
                    verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
                    controller_type=user_input.get(CONF_CONTROLLER_TYPE, 'udm')
                )
                _LOGGER.info("Attempting API login...")
                await self.hass.async_add_executor_job(api.login)
                _LOGGER.info("API login successful.")
                
                # Get controller info for the title
                controller_info = api.get_controller_info()
                controller_type_display = controller_info['type'].upper() if controller_info['type'] else 'UniFi'
                
                return self.async_create_entry(
                    title=f"{INTEGRATION_NAME} ({controller_type_display})", 
                    data={
                        CONF_URL: user_input[CONF_URL],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SITE: user_input.get(CONF_SITE, 'default'),
                        CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False),
                        CONF_CONTROLLER_TYPE: user_input.get(CONF_CONTROLLER_TYPE, 'udm'),
                        CONF_ENABLE_SCHEDULING: enable_scheduling,
                        CONF_SCHEDULE_INTERVAL: schedule_interval,
                        CONF_POLLING_INTERVAL: polling_interval  # Auto-calculated
                    }
                )
            except Exception as e:
                _LOGGER.error(f"API login failed: {e}")
                if "403" in str(e) or "forbidden" in str(e).lower():
                    errors["base"] = "access_denied"
                elif "timeout" in str(e).lower():
                    errors["base"] = "timeout"
                elif "connection" in str(e).lower():
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown_error"
        else:
            _LOGGER.info("No user input yet, showing form.")
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL, description="UniFi Controller URL (e.g., https://your-udm.local)"): str,
                vol.Required(CONF_USERNAME, description="UniFi Controller Username"): str,
                vol.Required(CONF_PASSWORD, description="UniFi Controller Password"): str,
                vol.Optional(CONF_SITE, default='default', description="UniFi Site Name"): str,
                vol.Optional(CONF_VERIFY_SSL, default=False, description="Verify SSL Certificate"): bool,
                vol.Optional(CONF_CONTROLLER_TYPE, default='udm', description="Controller Type"): vol.In(['udm', 'controller']),
                vol.Optional(CONF_ENABLE_SCHEDULING, default=DEFAULT_ENABLE_SCHEDULING, description="Enable Automatic Speed Tests"): bool,
                vol.Optional(
                    CONF_SCHEDULE_INTERVAL, 
                    default=DEFAULT_SCHEDULE_INTERVAL,
                    description="Speed Test Interval (minutes)"
                ): vol.All(int, vol.Range(min=15, max=1440)),  # 15 minutes to 24 hours
            }),
            errors=errors,
            description_placeholders={
                "controller_info": "Choose 'udm' for UDM Pro/Cloud Key Gen2, or 'controller' for traditional UniFi Controller.",
                "schedule_info": "Automatic speed tests run at regular intervals. Data polling is automatically optimized based on your speed test frequency to avoid rate limiting.",
                "rate_limit_warning": "⚠️ Setting intervals too low may cause 403 rate limit errors. Recommended: Speed tests every 60+ minutes minimum.",
                "polling_info": "📊 Data polling interval is automatically calculated to be optimal for your speed test schedule and prevent rate limiting."
            }
        )

class UniFiSpeedTestOptionsFlow(config_entries.OptionsFlow):
    """Options flow for HA Unifi Speedtest."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        # Modern approach: Don't manually set self.config_entry
        # The parent class provides it automatically through framework magic
        _LOGGER.info("Options flow initialized.")

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _LOGGER.info("Options flow step: init")
        errors = {}
        
        if user_input is not None:
            _LOGGER.info(f"Options input received: {user_input}")
            
            schedule_interval = user_input.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
            enable_scheduling = user_input.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
            
            # Auto-calculate polling interval
            polling_interval = calculate_polling_interval(schedule_interval) if enable_scheduling else 30
            
            # Add the calculated polling interval to the options
            user_input[CONF_POLLING_INTERVAL] = polling_interval
            
            # Get current values to check if reload is needed
            current_enable = self.config_entry.options.get(CONF_ENABLE_SCHEDULING, 
                                                         self.config_entry.data.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING))
            current_interval = self.config_entry.options.get(CONF_SCHEDULE_INTERVAL, 
                                                           self.config_entry.data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL))
            current_polling = self.config_entry.options.get(CONF_POLLING_INTERVAL, 
                                                          self.config_entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL))
            
            result = self.async_create_entry(title="", data=user_input)
            
            # If scheduling settings changed, we need to reload the entry
            if (current_enable != enable_scheduling or 
                current_interval != schedule_interval or 
                current_polling != polling_interval):
                _LOGGER.info("Scheduling settings changed, reloading integration...")
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )
            
            return result
        
        # Get current values from config entry data or options
        current_site = self.config_entry.options.get(CONF_SITE, 
                                                    self.config_entry.data.get(CONF_SITE, 'default'))
        current_verify_ssl = self.config_entry.options.get(CONF_VERIFY_SSL, 
                                                          self.config_entry.data.get(CONF_VERIFY_SSL, False))
        current_controller_type = self.config_entry.options.get(CONF_CONTROLLER_TYPE,
                                                              self.config_entry.data.get(CONF_CONTROLLER_TYPE, 'udm'))
        current_enable_scheduling = self.config_entry.options.get(CONF_ENABLE_SCHEDULING,
                                                                 self.config_entry.data.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING))
        current_schedule_interval = self.config_entry.options.get(CONF_SCHEDULE_INTERVAL,
                                                                 self.config_entry.data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL))
        current_polling_interval = self.config_entry.options.get(CONF_POLLING_INTERVAL,
                                                                self.config_entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL))

        _LOGGER.info("No options input yet, showing form.")
        
        # Calculate some helpful display values
        if current_enable_scheduling:
            tests_per_day = 1440 // current_schedule_interval  # 1440 minutes in a day
            calculated_polling = calculate_polling_interval(current_schedule_interval)
            status_msg = f"Currently: Speed tests every {current_schedule_interval} min (~{tests_per_day} tests/day), polling every {current_polling_interval} min (recommended: {calculated_polling} min)"
        else:
            status_msg = f"Currently: Scheduling disabled, polling every {current_polling_interval} min"
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SITE, default=current_site, description="UniFi Site Name"): str,
                vol.Optional(CONF_VERIFY_SSL, default=current_verify_ssl, description="Verify SSL Certificate"): bool,
                vol.Optional(CONF_CONTROLLER_TYPE, default=current_controller_type, description="Controller Type"): vol.In(['udm', 'controller']),
                vol.Optional(CONF_ENABLE_SCHEDULING, default=current_enable_scheduling, description="Enable Automatic Speed Tests"): bool,
                vol.Optional(
                    CONF_SCHEDULE_INTERVAL, 
                    default=current_schedule_interval,
                    description=f"Speed Test Interval (minutes) - Currently: {current_schedule_interval}"
                ): vol.All(int, vol.Range(min=15, max=1440)),
            }),
            errors=errors,
            description_placeholders={
                "current_status": status_msg,
                "auto_polling_info": (
                    "🔄 Polling Interval is Automatically Optimized:\n"
                    "• Based on your speed test frequency\n"
                    "• Prevents rate limiting and API conflicts\n"
                    "• Ensures reliable data collection"
                ),
                "interval_guidance": (
                    "📋 Interval Recommendations:\n"
                    "• Conservative: 120+ minutes (2+ hours)\n"
                    "• Balanced: 60-90 minutes (1-1.5 hours)\n"
                    "• Frequent: 30-45 minutes (may cause rate limiting)\n"
                    "• Minimum: 15 minutes (only for testing/debugging)"
                ),
                "rate_limit_info": (
                    "⚠️ Rate Limiting Protection:\n"
                    "The integration automatically handles rate limiting and backs off when needed. "
                    "If you experience 403 errors, increase the speed test interval. "
                    "Data polling is optimized automatically to prevent conflicts."
                ),
                "reload_warning": "⚡ Settings changes require integration reload which will happen automatically."
            }
        )
