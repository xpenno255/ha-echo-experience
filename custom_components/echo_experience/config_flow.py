"""Install the shared dashboard service; devices live in echo_experience.json."""
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
import voluptuous as vol
from .core import validate_profiles, MUSIC_STYLES, MUSIC_STYLES_OPTION, music_style, stored_music_styles
import json

def read_profiles(hass):
    with open(hass.config.path('echo_experience.json')) as f:
        return validate_profiles(json.load(f))['devices']

class EchoExperienceFlow(ConfigFlow, domain='echo_experience'):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id('echo_experience')
        self._abort_if_unique_id_configured()
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(read_profiles,self.hass)
            except (OSError, ValueError, KeyError):
                return self.async_show_form(step_id='user', errors={'base':'invalid_profiles'})
            return self.async_create_entry(title='Echo Experience',data={},options={'manage_dashboard':True})
        return self.async_show_form(step_id='user')

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EchoExperienceOptions()

class EchoExperienceOptions(OptionsFlow):
    """Dashboard management, then the music background for one chosen Echo. Other stored options are kept."""
    def __init__(self):
        self._profiles=None
        self._pending={}

    async def _load_profiles(self):
        if self._profiles is None:
            try:self._profiles=await self.hass.async_add_executor_job(read_profiles,self.hass)
            except (OSError, ValueError, KeyError, TypeError):self._profiles=[]
        return self._profiles

    def _save(self, **changes):
        return self.async_create_entry(title='',data={**self.config_entry.options,**changes})

    async def async_step_init(self, user_input=None):
        profiles=await self._load_profiles()
        ids=[p['id'] for p in profiles]
        if user_input is not None:
            manage=bool(user_input.get('manage_dashboard',True))
            device=user_input.get('device')
            # Without readable profiles there is no Echo to style; still let dashboard management change.
            if not profiles:return self._save(manage_dashboard=manage)
            if device not in ids:
                return self.async_show_form(step_id='init',data_schema=self._init_schema(profiles,manage,ids[0]),errors={'device':'unknown_device'})
            self._pending={'manage_dashboard':manage,'device':device}
            return await self.async_step_music_style()
        current=self.config_entry.options.get('manage_dashboard',True)
        errors=None if profiles else {'base':'invalid_profiles'}
        return self.async_show_form(step_id='init',data_schema=self._init_schema(profiles,current,ids[0] if ids else None),errors=errors)

    def _init_schema(self, profiles, manage, device):
        fields={vol.Required('manage_dashboard',default=manage):bool}
        if profiles:
            fields[vol.Required('device',default=device)]=SelectSelector(SelectSelectorConfig(
                options=[{'value':p['id'],'label':p.get('name',p['id'])} for p in profiles],mode=SelectSelectorMode.DROPDOWN))
        return vol.Schema(fields)

    async def async_step_music_style(self, user_input=None):
        device=self._pending.get('device')
        if device is None:return await self.async_step_init()
        styles=stored_music_styles(self.config_entry.options)
        errors=None
        if user_input is not None:
            style=user_input.get('music_style')
            if style in MUSIC_STYLES:
                styles[device]=style
                return self._save(manage_dashboard=self._pending['manage_dashboard'],**{MUSIC_STYLES_OPTION:styles})
            errors={'music_style':'invalid_style'}
        name=next((p.get('name',p['id']) for p in self._profiles or [] if p['id']==device),device)
        schema=vol.Schema({vol.Required('music_style',default=music_style(styles.get(device))):SelectSelector(SelectSelectorConfig(
            options=list(MUSIC_STYLES),translation_key='music_style',mode=SelectSelectorMode.LIST))})
        return self.async_show_form(step_id='music_style',data_schema=schema,errors=errors,description_placeholders={'device':name})
