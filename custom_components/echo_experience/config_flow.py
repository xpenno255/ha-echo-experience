"""Install the shared dashboard service; devices live in echo_experience.json."""
from homeassistant.config_entries import ConfigFlow
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
            return self.async_create_entry(title='Echo Experience',data={})
        return self.async_show_form(step_id='user')
