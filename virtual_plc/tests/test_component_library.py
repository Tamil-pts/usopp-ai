from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from virtual_plc.core.component_library import ComponentLibrary
from virtual_plc.core.environment import build_plan
from virtual_plc.core.project import analyze_project
from virtual_plc.core.runtime import VirtualRuntime


class ComponentLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=analyze_project(Path(__file__).resolve().parents[1]/'examples/MotorCylinderPLC')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.library=ComponentLibrary(Path(self.temp.name)/'first-account')
        self.runtime=VirtualRuntime(self.model)
        self.components=[item for item in build_plan(self.runtime)['components'] if item['kind'] in {'motor','cylinder'}]
        for index,item in enumerate(self.components):item['position']={'x':100+index*270,'y':80}
        self.metadata={'name':'Delivery station','manufacturer':'Fixture make','model':'Model 1',
                       'terminals':[{'type':'DI','terminal':'X1:1','signal':'Running','unit':'BOOL'},
                                    {'type':'AI','terminal':'X1:2','signal':'Pressure','unit':'bar'},
                                    {'type':'COMM','terminal':'X2','protocol':'CANopen'}]}

    def test_library_roundtrip_preserves_models_vendor_terminals_layout_and_internal_links(self):
        encoder={'id':'encoder','name':'Encoder','kind':'encoder','enabled':True,'bindings':{},'config':{},
                 'links':{'speed':{'component':self.components[0]['id'],'port':'speed'}},'position':{'x':640,'y':80}}
        motor=next(item for item in self.components if item['kind']=='motor')
        encoder['links']['speed']['component']=motor['id']
        item=self.library.save(self.metadata,self.components+[encoder],'Source project')
        reloaded=ComponentLibrary(self.library.root).load(item['id'])
        self.assertEqual('Fixture make',reloaded['manufacturer'])
        self.assertEqual({'AI','DI','COMM'},{port['type'] for port in reloaded['terminals']})
        copies=self.library.instantiate(item['id'],self.runtime,offset_x=50,offset_y=25)
        self.assertEqual({'x':150,'y':105},copies[0]['position'])
        self.assertTrue(all(not copy['enabled'] and not copy['bindings'] for copy in copies))
        self.assertTrue(all(copy['id'] not in {original['id'] for original in self.components} for copy in copies))
        copied_motor=next(copy for copy in copies if copy['kind']=='motor')
        copied_encoder=next(copy for copy in copies if copy['kind']=='encoder')
        self.assertEqual(copied_motor['id'],copied_encoder['links']['speed']['component'])
        self.assertTrue(self.library.list()[0]['layoutSaved'])

    def test_explicit_exact_matching_is_typed_and_still_requires_enabling(self):
        item=self.library.save(self.metadata,self.components)
        copies=self.library.instantiate(item['id'],self.runtime,match_exact=True)
        self.assertTrue(all(copy['bindings'] for copy in copies))
        self.assertFalse(any(copy['enabled'] for copy in copies))
        other=deepcopy(self.model);other['variables']=[]
        # A separate target with no saved addresses must receive disconnected drafts.
        empty=VirtualRuntime({'programs':[],'variables':[],'tasks':[]})
        self.assertFalse(any(copy['bindings'] for copy in self.library.instantiate(item['id'],empty,match_exact=True)))

    def test_other_account_cannot_read_reference_or_model_and_paths_are_confined(self):
        item=self.library.save(self.metadata,self.components)
        reference=self.library.attach(item['id'],'../Vendor.dxf',b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n')
        path,name=self.library.reference(item['id'],reference['references'][0]['id'])
        self.assertEqual('Vendor.dxf',name)
        self.assertTrue(path.resolve().is_relative_to(self.library.root.resolve()))
        other=ComponentLibrary(Path(self.temp.name)/'other-account')
        self.assertEqual([],other.list())
        with self.assertRaises(ValueError):other.load(item['id'])
        with self.assertRaises(ValueError):self.library.load('../first-account')
        with self.assertRaises(ValueError):self.library.attach(item['id'],'run.exe',b'bad')

    def test_layout_bounds_and_terminal_types_are_checked(self):
        item=self.library.save(self.metadata,self.components)
        with self.assertRaises(ValueError):self.library.instantiate(item['id'],self.runtime,offset_x=12000)
        with self.assertRaises(ValueError):self.library.save({**self.metadata,'terminals':[{'type':'unsupported'}]},self.components)


if __name__=='__main__':unittest.main()
