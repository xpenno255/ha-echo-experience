"""Capture the kiosk screen through its existing ESPHome screenshot entity."""
import sys,time
from pathlib import Path
from ha_client import ROOT,rest,SESSION,URL
from deploy import AUDIT
p=AUDIT
eid='sensor.amzn_echo_show_8_last_screenshot'
before=rest('/api/states/'+eid)['state']
rest('/api/services/button/press',{'entity_id':'button.amzn_echo_show_8_take_screenshot'})
for _ in range(30):
 time.sleep(.25)
 if rest('/api/states/'+eid)['state']!=before:break
else:raise RuntimeError('Screenshot capture did not update')
r=SESSION.get(URL+'/api/camera_proxy/camera.amzn_echo_show_8_screenshot',timeout=20);r.raise_for_status()
path=p/(sys.argv[1] if len(sys.argv)>1 else 'echo-live.jpg');path.write_bytes(r.content);print(path)
