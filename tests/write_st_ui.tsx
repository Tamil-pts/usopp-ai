import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import type {ValidationWorkspace} from '../src/features/validation/useValidationWorkspace';

Object.assign(globalThis,{location:{pathname:'/bytemap/'},window:new EventTarget()});
const {WriteSTGenerator}=await import('../src/features/validation/WriteSTGenerator');
const {ValidationPage}=await import('../src/features/validation/ValidationPage');
const workspace={localProjectPath:'C:/reference/project 1',projectFiles:[],projectName:'project 1',localMetadataPath:'',
 localMetadataName:'',machineDepartment:'Finisher',busy:'',message:'',error:'',result:null,generated:null,
 projectDetails:null,sourceChanged:false,detailsError:'',detailsLoading:false} as unknown as ValidationWorkspace;
const panel=renderToStaticMarkup(<WriteSTGenerator workspace={workspace}/>);
assert.equal((panel.match(/Generate ST<\/button>/g)||[]).length,1);
assert.ok(panel.includes('Project selected — choose Generate ST'));
assert.ok(!panel.includes('Select a project, then choose Analyze project'));
const page=renderToStaticMarkup(<ValidationPage workspace={workspace} metaCols={[]}/>);
const panelStart=page.indexOf('class="writeST card"');assert.ok(panelStart>0);
assert.ok(!page.slice(0,panelStart).includes('Generate Write ST'));
assert.ok(page.slice(panelStart).includes('Generate ST</button>'));
const noProject=renderToStaticMarkup(<WriteSTGenerator workspace={{...workspace,localProjectPath:''}}/>);
assert.ok(noProject.includes('Select a project to begin'));
assert.ok(/disabled=""[^>]*>[\s\S]*?Generate ST<\/button>/.test(noProject));
console.log('Write ST UI checks passed: panel action, selected project, empty project and toolbar placement.');
