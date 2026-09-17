"""Run bounded text-only checks with the real Echo's device context."""
import asyncio,json,time
from pathlib import Path
import websockets
from ha_client import ROOT,URL,ENV,commands,ws_commands
from deploy import AUDIT
HERE=Path(__file__).resolve().parent
async def run(text):
    pipeline=ENV.get('echo_pipeline_id')
    if not pipeline:
        available=(await ws_commands([{'type':'assist_pipeline/pipeline/list'}]))[0]['pipelines']
        pipeline=next(p['id'] for p in available if p['name']=='Echo Home')
    profile=json.loads((HERE/'profiles.json').read_text())['devices'][0]
    async with websockets.connect(URL.replace('https://','wss://').replace('http://','ws://')+'/api/websocket',max_size=None) as ws:
        await ws.recv();await ws.send(json.dumps({'type':'auth','access_token':ENV['access_token']}));assert json.loads(await ws.recv())['type']=='auth_ok'
        await ws.send(json.dumps({'id':1,'type':'assist_pipeline/run','start_stage':'intent','end_stage':'intent','pipeline':pipeline,'device_id':profile['device_id'],'input':{'text':text}}))
        events=[];tools=[];started=time.monotonic();speech='';response=None
        while True:
            message=json.loads(await asyncio.wait_for(ws.recv(),90))
            if message.get('id')!=1:continue
            if message['type']=='result' and not message.get('success'):raise RuntimeError(message.get('error'))
            if message['type']!='event':continue
            ev=message['event'];events.append(ev)
            if ev['type']=='intent-progress':
                delta=ev.get('data',{}).get('chat_log_delta',{})
                tools.extend(delta.get('tool_calls') or [])
            if ev['type']=='intent-end':
                response=ev['data']['intent_output'];speech=response.get('response',{}).get('speech',{}).get('plain',{}).get('speech','')
            if ev['type'] in ['run-end','error']:break
        result={'text':text,'speech':speech,'response':response,'tools':tools,'seconds':round(time.monotonic()-started,2),'events':events}
        return result
async def main():
    import sys
    rows=[]
    for text in sys.argv[1:]:
        result=await run(text);rows.append(result)
        print(json.dumps({k:result[k] for k in ['text','speech','tools','seconds']},ensure_ascii=False),flush=True)
    (AUDIT/('live_intents_'+str(int(time.time()))+'.json')).write_text(json.dumps(rows,indent=2))
if __name__=='__main__':asyncio.run(main())
