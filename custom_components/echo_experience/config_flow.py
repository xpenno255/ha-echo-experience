"""Install the shared dashboard service; devices live in echo_experience.json."""
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
import voluptuous as vol
from .core import validate_profiles
import json

class EchoExperienceFlow(ConfigFlow, domain='echo_experience'):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id('echo_experience')
        self._abort_if_unique_id_configured()
        if user_input is not None:
            try:
                def read():
                    with open(self.hass.config.path('echo_experience.json')) as f:
                        return validate_profiles(json.load(f))
                await self.hass.async_add_executor_job(read)
            except (OSError, ValueError, KeyError):
                return self.async_show_form(step_id='user', errors={'base':'invalid_profiles'})
            return self.async_create_entry(title='Echo Experience',data={},options={'manage_dashboard':True})
        return self.async_show_form(step_id='user')

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EchoExperienceOptions()

class EchoExperienceOptions(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title='',data=user_input)
        current=self.config_entry.options.get('manage_dashboard',True)
        return self.async_show_form(step_id='init',data_schema=vol.Schema({vol.Required('manage_dashboard',default=current):bool}))
