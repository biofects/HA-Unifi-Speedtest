"""Config flow for HA UniFi Speedtest integration."""
from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol
import logging

from .const import (
    DOMAIN, 
    INTEGRATION_NAME,
    CONF_URL, 
    CONF_USERNAME, 
    CONF_PASSWORD,
    CONF_API_KEY,
    CONF_SITE, 
    CONF_VERIFY_SSL,
    CONF_CONTROLLER_TYPE,
    CONF_ENABLE_SCHEDULING,
    CONF_SCHEDULE_INTERVAL,
    CONF_POLLING_INTERVAL,
    CONF_ENABLE_MULTI_WAN,
    CONF_SHOW_INACTIVE_WAN,
    CONF_RUN_SPEEDTEST_ON_STARTUP,
    DEFAULT_SCHEDULE_INTERVAL,
    DEFAULT_ENABLE_SCHEDULING,
    DEFAULT_ENABLE_MULTI_WAN,
    DEFAULT_SHOW_INACTIVE_WAN,
    DEFAULT_RUN_SPEEDTEST_ON_STARTUP
)
from .api_factory import create_unifi_api

_LOGGER = logging.getLogger(__name__)


def calculate_polling_interval(schedule_interval: int) -> int:
    """Calculate optimal polling interval based on speed test schedule."""
    if schedule_interval <= 30:
        return max(10, schedule_interval // 3)
    elif schedule_interval <= 60:
        return max(15, schedule_interval // 2)
    else:
        return max(20, schedule_interval // 3)


class UniFiSpeedTestConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Unifi Speedtest."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize config flow."""
        self.controller_type = None
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return UniFiSpeedTestOptionsFlow(config_entry)
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step - select controller type."""
        _LOGGER.info("Config flow step 1: Controller type selection")
        
        if user_input is not None:
            self.controller_type = user_input[CONF_CONTROLLER_TYPE]
            _LOGGER.info(f"Controller type selected: {self.controller_type}")
            return await self.async_step_credentials()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_TYPE, default='udm'): vol.In({
                    'udm': 'UDM Pro/SE/Cloud Key Gen2+',
                    'controller': 'Self-hosted Network Application'
                }),
            }),
            description_placeholders={
                "info": "Select your UniFi controller type"
            }
        )

    async def async_step_credentials(self, user_input=None):
        """Handle credentials based on controller type."""
        errors = {}
        _LOGGER.info(f"Config flow step 2: Credentials for {self.controller_type}")
        
        if user_input is not None:
            _LOGGER.info("Credentials received, validating...")
            try:
                api_args = {
                    "url": user_input[CONF_URL],
                    "site": user_input.get(CONF_SITE, 'default'),
                    "verify_ssl": user_input.get(CONF_VERIFY_SSL, False),
                    "controller_type": self.controller_type,
                    "enable_multi_wan": user_input.get(CONF_ENABLE_MULTI_WAN, DEFAULT_ENABLE_MULTI_WAN),
                }
                
                if self.controller_type == 'udm':
                    api_args["api_key"] = user_input[CONF_API_KEY]
                else:
                    api_args["username"] = user_input[CONF_USERNAME]
                    api_args["password"] = user_input[CONF_PASSWORD]
                
                api = await self.hass.async_add_executor_job(
                    lambda: create_unifi_api(**api_args)
                )
                
                if self.controller_type == 'controller':
                    await self.hass.async_add_executor_job(api.login)
                
                connection_ok = await self.hass.async_add_executor_job(api.test_connection)
                if not connection_ok:
                    raise Exception("Connection test failed")
                
                _LOGGER.info("Connection test successful")
                
                controller_info = await self.hass.async_add_executor_job(api.get_controller_info)
                controller_type_display = controller_info.get('type', 'UniFi').upper()
                
                schedule_interval = user_input.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
                enable_scheduling = user_input.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
                polling_interval = calculate_polling_interval(schedule_interval) if enable_scheduling else 30
                
                entry_data = {
                    CONF_URL: user_input[CONF_URL],
                    CONF_SITE: user_input.get(CONF_SITE, 'default'),
                    CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False),
                    CONF_CONTROLLER_TYPE: self.controller_type,
                    CONF_ENABLE_SCHEDULING: enable_scheduling,
                    CONF_SCHEDULE_INTERVAL: schedule_interval,
                    CONF_POLLING_INTERVAL: polling_interval,
                    CONF_ENABLE_MULTI_WAN: user_input.get(CONF_ENABLE_MULTI_WAN, DEFAULT_ENABLE_MULTI_WAN),
                    CONF_SHOW_INACTIVE_WAN: user_input.get(CONF_SHOW_INACTIVE_WAN, DEFAULT_SHOW_INACTIVE_WAN),
                }
                
                if self.controller_type == 'udm':
                    entry_data[CONF_API_KEY] = user_input[CONF_API_KEY]
                else:
                    entry_data[CONF_USERNAME] = user_input[CONF_USERNAME]
                    entry_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
                
                return self.async_create_entry(
                    title=f"{INTEGRATION_NAME} ({controller_type_display})", 
                    data=entry_data
                )
                
            except Exception as e:
                _LOGGER.error(f"Configuration validation failed: {e}")
                error_str = str(e).lower()
                
                # Check for credential-related errors
                if "api key is required" in error_str or "api_key" in error_str:
                    errors["base"] = "invalid_auth"
                    _LOGGER.error("API key required for UDM/UniFi OS controllers. Self-hosted controllers should use username/password.")
                elif "username and password" in error_str:
                    errors["base"] = "invalid_auth"
                    _LOGGER.error("Username and password required for self-hosted software controllers.")
                elif "403" in str(e) or "forbidden" in error_str:
                    errors["base"] = "access_denied"
                elif "401" in str(e) or "unauthorized" in error_str:
                    errors["base"] = "invalid_auth"
                elif "timeout" in error_str:
                    errors["base"] = "timeout"
                elif "connect" in error_str:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown_error"
        
        schema_dict = {
            vol.Required(CONF_URL): str,
        }
        
        if self.controller_type == 'udm':
            schema_dict[vol.Required(CONF_API_KEY)] = str
        else:
            schema_dict[vol.Required(CONF_USERNAME)] = str
            schema_dict[vol.Required(CONF_PASSWORD)] = str
        
        schema_dict.update({
            vol.Optional(CONF_SITE, default='default'): str,
            vol.Optional(CONF_VERIFY_SSL, default=False): bool,
            vol.Optional(CONF_ENABLE_SCHEDULING, default=DEFAULT_ENABLE_SCHEDULING): bool,
            vol.Optional(CONF_SCHEDULE_INTERVAL, default=DEFAULT_SCHEDULE_INTERVAL): vol.All(int, vol.Range(min=15, max=1440)),
            vol.Optional(CONF_RUN_SPEEDTEST_ON_STARTUP, default=DEFAULT_RUN_SPEEDTEST_ON_STARTUP): bool,
        })
        
        if self.controller_type == 'udm':
            schema_dict[vol.Optional(CONF_ENABLE_MULTI_WAN, default=DEFAULT_ENABLE_MULTI_WAN)] = bool
            schema_dict[vol.Optional(CONF_SHOW_INACTIVE_WAN, default=DEFAULT_SHOW_INACTIVE_WAN)] = bool
        
        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )


class UniFiSpeedTestOptionsFlow(config_entries.OptionsFlow):
    """Options flow for HA Unifi Speedtest."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Don't set self.config_entry - parent class provides it automatically
        # This avoids deprecated warning while accepting the required parameter
        super().__init__()

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        
        if user_input is not None:
            schedule_interval = user_input.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
            enable_scheduling = user_input.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
            polling_interval = calculate_polling_interval(schedule_interval) if enable_scheduling else 30
            user_input[CONF_POLLING_INTERVAL] = polling_interval
            
            # Check if we need to reload BEFORE creating entry
            current_enable = self.config_entry.options.get(
                CONF_ENABLE_SCHEDULING, 
                self.config_entry.data.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
            )
            current_interval = self.config_entry.options.get(
                CONF_SCHEDULE_INTERVAL,
                self.config_entry.data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
            )
            current_show_inactive = self.config_entry.options.get(
                CONF_SHOW_INACTIVE_WAN,
                self.config_entry.data.get(CONF_SHOW_INACTIVE_WAN, DEFAULT_SHOW_INACTIVE_WAN)
            )
            new_show_inactive = user_input.get(CONF_SHOW_INACTIVE_WAN, DEFAULT_SHOW_INACTIVE_WAN)
            
            needs_reload = (current_enable != enable_scheduling or 
                           current_interval != schedule_interval or 
                           current_show_inactive != new_show_inactive)
            
            result = self.async_create_entry(title="", data=user_input)
            
            # Reload AFTER entry is created if settings changed
            # Use async_call_later to ensure options are saved first
            if needs_reload:
                async def _reload_entry(_now):
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                from homeassistant.helpers.event import async_call_later
                async_call_later(self.hass, 1, _reload_entry)
            
            return result
        
        current_site = self.config_entry.options.get(
            CONF_SITE, self.config_entry.data.get(CONF_SITE, 'default')
        )
        current_verify_ssl = self.config_entry.options.get(
            CONF_VERIFY_SSL, self.config_entry.data.get(CONF_VERIFY_SSL, False)
        )
        current_controller_type = self.config_entry.data.get(CONF_CONTROLLER_TYPE, 'udm')
        current_enable_scheduling = self.config_entry.options.get(
            CONF_ENABLE_SCHEDULING,
            self.config_entry.data.get(CONF_ENABLE_SCHEDULING, DEFAULT_ENABLE_SCHEDULING)
        )
        current_schedule_interval = self.config_entry.options.get(
            CONF_SCHEDULE_INTERVAL,
            self.config_entry.data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
        )
        current_enable_multi_wan = self.config_entry.options.get(
            CONF_ENABLE_MULTI_WAN,
            self.config_entry.data.get(CONF_ENABLE_MULTI_WAN, DEFAULT_ENABLE_MULTI_WAN)
        )
        current_show_inactive_wan = self.config_entry.options.get(
            CONF_SHOW_INACTIVE_WAN,
            self.config_entry.data.get(CONF_SHOW_INACTIVE_WAN, DEFAULT_SHOW_INACTIVE_WAN)
        )
        current_run_speedtest_on_startup = self.config_entry.options.get(
            CONF_RUN_SPEEDTEST_ON_STARTUP,
            self.config_entry.data.get(CONF_RUN_SPEEDTEST_ON_STARTUP, DEFAULT_RUN_SPEEDTEST_ON_STARTUP)
        )
        
        schema_dict = {
            vol.Optional(CONF_SITE, default=current_site): str,
            vol.Optional(CONF_VERIFY_SSL, default=current_verify_ssl): bool,
            vol.Optional(CONF_ENABLE_SCHEDULING, default=current_enable_scheduling): bool,
            vol.Optional(CONF_SCHEDULE_INTERVAL, default=current_schedule_interval): vol.All(int, vol.Range(min=15, max=1440)),
            vol.Optional(CONF_RUN_SPEEDTEST_ON_STARTUP, default=current_run_speedtest_on_startup): bool,
        }
        
        if current_controller_type == 'udm':
            schema_dict[vol.Optional(CONF_ENABLE_MULTI_WAN, default=current_enable_multi_wan)] = bool
            schema_dict[vol.Optional(CONF_SHOW_INACTIVE_WAN, default=current_show_inactive_wan)] = bool
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
