"""Loopback-only checks: never contact a physical controller."""
import socket
import threading
import unittest

from backend.core import nami_transport as tcp
from backend.core.nami_simulator import frame


class SequenceFailureTests(unittest.TestCase):
    def test_timeout_requests_close_and_skips_remaining_groups(self):
        requests, errors = [], []
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(3)
            def controller():
                try:
                    with listener.accept()[0] as conn:
                        conn.settimeout(3)
                        for group in [10, 20, 11]:
                            raw = bytearray()
                            while len(raw) < 9:
                                part = conn.recv(9 - len(raw))
                                if not part:
                                    raise AssertionError('Client closed before GC 11')
                                raw.extend(part)
                            requests.append(bytes(raw))
                            self.assertEqual(bytes(raw), tcp.read_request(0, group))
                            if group == 10:
                                conn.sendall(frame(0, b'\x01\x00'))
                            # GC 20 deliberately has no reply; GC 11 closes without ACK.
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=controller, daemon=True)
            worker.start()
            result = tcp.sequence('127.0.0.1', listener.getsockname()[1], 0, [10, 20, 150], 200)
            worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors, errors)
            self.assertEqual(len(requests), 3)
            self.assertTrue(result['results'][0]['success'])
            self.assertNotIn('error', result['results'][0])
            self.assertEqual(result['results'][1]['stage'], 'receive')
            self.assertEqual(result['results'][2]['stage'], 'not_sent')
            self.assertEqual(result['results'][2]['sentBytes'], [])
            self.assertEqual(result['closeResult']['sentBytes'], list(tcp.read_request(0, 11)))
            self.assertTrue(result['closeResult']['plcClosed'])

    def test_no_listener_does_not_claim_any_bytes_sent(self):
        # Keep an unlistened local port reserved throughout the check.
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            result = tcp.sequence('127.0.0.1', reserved.getsockname()[1], 0, [10, 20], 100)
        self.assertFalse(result['tcpConnected'])
        self.assertIsNone(result['closeResult'])
        self.assertEqual([r['stage'] for r in result['results']], ['connect', 'not_sent'])
        self.assertTrue(all(not r['sentBytes'] and not r['success'] for r in result['results']))


if __name__ == '__main__':
    unittest.main()
