"""Deploy owned files and an additive dashboard, with focused backups."""
import argparse,json,os,hashlib
from pathlib import Path
import smbclient
from ha_client import ENV,rest,commands
HERE=Path(__file__).resolve().parent
AUDIT=Path(ENV.get('echo_backup_dir') or ((HERE/'.audit_path').read_text().strip() if (HERE/'.audit_path').exists() else HERE/'.backups'))
AUDIT.mkdir(parents=True,exist_ok=True,mode=0o700)
BASE='\\\\'+ENV['smb_host']+'\\config'

def connect():
    smbclient.register_session(ENV['smb_host'],username=ENV['smb_username'],password=ENV['smb_password'],connection_timeout=15)


def write(relative,data):
    path=BASE+'\\'+relative.replace('/','\\')
    backup=AUDIT/('predeploy__'+relative.replace('/','__'))
    if not backup.exists():
        try:
            with smbclient.open_file(path,'rb') as f:backup.write_bytes(f.read())
        except FileNotFoundError: pass
        except OSError as err:
            if getattr(err,'errno',None)!=2:raise
    smbclient.makedirs(path.rsplit('\\',1)[0],exist_ok=True)
    with smbclient.open_file(path,'wb') as f:f.write(data)
    with smbclient.open_file(path,'rb') as f:assert f.read()==data


def install_files():
    connect()
    for f in sorted((HERE/'custom_components/echo_experience').glob('*')):
        if f.suffix in ['.py','.json','.yaml']:write('custom_components/echo_experience/'+f.name,f.read_bytes())
    write('echo_experience.json',(HERE/'profiles.json').read_bytes())
    write('www/echo-experience/echo-experience.js',(HERE/'www/echo-experience.js').read_bytes())
    print('Verified integration, profiles and dashboard JavaScript on HA')

def dashboard():
    profiles=json.loads((HERE/'profiles.json').read_text())['devices']
    views=[]
    for p in profiles:
        views.append({'title':p['name'],'path':p['id'],'type':'panel','cards':[{'type':'custom:echo-experience-card','device':p['id']}]})
        views.append({'title':p['name']+' Screensaver','path':p['id']+'-screensaver','type':'panel','subview':True,'cards':[{'type':'custom:echo-experience-card','device':p['id'],'ambient':True}]})
    config={'title':'Echo Home','views':views}
    dashboards,resources=commands({'type':'lovelace/dashboards/list'},{'type':'lovelace/resources'})
    if not any(d['url_path']=='echo-home' for d in dashboards):
        commands({'type':'lovelace/dashboards/create','url_path':'echo-home','title':'Echo Home','icon':'mdi:tablet-dashboard','show_in_sidebar':True,'require_admin':False})
    else:
        before=commands({'type':'lovelace/config','url_path':'echo-home'})[0]
        if not (AUDIT/'echo-home.before.json').exists():(AUDIT/'echo-home.before.json').write_text(json.dumps(before,indent=2))
    commands({'type':'lovelace/config/save','url_path':'echo-home','config':config})
    resource='/local/echo-experience/echo-experience.js?v='+hashlib.sha256((HERE/'www/echo-experience.js').read_bytes()).hexdigest()[:10]
    existing=next((r for r in resources if r['url'].startswith('/local/echo-experience/echo-experience.js')),None)
    if existing:
        commands({'type':'lovelace/resources/update','resource_id':existing['id'],'url':resource,'res_type':'module'})
    else:commands({'type':'lovelace/resources/create','url':resource,'res_type':'module'})
    assert commands({'type':'lovelace/config','url_path':'echo-home'})[0]==config
    (HERE/'dashboard.json').write_text(json.dumps(config,indent=2)+'\n')
    print('Echo Home dashboard saved and verified')

if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--files-only',action='store_true');args=parser.parse_args()
    install_files()
    if not args.files_only:dashboard()
