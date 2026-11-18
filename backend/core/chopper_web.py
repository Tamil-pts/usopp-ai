"""Bounded public HTTPS retrieval: allowlisted hosts, pinned public IP, no cookies/proxy."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlencode
import os

MAX_BYTES=1024*1024


def public_url(url, domains, *, resolver=None):
    parsed=urlsplit(str(url))
    host=(parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme!='https' or not host or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.fragment:
        raise ValueError('Web sources require a public HTTPS URL without credentials, fragments or custom ports.')
    if host not in domains:raise ValueError('This source domain is not on the administrator-approved web list: '+host)
    addresses=list(dict.fromkeys(row[4][0] for row in (resolver or socket.getaddrinfo)(host,443,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Web access to loopback, private, reserved or link-local addresses is blocked.')
    return parsed, addresses[0]


def get_bytes(url, domains, headers=None, method='GET', body=None, timeout=6):
    for _ in range(4):
        parsed, address=public_url(url,domains)
        connection=http.client.HTTPSConnection(parsed.hostname,443,timeout=timeout,context=ssl.create_default_context())
        # TLS still verifies the original hostname. Only the TCP destination is pinned.
        connection._create_connection=lambda _addr, timeout=timeout, source_address=None:socket.create_connection((address,443),timeout,source_address)
        try:
            connection.request(method,(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),body=body,headers={'User-Agent':'uSOPp-Chopper/1.0','Accept':'text/html,text/plain,application/json',**(headers or {})})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                # Credentials never cross a redirect boundary.
                if headers or method!='GET':raise ValueError('Authenticated or POST redirects are not allowed.')
                url=urljoin(url,response.getheader('Location',''))
                continue
            if response.status!=200:raise ValueError('Web source returned HTTP '+str(response.status))
            kind=response.getheader('Content-Type','').split(';')[0].strip().lower()
            if kind not in {'text/html','text/plain','application/json'}:raise ValueError('Choose a readable HTML or text source. Binary downloads are not executed or opened.')
            body=response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:raise ValueError('Web source exceeds the 1 MB retrieval limit.')
            return url,body,kind
        finally:connection.close()
    raise ValueError('Web source exceeded the redirect limit.')


class Text(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','svg','noscript'}:self.skip+=1
        if not self.skip and tag in {'p','div','li','h1','h2','h3','br'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','svg','noscript'}:self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def retrieve(url,domains):
    final,body,kind=get_bytes(url,domains)
    text=body.decode('utf-8',errors='replace')
    if kind=='text/html':
        parser=Text();parser.feed(text);text=''.join(parser.parts)
    text='\n'.join(' '.join(line.split()) for line in text.splitlines() if line.strip())
    if not text:raise ValueError('No readable text was extracted from this web source.')
    return {'url':final,'sha256':hashlib.sha256(body).hexdigest(),'retrievedAt':datetime.now(timezone.utc).isoformat(),
            'text':text[:16000],'shortened':len(text)>16000,'trust':'external untrusted source; not PLC project evidence'}


def search(query,domains):
    key=os.getenv('USOPP_BRAVE_SEARCH_KEY','')
    if not key:raise ValueError('Web search needs the server USOPP_BRAVE_SEARCH_KEY setting. You can enter approved source URLs instead.')
    if not query or len(query)>400:raise ValueError('Enter a public web-search query up to 400 characters. Do not include confidential PLC content.')
    _,body,_=get_bytes('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':5}),['api.search.brave.com'],{'X-Subscription-Token':key})
    value=json.loads(body)
    # Search results are discovery only. Read sources under the normal domain/IP policy.
    return [row['url'] for row in value.get('web',{}).get('results',[]) if urlsplit(row.get('url','')).hostname in domains][:3]
