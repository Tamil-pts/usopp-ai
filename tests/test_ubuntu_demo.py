"""Launcher checks without installing dependencies or touching real processes."""
import contextlib
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch, Mock
from scripts import ubuntu_demo as demo


class UbuntuDemoTests(unittest.TestCase):
    def test_process_identity_reads_start_ticks_after_comm_with_spaces(self):
        fields=['S'] + ['0'] * 18 + ['98765'] + ['0'] * 5
        with patch.object(Path,'read_text',return_value='123 (python worker) '+' '.join(fields)), \
             patch.object(Path,'read_bytes',return_value=b'/app/python\0-m\0uvicorn\0'):
            self.assertEqual(demo.process_identity(123),{'started':'98765','command':['/app/python','-m','uvicorn']})

    def test_pid_reuse_and_different_root_are_rejected(self):
        identity={'started':'123','command':['python','-m','uvicorn']}
        state={'pid':42,'root':str(demo.ROOT),'identity':identity}
        with patch.object(demo,'process_identity',return_value=identity):
            self.assertTrue(demo.is_running(state))
            self.assertFalse(demo.is_running({**state,'root':'/another/app'}))
        with patch.object(demo,'process_identity',return_value={**identity,'started':'999'}):
            self.assertFalse(demo.is_running(state))

    def test_stop_does_not_signal_untracked_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'server.json';state.write_text('{}')
            with patch.object(demo,'STATE',state),patch.object(demo,'is_running',return_value=False), \
                 patch.object(demo.os,'kill') as kill,contextlib.redirect_stdout(io.StringIO()):
                demo.stop();kill.assert_not_called();self.assertFalse(state.exists())

    def test_stop_signals_only_confirmed_server(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'server.json';state.write_text(json.dumps({'pid':42}))
            with patch.object(demo,'STATE',state),patch.object(demo,'is_running',side_effect=[True,False,False]), \
                 patch.object(demo.os,'kill') as kill,contextlib.redirect_stdout(io.StringIO()):
                demo.stop();kill.assert_called_once_with(42,signal.SIGTERM)
                self.assertFalse(state.exists())

    def test_install_commands_build_both_interfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            python=Path(directory)/'python';python.write_text('')
            with patch.object(demo,'PYTHON',python),patch.object(demo,'load_state',return_value={}), \
                 patch.object(demo,'is_running',return_value=False), \
                 patch.object(demo.shutil,'which',side_effect=lambda name:'/usr/bin/'+name), \
                 patch.object(demo.subprocess,'check_output',return_value='v20.18.0\n'), \
                 patch.object(demo.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO()):
                demo.install()
            self.assertEqual(run.call_args_list[0].args[0][1:4],['-m','pip','install'])
            self.assertEqual(run.call_args_list[1].args[0],['/usr/bin/npm','ci','--no-audit','--no-fund'])
            self.assertEqual(run.call_args_list[2].args[0],['/usr/bin/npm','run','build'])

    def test_start_waits_for_health_and_records_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'dist').mkdir();(root/'dist/index.html').write_text('UI')
            (root/'package.json').write_text('{"version":"4.64.8"}')
            python=root/'python';python.write_text('');state=root/'state/server.json'
            process=Mock(pid=42);process.poll.return_value=None
            probe=Mock();probe.connect_ex.return_value=1
            socket=Mock();socket.__enter__=Mock(return_value=probe);socket.__exit__=Mock()
            identity={'started':'123','command':['python','-m','uvicorn']}
            with patch.object(demo,'ROOT',root),patch.object(demo,'PYTHON',python), \
                 patch.object(demo,'STATE',state),patch.object(demo,'LOG',root/'logs/demo.log'), \
                 patch.object(demo,'is_running',return_value=False),patch.object(demo.socket,'socket',return_value=socket), \
                 patch.object(demo.subprocess,'Popen',return_value=process) as popen, \
                 patch.object(demo,'health',return_value={'version':'4.64.8'}), \
                 patch.object(demo,'process_identity',return_value=identity),contextlib.redirect_stdout(io.StringIO()):
                demo.start('0.0.0.0',8200)
                self.assertTrue(popen.call_args.kwargs['start_new_session'])
                self.assertEqual(json.loads(state.read_text())['identity'],identity)
                self.assertIn('virtual_plc.server:create_app',popen.call_args.args[0])
                self.assertIn('--factory',popen.call_args.args[0])


if __name__=='__main__':unittest.main()
