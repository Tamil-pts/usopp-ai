import unittest
from types import SimpleNamespace
from backend.core.web_security import allowed_host, unsafe_origin


class TestDevTunnelSecurity(unittest.TestCase):
    def test_allowed_host_devtunnels(self):
        self.assertTrue(allowed_host('abc123-8200.inc1.devtunnels.ms'))
        self.assertTrue(allowed_host('127.0.0.1:8200'))
        self.assertFalse(allowed_host('evil.example.com'))

    def test_unsafe_origin_with_forwarded_devtunnel(self):
        req = SimpleNamespace(
            url=SimpleNamespace(scheme='http'),
            headers={
                'host': '127.0.0.1:8200',
                'x-forwarded-host': 'abc123-8200.inc1.devtunnels.ms',
                'x-forwarded-proto': 'https',
                'origin': 'https://abc123-8200.inc1.devtunnels.ms',
            },
        )
        self.assertFalse(unsafe_origin(req, []))

    def test_unsafe_origin_rejects_untrusted_origin(self):
        req = SimpleNamespace(
            url=SimpleNamespace(scheme='http'),
            headers={
                'host': '127.0.0.1:8200',
                'x-forwarded-host': 'abc123-8200.inc1.devtunnels.ms',
                'x-forwarded-proto': 'https',
                'origin': 'https://attacker.example.com',
            },
        )
        self.assertTrue(unsafe_origin(req, []))


if __name__ == '__main__':
    unittest.main()
