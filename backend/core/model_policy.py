"""Connection policy shared by confidential Chopper model transports."""
import ipaddress
from urllib.parse import urlsplit


def loopback_url(url):
    value=urlsplit(str(url))
    if value.scheme not in {'http','https'} or not value.hostname or value.username or value.password or value.query or value.fragment:
        return False
    try:return ipaddress.ip_address(value.hostname).is_loopback
    except ValueError:return value.hostname.casefold()=='localhost'


def enforce(cfg):
    if cfg.get('provider')=='local':return
    if (cfg.get('localOnly') or cfg.get('provider')=='embedded') and not loopback_url(cfg.get('baseUrl','')):
        raise ValueError('Local-only Chopper accepts loopback model endpoints only. No project evidence was sent.')


def request_options(cfg):
    # Ignore system proxies for local evidence, including token counting requests.
    return {'proxies':{'http':'','https':'','all':''}} if loopback_url(cfg.get('baseUrl','')) else {}
