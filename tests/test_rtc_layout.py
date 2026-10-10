"""RTC protocol checks use a loopback TCP peer, never a physical PLC."""
import socket
import threading
import unittest
from fastapi import HTTPException
from backend.api.nami import send_rtc
from backend.core.nami_simulator import frame
from backend.core.nami_transport import read_request


class RTCLayoutTests(unittest.TestCase):
    def test_default_spinconnect_exact_indices_and_no_clock_applied_claim(self):
        text = '2026-10-08 14:05:06'
        result = send_rtc({'isSimulated': True, 'asciiPayload': text, 'machineId': 3})
        expected = frame(3, b'\x00\x0a\x00\x00' + text.encode('ascii'), 1)
        self.assertEqual(result['sentBytes'], list(expected))
        self.assertEqual(len(expected), 30)
        self.assertEqual(expected[3:5], b'\x00\x17')
        self.assertEqual(expected[9:28].decode('ascii'), text)
        self.assertEqual([expected[i] for i in (9, 14, 17, 20, 23, 26)], [50, 49, 48, 49, 48, 48])
        self.assertIsNone(result['clockApplied'])
        self.assertIn('no physical PLC', result['message'])
        self.assertEqual(result['closeResult']['sentBytes'], list(read_request(3, 11)))

    def test_bad_timestamp_function_and_close_group_rejected_before_network(self):
        for override in ({'asciiPayload': '20261008140506'}, {'asciiPayload': '2026-02-30 14:05:06'},
                         {'asciiPayload': '2026-10-08 24:05:06'}, {'groupCode': 11}, {'functionCode': 0},
                         {'asciiPayload': '2026-10-08 14:05:06 extra'}, {'rtcLayout': 'guess'}):
            with self.subTest(override=override), self.assertRaises(HTTPException) as error:
                send_rtc({'ip': '127.0.0.1', 'asciiPayload': '2026-10-08 14:05:06', **override})
            self.assertEqual(error.exception.status_code, 400)

    def test_actual_tcp_sends_timestamp_then_gc11_on_response_and_timeout(self):
        for reply in (True, False):
            with self.subTest(reply=reply), socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(3)
                received, errors = [], []
                def peer():
                    try:
                        with listener.accept()[0] as conn:
                            conn.settimeout(3)
                            for size in (30, 9):
                                raw = bytearray()
                                while len(raw) < size:
                                    part = conn.recv(size - len(raw))
                                    if not part: raise AssertionError('Closed before GC 11')
                                    raw.extend(part)
                                received.append(bytes(raw))
                                if size == 30 and reply:
                                    conn.sendall(frame(4, b'\x00\x00\xa0\x40'))
                    except Exception as exc:
                        errors.append(exc)
                worker = threading.Thread(target=peer, daemon=True); worker.start()
                result = send_rtc({'ip': '127.0.0.1', 'port': listener.getsockname()[1], 'timeoutMs': 200,
                                   'machineId': 4, 'asciiPayload': '2026-10-08 14:05:06'})
                worker.join(4)
                self.assertFalse(worker.is_alive()); self.assertFalse(errors, errors)
                self.assertEqual(len(received), 2)
                self.assertEqual(received[0][9:28], b'2026-10-08 14:05:06')
                self.assertEqual(received[1], read_request(4, 11))
                self.assertEqual(result['sentBytes'], list(received[0]))
                self.assertEqual(result['success'], reply)
                self.assertTrue(result['closeResult']['plcClosed'])
                self.assertIsNone(result['clockApplied'])


if __name__ == '__main__':
    unittest.main()
