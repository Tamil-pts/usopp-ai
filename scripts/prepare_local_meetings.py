"""Prepare the pinned upstream Jitsi deployment; never starts services or opens ports."""
import argparse,hashlib,ipaddress,json,secrets,stat,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
import requests

COMMIT='fca3e3a578a1bdd527c20b9d86a31cfc362d5426'
RELEASE='stable-11248-3'
SHA256='66487a78047c0f4a93d79b8b014ec553aa9fb2691f99e7b833653167c8d243f3'

def prepare(target,url,lan_ip,archive=None):
    parsed=urlsplit(url);address=ipaddress.ip_address(lan_ip)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path not in {'','/'} or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Use the local meeting server HTTPS origin, without a path or credentials.')
    if not address.is_private or address.is_loopback or address.is_unspecified or address.version!=4:raise ValueError('Enter this meeting server LAN IPv4 address, not localhost.')
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):raise ValueError('Choose an empty output directory; existing meeting secrets and data are preserved.')
    if archive:raw=Path(archive).read_bytes()
    else:
        response=requests.get('https://codeload.github.com/jitsi/docker-jitsi-meet/zip/'+COMMIT,timeout=60);response.raise_for_status();raw=response.content
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('The upstream deployment archive checksum did not match.')
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(raw)) as source:
        entries=[]
        for info in source.infolist():
            parts=PurePosixPath(info.filename).parts[1:]
            if not parts:continue
            if '..' in parts or PurePosixPath(*parts).is_absolute() or '\\' in info.filename or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Unsafe archive member.')
            destination=target.joinpath(*parts)
            if not destination.resolve().is_relative_to(target):raise ValueError('Unsafe archive path.')
            entries.append((info,destination))
        target.mkdir(parents=True,exist_ok=True)
        for info,destination in entries:
            if info.is_dir():destination.mkdir(parents=True,exist_ok=True)
            else:destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(source.read(info))
    config=target/'config';dirs=['web','prosody/config','prosody/prosody-plugins-custom','jicofo','jvb','jigasi','jibri','transcriber','storage/jibri','storage/prosody','storage/transcripts','storage/web','tmp/web-crontabs','tmp/web-load-test']
    for folder in dirs:
        directory=config/folder;directory.mkdir(parents=True,exist_ok=True)
        # Upstream's rootless containers require writable storage/tmp mounts.
        if folder.startswith(('storage/','tmp/')):directory.chmod(0o777)
    secret=secrets.token_urlsafe(48)
    settings={'JITSI_IMAGE_VERSION':RELEASE,'CONFIG':'./config','PUBLIC_URL':url.rstrip('/'),'HTTP_PORT':'8800','HTTPS_PORT':'8443','TZ':'Asia/Kolkata','JVB_ADVERTISE_IPS':lan_ip,'ENABLE_AUTH':'1','AUTH_TYPE':'jwt','ENABLE_GUESTS':'0','JWT_ALLOW_EMPTY':'0','JWT_APP_ID':'usopp','JWT_APP_SECRET':secret,'JWT_ACCEPTED_ISSUERS':'usopp','JWT_ACCEPTED_AUDIENCES':'usopp','ENABLE_LETSENCRYPT':'0','DISABLE_LOCAL_RECORDING':'0','DISABLE_POLLS':'0','DISABLE_REACTIONS':'0'}
    settings.update(XMPP_DOMAIN=parsed.hostname,XMPP_AUTH_DOMAIN='auth.'+parsed.hostname,XMPP_MUC_DOMAIN='muc.'+parsed.hostname,XMPP_INTERNAL_MUC_DOMAIN='internal-muc.'+parsed.hostname)
    for key in ('JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD','JIGASI_XMPP_PASSWORD','JIBRI_RECORDER_PASSWORD','JIBRI_XMPP_PASSWORD'):settings[key]=secrets.token_urlsafe(32)
    original=(target/'env.example').read_text(encoding='utf-8');(target/'.env').write_text(original+'\n# uSOPp.ai local authenticated meeting overrides\n'+'\n'.join(k+'='+v for k,v in settings.items())+'\n',encoding='utf-8')
    (target/'usopp-meetings.json').write_text(json.dumps({'url':url.rstrip('/'),'appId':'usopp','secret':secret},indent=2),encoding='utf-8')
    for name in ('.env','usopp-meetings.json'):(target/name).chmod(0o600)
    (target/'USOPP_DEPLOYMENT.json').write_text(json.dumps({'commit':COMMIT,'release':RELEASE,'archiveSha256':SHA256,'serviceStarted':False,'needsTrustedHttps':True},indent=2),encoding='utf-8')
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=Path('deploy/meetings/runtime'));parser.add_argument('--url',required=True);parser.add_argument('--lan-ip',required=True);parser.add_argument('--archive',type=Path)
    args=parser.parse_args();print('Prepared:',prepare(args.output,args.url,args.lan_ip,args.archive));print('No services started. Follow deploy/meetings/README.md to configure HTTPS and start Docker Compose. Keep generated secrets private.')
