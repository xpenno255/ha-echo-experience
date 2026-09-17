"""Text-only end-to-end turn tests, including the satellite's completion event."""
import asyncio,json,time
from pathlib import Path
from ha_client import ROOT,commands
from verify_live import run
from deploy import AUDIT

async def main():
    p=AUDIT
    cases=[
      ('Set a check timer for fifteen minutes','timers','echo_timer'),
      ('Cancel the check timer','timers','echo_timer'),
      ('What is 350 Fahrenheit in Celsius?','answer','echo_convert'),
      ('Will it rain tomorrow?','weather','echo_weather'),
      ('How do I defrost 400 grams of mince in my microwave?','guide','echo_guide'),
    ]
    rows=[]
    for text,view,tool in cases:
        r=await run(text)
        # This is the same event sent by the satellite browser after intent-end.
        event={'type':'voice_satellite/fire_chat_event','entity_id':'assist_satellite.echo_show_8','stt_text':text,'tts_text':r['speech'],'tool_calls':[{'name':t['tool_name']} for t in r['tools']]}
        from ha_client import ws_commands
        await ws_commands([event])
        snapshot=(await ws_commands([{'type':'echo_experience/state','device':'echo_show_8'}]))[0]
        names=[t['tool_name'].split('__')[-1] for t in r['tools']]
        passed=tool in names and snapshot['result']['view']==view and bool(r['speech']) and not r['speech'].startswith('Something went wrong')
        if text.startswith('Set '):passed=passed and any(t['name']=='check' for t in snapshot['timers'])
        if text.startswith('Cancel '):passed=passed and not snapshot['timers']
        row={'text':text,'passed':passed,'view':snapshot['result']['view'],'speech':r['speech'],'tools':names,'seconds':r['seconds']};rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    (p/'final_routing_tests.json').write_text(json.dumps(rows,indent=2))
    assert all(r['passed'] for r in rows),'One or more routing checks failed'

if __name__=='__main__':asyncio.run(main())
