"""Browser defenses for the local-server deployment; no claim of network certification."""
import ipaddress
import os
import socket
from functools import lru_cache
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse


@lru_cache(maxsize=1)
def local_names():
    return {'localhost', socket.gethostname().lower(), socket.getfqdn().lower()}


def allowed_host(value):
    try:
        parsed=urlsplit('//'+value)
        host=parsed.hostname
        if not host or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:return False
        parsed.port  # Reject malformed port syntax too.
        host=host.lower().rstrip('.')
    except ValueError:return False
    configured=[h.strip().lower().rstrip('.') for h in os.getenv('USOPP_ALLOWED_HOSTS','').split(',') if h.strip()]
    if configured:return host in configured
    if host in local_names():return True
    try:
        address=ipaddress.ip_address(host)
        return address.is_loopback or address.is_private
    except ValueError:return False


def response_headers(scheme='http'):
    headers={
        'X-Content-Type-Options':'nosniff',
        'X-Frame-Options':'SAMEORIGIN',
        'Referrer-Policy':'strict-origin-when-cross-origin',
        # Keep recorder, same-origin PDF viewers and configured Office integrations usable.
        # This baseline does not claim a complete script-src CSP or XSS protection.
        'Content-Security-Policy':"base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
        'Permissions-Policy':'camera=(), geolocation=(), payment=(), usb=()',
    }
    if scheme=='https':headers['Strict-Transport-Security']='max-age=31536000'
    return headers


def unsafe_origin(request,dev_origins):
    origin=request.headers.get('origin')
    expected=f'{request.url.scheme}://{request.headers.get("host")}'
    if origin:return origin not in dev_origins and origin!=expected
    # Modern browser metadata covers cross-site requests that omit Origin.
    if request.headers.get('sec-fetch-site')=='cross-site':return True
    referer=request.headers.get('referer')
    if referer:
        try:
            value=urlsplit(referer);source=f'{value.scheme}://{value.netloc}'
        except ValueError:return True
        return source not in dev_origins and source!=expected
    # Authenticated non-browser clients (MCP and local tools) need not send browser headers.
    return False


class SecurityHeadersMiddleware:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        async def secured(message):
            if message['type']=='http.response.start':
                headers=MutableHeaders(scope=message)
                for key,value in response_headers(scope.get('scheme','http')).items():headers.setdefault(key,value)
                if scope.get('path','').startswith('/api/'):
                    headers['Cache-Control']='private, no-store'
                if 'server' in headers:del headers['server']
            await send(message)
        host=Headers(scope=scope).get('host','')
        in_process_test=(scope.get('client') or ('',0))[0]=='testclient' and host.split(':')[0]=='testserver'
        if not in_process_test and not allowed_host(host):
            return await JSONResponse({'detail':'This host is not allowed. Configure USOPP_ALLOWED_HOSTS for the local server.'},status_code=400)(scope,receive,secured)
        return await self.app(scope,receive,secured)
