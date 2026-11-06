"""Local-only checks: no real controller is contacted or written to."""
import socket
import subprocess
import threading
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import nami_transport as tcp
from backend.core.nami_simulator import frame, payload, DEFAULT_STATE
from backend.core import accounts

class NamiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.override=patch.object(accounts,'store',accounts.AccountStore(Path(self.temp.name)/'accounts.sqlite3'))
        self.override.start()
        self.client = TestClient(app)
        self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})

    def tearDown(self):
        self.client.close();self.override.stop();self.temp.cleanup()

    def test_feature_document_is_not_main_app(self):
        response = self.client.get('/nami/index.html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/nami/assets/', response.text)
        self.assertEqual(self.client.get('/nami/default_metadata.csv').status_code, 200)
        self.assertEqual(self.client.get('/nami/missing.js').status_code, 404)

    def test_simulator_handshake_and_groups(self):
        result = self.client.post('/api/nami/plc/test-connection', json={'isSimulated':True}).json()
        self.assertTrue(result['success'])
        self.assertEqual(result['programVersionStr'], '5.296')
        groups = [10,20,30,40,50,60,70,80,90,100,110,130,140,150,240,250,410,500,510,520,530,600]
        result = self.client.post('/api/nami/plc/read-multiple-groups', json={'isSimulated':True,'groupCodes':groups,'machineId':7}).json()
        self.assertEqual(len(result['results']), len(groups))
        for item in result['results']:
            raw = item['rawBytes']
            self.assertTrue(item['success'])
            self.assertEqual(raw[1], 7)
            self.assertEqual(len(raw), int.from_bytes(bytes(raw[3:5]),'big')+7)
            checksum = 0
            for b in raw[:-2]: checksum ^= b
            self.assertEqual(checksum, raw[-2])

    def test_invalid_configuration(self):
        for field, value in [('machineId',256),('machineId',-1),('machineId',1.5),('port',0),('port',65536),('timeoutMs',0)]:
            with self.subTest(field=field, value=value):
                response = self.client.post('/api/nami/plc/test-connection',json={'isSimulated':True,field:value})
                self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post('/api/nami/plc/read-group',json={'isSimulated':True,'groupCode':11}).status_code,400)

    def test_ping_is_one_icmp_request_and_never_sends_plc_protocol(self):
        with patch('backend.api.nami.subprocess.run', return_value=subprocess.CompletedProcess(['ping'], 0, 'reply', '')) as run:
            response = self.client.post('/api/nami/plc/ping', json={'ip':'127.0.0.2','timeoutMs':1200})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(response.json()['protocolRequestSent'])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], '127.0.0.2')
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_ping_rejects_non_private_and_invalid_addresses(self):
        for address in ('not-an-ip', '8.8.8.8', '::1'):
            with self.subTest(address=address):
                response = self.client.post('/api/nami/plc/ping', json={'ip':address})
                self.assertEqual(response.status_code, 400)

    def test_ping_reports_timeout_without_protocol_request(self):
        with patch('backend.api.nami.subprocess.run', side_effect=subprocess.TimeoutExpired(['ping'], 1)):
            response = self.client.post('/api/nami/plc/ping', json={'ip':'127.0.0.2','timeoutMs':100})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['success'])
        self.assertFalse(response.json()['protocolRequestSent'])

    def test_handshake_rejects_corrupted_or_wrong_machine_frame(self):
        for raw in [list(frame(1,payload(10,DEFAULT_STATE))), [3,0,0,0,4,0,0,0,0,99,2]]:
            with patch.object(tcp,'sequence',return_value={'results':[{'success':True,'rawBytes':raw}],'closeResult':None,'error':None}):
                result = self.client.post('/api/nami/plc/test-connection',json={'ip':'127.0.0.1','port':8302,'machineId':0}).json()
                self.assertFalse(result['success'])
                self.assertTrue(result['error'])

    def test_rtc_and_manual_simulation(self):
        result = self.client.post('/api/nami/plc/send-rtc',json={'isSimulated':True,'rtcLayout':'legacy','asciiPayload':'20261005120000','machineId':3}).json()
        self.assertTrue(result['success'])
        self.assertEqual(result['resultCode'],0)
        result = self.client.post('/api/nami/plc/send-raw',json={'isSimulated':True,'rawBytes':list(tcp.read_request(3,20))}).json()
        self.assertTrue(result['success'])
        self.assertEqual(result['rawBytes'][1],3)

    def test_fragmented_tcp_sequence_and_close_command(self):
        errors, received = [], []
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen()
            port = listener.getsockname()[1]
            def controller():
                try:
                    with listener.accept()[0] as conn:
                        conn.settimeout(3)
                        for group in (10,20,11):
                            request = bytearray()
                            while len(request)<9:
                                part=conn.recv(9-len(request))
                                if not part: raise AssertionError('Missing request')
                                request.extend(part)
                            received.append(bytes(request))
                            self.assertEqual(bytes(request),tcp.read_request(7,group))
                            if group != 11:
                                response=frame(7,payload(group,DEFAULT_STATE))
                                conn.sendall(response[:2]);conn.sendall(response[2:5]);conn.sendall(response[5:])
                except Exception as exc: errors.append(exc)
            worker=threading.Thread(target=controller)
            worker.start()
            result=tcp.sequence('127.0.0.1',port,7,[10,20],1000)
            worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors,errors)
            self.assertIsNone(result['error'])
            self.assertEqual(len(result['results']),2)
            self.assertTrue(result['closeResult']['success'])
            self.assertEqual(len(received),3)

if __name__ == '__main__':
    unittest.main()
