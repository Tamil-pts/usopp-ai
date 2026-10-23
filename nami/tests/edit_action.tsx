import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import type {MetadataItem,PLCConfig} from '../src/types';

// Only the browser location is needed by the UI cache's module initializer.
Object.assign(globalThis,{location:{pathname:'/nami/'},window:new EventTarget()});
const {GroupDataView}=await import('../src/components/GroupDataView');
const {ParameterEditModal}=await import('../src/components/ParameterEditModal');
const {activateUserStorage,userStorage}=await import('../../src/shared/userStorage');
activateUserStorage({id:987});
userStorage.setItem('nami_write_example',JSON.stringify({port:21011}));
assert.equal(JSON.parse(userStorage.getItem('nami_write_example')!).port,21011);

const writable:MetadataItem={sNo:1,screenName:'Settings',machineVariants:'BOTH',parameter:'Writable setting',units:'',min:0,max:400,
 tagCode:1,groupCode:130,offset:0,fromVersion:'1',toVersion:'1',dataType:'UINT',offsetFactor:1,scaleFactor:1,isVisible:true,isWritable:true};
const readonly={...writable,tagCode:2,offset:2,parameter:'Readonly setting',isWritable:false};
const props={groupCode:130,metadataItems:[writable,readonly],onPollGroup:()=>{},isPolling:false,searchQuery:'',dataModelCheck:null,
 missingDataModelParameters:[],dataModelReferences:new Map(),referenceData:{models:[],loading:false,error:null} as any,
 onOpenDataModels:()=>{},onEditParameter:()=>{}};
const html=renderToStaticMarkup(<GroupDataView {...props}/>);
assert.ok(html.includes('aria-label="Edit Writable setting"'));
assert.ok(!html.includes('aria-label="Edit Readonly setting"'));
assert.ok(!renderToStaticMarkup(<GroupDataView {...props} readOnly/>).includes('aria-label="Edit Writable setting"'));
const plc:PLCConfig={id:'example',name:'Example PLC',ip:'127.0.0.1',port:21010,machineId:7,isSimulated:false,endianness:'little',timeoutMs:1000};
const modalProps={item:writable,plc,metadata:[writable],metadataSource:'Example',onClose:()=>{},onWritten:()=>{}};
const modal=renderToStaticMarkup(<ParameterEditModal {...modalProps}/>);
assert.ok(modal.includes('Edit PLC parameter'));
assert.ok(modal.includes('Read current settings'));
assert.ok(modal.includes('Settings TCP port'));
const ybs=renderToStaticMarkup(<ParameterEditModal {...modalProps} plc={{...plc,frameProtocol:'ybs'}}/>);
assert.ok(ybs.includes('YBS needs a verified settings write protocol'));
assert.ok(!ybs.includes('Send to PLC and verify'));
console.log('DataInspect edit action: writable/readonly/history, editor and YBS checks passed.');
activateUserStorage(null);
