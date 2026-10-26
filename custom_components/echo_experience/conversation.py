"""Echo Relay conversation agent: select it as the pipeline agent of a listen-only satellite."""
from homeassistant.components.conversation import ConversationEntity, ConversationEntityFeature
from homeassistant.const import MATCH_ALL

from .relay import Relay

DOMAIN = 'echo_experience'


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EchoRelayAgent(hass.data[DOMAIN], entry)])


class EchoRelayAgent(ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = 'Echo Relay'
    _attr_supported_features = ConversationEntityFeature(0)

    def __init__(self, runtime, entry):
        self.relay = Relay(runtime.hass, runtime)
        self._attr_unique_id = f'{entry.entry_id}_relay'

    @property
    def supported_languages(self):
        return MATCH_ALL

    async def async_process(self, user_input):
        return await self.relay.process(user_input)
