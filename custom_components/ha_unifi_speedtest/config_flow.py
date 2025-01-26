from homeassistant import config_entries
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import (
    DOMAIN, 
    INTEGRATION_NAME,
    CONF_URL, 
    CONF_USERNAME, 
    CONF_PASSWORD, 
    CONF_SITE, 
    CONF_VERIFY_SSL
)
from .api import UniFiAPI

class UniFiSpeedTestConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Unifi Speedtest."""
    VERSION = 1
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            try:
                # Attempt to login and validate credentials
                api = UniFiAPI(
                    user_input[CONF_URL], 
                    user_input[CONF_USERNAME], 
                    user_input[CONF_PASSWORD],
                    site=user_input.get(CONF_SITE, 'default'),
                    verify_ssl=user_input.get(CONF_VERIFY_SSL, False)
                )
                await self.hass.async_add_executor_job(api.login)
                
                return self.async_create_entry(
                    title=f"{INTEGRATION_NAME} ({user_input[CONF_URL]})", 
                    data={
                        CONF_URL: user_input[CONF_URL],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SITE: user_input.get(CONF_SITE, 'default'),
                        CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False)
                    }
                )
            except Exception as e:
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_SITE, default='default'): str,
                vol.Optional(CONF_VERIFY_SSL, default=False): bool
            }),
            errors=errors
        )

async def async_get_options_flow(config_entry):
    """Get the options flow for this handler."""
    return UniFiSpeedTestOptionsFlow(config_entry)

class UniFiSpeedTestOptionsFlow(config_entries.OptionsFlow):
    """Options flow for HA Unifi Speedtest."""
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SITE, 
                    default=self.config_entry.data.get(CONF_SITE, 'default')
                ): str,
                vol.Optional(
                    CONF_VERIFY_SSL, 
                    default=self.config_entry.data.get(CONF_VERIFY_SSL, False)
                ): bool
            })
        )
