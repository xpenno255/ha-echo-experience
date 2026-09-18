"""Build the short voice stop route from the installed Echo profiles."""
import json

AUTOMATION_ID = '1757961047860'
COMMANDS = ['stop', 'stop music', 'stop sonos', 'stop the music', 'stop the sonos',
            'stop playing music', 'turn off the music', 'stop sonos in here']
TARGET_TEMPLATE = """{% if origin_device in device_players %}
  {{ [device_players[origin_device]] }}
{% elif origin_area %}
  {{ integration_entities('sonos') | select('in', area_entities(origin_area))
     | select('match', '^media_player\\.') | list }}
{% else %}
  {{ [] }}
{% endif %}"""


def build(profiles, entity_registry):
    registry = {e['entity_id']: e for e in entity_registry}
    routes = {}
    for profile in profiles:
        ids = [profile['device_id']]
        for satellite in profile.get('ducking', {}).get('additional_satellites', []):
            device = registry.get(satellite, {}).get('device_id')
            if device:
                ids.append(device)
        for device in ids:
            player = profile['music_player']
            if device in routes and routes[device] != player:
                raise ValueError('A voice device has conflicting music stop targets')
            routes[device] = player
    return {
        'id': AUTOMATION_ID,
        'alias': 'Stop Sonos in Voice Assistant Area',
        'description': 'Known Echo/companion voice devices stop their configured Music Assistant group. Other devices require a real area and target only native Sonos entities in it. Generated from Echo Experience profiles.',
        'triggers': [{'trigger': 'conversation', 'command': COMMANDS}],
        'variables': {
            'device_players': routes,
            'origin_device': "{{ trigger.device_id | default('', true) }}",
            'origin_area': "{{ area_id(origin_device) if origin_device else none }}",
            'stop_players': TARGET_TEMPLATE,
        },
        'actions': [{'choose': [{
            'conditions': [{'condition': 'template', 'value_template': '{{ stop_players | length > 0 }}'}],
            'sequence': [
                {'action': 'media_player.media_stop', 'target': {'entity_id': '{{ stop_players }}'}},
                {'set_conversation_response': 'Stopped.'},
            ],
        }], 'default': [{'set_conversation_response': "I couldn't identify the music speaker for this device."}]}],
        'mode': 'parallel', 'max': 10,
    }


def install():
    from requests import HTTPError
    from ha_client import commands, rest
    from deploy import AUDIT, HERE
    profiles = json.loads((HERE / 'profiles.json').read_text())['devices']
    config = build(profiles, commands({'type': 'config/entity_registry/list'})[0])
    try:
        before = rest('/api/config/automation/config/' + AUTOMATION_ID)
    except HTTPError as err:
        if err.response.status_code != 404:
            raise
        before = None
    backup = AUDIT / 'stop_automation_before_scoped_routing.private.json'
    if before is not None and not backup.exists():
        backup.write_text(json.dumps(before, indent=2))
    rest('/api/config/automation/config/' + AUTOMATION_ID, config)
    assert rest('/api/config/automation/config/' + AUTOMATION_ID) == config
    (HERE / 'automations/voice_music_stop.json').write_text(json.dumps(config, indent=2) + '\n')
    print('Voice stop automation saved and verified; no Core restart required')


if __name__ == '__main__':
    install()
