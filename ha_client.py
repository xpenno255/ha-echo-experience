"""Local deployment client; credentials stay in the untracked .env or environment."""
import asyncio, json, os
from pathlib import Path
import requests, websockets
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
ENV={}
for env_file in (ROOT/'.env', HERE/'.env'):
 if env_file.exists():
  ENV.update({k.strip():v.strip().strip('\"\'') for l in env_file.read_text().splitlines() if '=' in l and not l.lstrip().startswith('#') for k,v in [l.split('=',1)]})
ENV.update(os.environ)
URL=ENV['homeassistant_url'].rstrip('/')
SESSION=requests.Session()
SESSION.headers.update({'Authorization':'Bearer '+ENV['access_token']})
def rest(path, data=None, method=None):
 r=SESSION.request(method or ('POST' if data is not None else 'GET'),URL+path,json=data,timeout=45)
 r.raise_for_status()
 return r.json()
async def ws_commands(commands):
 out=[]
 async with websockets.connect(URL.replace('https://','wss://').replace('http://','ws://')+'/api/websocket',max_size=32*1024*1024) as ws:
  await ws.recv(); await ws.send(json.dumps({'type':'auth','access_token':ENV['access_token']}))
  assert json.loads(await ws.recv())['type']=='auth_ok'
  for i,cmd in enumerate(commands,1):
   await ws.send(json.dumps({'id':i,**cmd}))
   while True:
    result=json.loads(await asyncio.wait_for(ws.recv(),45))
    if result.get('id')==i and result['type']=='result':break
   if not result.get('success'): raise RuntimeError(result.get('error'))
   out.append(result.get('result'))
 return out

def commands(*cmds):return asyncio.run(ws_commands(cmds))
