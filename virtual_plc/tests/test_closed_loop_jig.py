"""Execute actual supported ST, real I/O bindings and simulated physical feedback."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from virtual_plc.core.components import DeviceComponents
from virtual_plc.core.environment import build_plan,LogicIndex
from virtual_plc.core.auto_mapping import discover
from virtual_plc.core.project import analyze_project
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.core.service import VirtualPLCService

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/MotorCylinderPLC'


class ClosedLoopJigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=analyze_project(EXAMPLE)

    def runtime(self):
        runtime=VirtualRuntime(self.model)
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        return runtime

    def test_exact_io_and_cross_program_logic_map_motor_and_cylinder(self):
        runtime=self.runtime();plan=build_plan(runtime)
        self.assertEqual(2,plan['automaticMappings'],plan)
        physical={device['kind']:device for device in plan['components'] if device['kind'] in {'motor','cylinder'}}
        self.assertEqual({'motor','cylinder'},set(physical))
        self.assertEqual('high',physical['motor']['evidence']['confidence'])
        self.assertTrue(physical['motor']['bindings']['running'].endswith('Motor1Running'))
        self.assertTrue(physical['cylinder']['bindings']['extended'].endswith('Cylinder1Extended'))
        self.assertFalse(any(device['kind']=='encoder' for device in plan['components']))

    def test_start_motor_feedback_cylinder_extend_and_return_without_feedback_toggles(self):
        runtime=self.runtime();devices=DeviceComponents(build_plan(runtime)['components'],runtime)
        devices.prepare()
        for _ in range(5):
            devices.prepare();runtime.command('scan');devices.after_scan()
        self.assertEqual(0,runtime.get_value('Step'))
        self.assertFalse(runtime.get_value('Motor1Cmd'))
        self.assertTrue(runtime.get_value('Cylinder1Retracted'))
        button=next(device for device in devices.components if device['kind']=='pushbutton' and device['name']=='StartButton')
        devices.states[button['id']]['pressedUntilMs']=runtime.time_ms+200
        history=[]
        for _ in range(300):
            devices.prepare();runtime.command('scan');devices.after_scan()
            history.append((runtime.time_ms,runtime.get_value('Step'),runtime.get_value('Motor1Cmd'),
                            runtime.get_value('Motor1Running'),runtime.get_value('Cylinder1Extended')))
            if runtime.get_value('CycleComplete'):break
        self.assertTrue(runtime.get_value('CycleComplete'),history[-10:])
        self.assertEqual(4,runtime.get_value('Step'))
        self.assertTrue(any(row[2] and not row[3] for row in history),'Motor feedback must respect start delay.')
        self.assertTrue(any(row[4] for row in history),'Cylinder must reach its extended switch.')
        self.assertTrue(runtime.get_value('Cylinder1Retracted'))

    def test_incomplete_hardware_is_a_proposal_and_never_writes_feedback(self):
        model=deepcopy(self.model);model['hardware']['channels']=[]
        runtime=VirtualRuntime(model);plan=build_plan(runtime)
        self.assertEqual(0,plan['automaticMappings'])
        self.assertEqual(2,len(plan['pendingMappings']))
        self.assertFalse(any(device['kind'] in {'motor','cylinder'} for device in plan['components']))

    def test_names_without_compiled_dependency_are_not_automatic(self):
        runtime=self.runtime();index=LogicIndex(runtime)
        for target in list(index.writers):
            if target.endswith('Step'):index.writers[target]=[]
        proposals=discover(runtime,index)
        self.assertTrue(proposals)
        self.assertFalse(any(proposal['automatic'] for proposal in proposals))

    def test_cylinder_fault_holds_position_and_conflicting_commands_are_reported(self):
        runtime=self.runtime();plan=build_plan(runtime)
        cylinder=next(item for item in plan['components'] if item['kind']=='cylinder')
        cylinder['config']['faultInjected']=1
        devices=DeviceComponents(plan['components'],runtime);devices.prepare()
        runtime.set_value('Step',2,return_snapshot=False)
        runtime.set_value('Motor1Running',True,force=True,return_snapshot=False)
        for _ in range(150):
            devices.prepare();runtime.command('scan');devices.after_scan()
        self.assertFalse(runtime.get_value('Cylinder1Extended'))
        status=next(item for item in devices.snapshot() if item['kind']=='cylinder')
        self.assertEqual('fault',status['status']['state'])
        self.assertTrue(status['actionRequired'])

    def test_manual_connections_are_preserved_and_new_feedback_requires_confirmation(self):
        runtime=self.runtime();plan=build_plan(runtime)
        original=next(item for item in plan['components'] if item['kind']=='cylinder')
        original['evidence']['mappingSource']='manual'
        original['config']['travelMs']=2500
        rebuilt=build_plan(runtime,[original])
        preserved=next(item for item in rebuilt['components'] if item['id']==original['id'])
        self.assertEqual(2500,preserved['config']['travelMs'])
        self.assertTrue(any(item['kind']=='cylinder' for item in rebuilt['pendingMappings']))

    def test_fault_blocks_motion_and_forced_feedback_takes_precedence(self):
        runtime=self.runtime();components=build_plan(runtime)['components']
        motor=next(device for device in components if device['kind']=='motor')
        motor['config']['faultInjected']=1
        devices=DeviceComponents(components,runtime);devices.prepare()
        runtime.set_value('Step',1,return_snapshot=False)
        for _ in range(50):
            devices.prepare();runtime.command('scan');devices.after_scan()
        self.assertFalse(runtime.get_value('Motor1Running'))
        self.assertEqual(1,runtime.get_value('Step'))
        runtime.set_value('Motor1Running',True,force=True,return_snapshot=False)
        devices.prepare();runtime.command('scan');devices.after_scan()
        self.assertTrue(runtime.get_value('Motor1Running'))

    def test_enabling_jig_keeps_running_plc_memory_and_scan_time(self):
        with tempfile.TemporaryDirectory() as folder:
            service=VirtualPLCService(Path(folder));self.addCleanup(service.close)
            document=service.create('test',EXAMPLE)
            workspace=service.get('test',document['id'])
            deadline=time.monotonic()+20
            while workspace.document['status']=='analyzing' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual('ready',workspace.document['status'],workspace.progress)
            service.command(workspace,'scan')
            original=workspace.runtime
            original.set_value('Step',1,return_snapshot=False)
            with patch.object(service,'_start_worker'):
                service.command(workspace,'run')
            before=original.time_ms
            response=service.configure_jig(workspace,True)
            self.assertIs(original,workspace.runtime)
            self.assertEqual('running',workspace.runtime.status)
            self.assertEqual(before,workspace.runtime.time_ms)
            self.assertEqual(1,workspace.runtime.get_value('Step'))
            self.assertTrue(response['jig']['enabled'])
            self.assertFalse(workspace.runtime.get_value('CycleComplete'))

    def test_explicit_confirmation_and_scenario_contacts_share_existing_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            service=VirtualPLCService(Path(folder));self.addCleanup(service.close)
            document=service.create('test',EXAMPLE);workspace=service.get('test',document['id'])
            deadline=time.monotonic()+20
            while workspace.document['status']=='analyzing' and time.monotonic()<deadline:time.sleep(.01)
            workspace.runtime.project['hardware']['channels']=[]
            prepared=service.configure_jig(workspace,True)
            proposal=prepared['environment']['pendingMappings'][0]
            confirmed=service.confirm_mapping(workspace,proposal['id'])
            device=next(item for item in confirmed['components'] if item['id']==proposal['id'])
            self.assertEqual('confirmed',device['evidence']['confidence'])
            self.assertFalse(any(item['id']==proposal['id'] for item in confirmed['environment']['pendingMappings']))
            service._scenario_event(workspace,{'name':'StartButton','value':True})
            devices=service._devices(workspace)
            devices.prepare()
            self.assertTrue(workspace.runtime.get_value('StartButton'))
            service._scenario_event(workspace,{'name':'StartButton','value':False})
            devices.prepare()
            self.assertFalse(workspace.runtime.get_value('StartButton'))


if __name__=='__main__':unittest.main()
