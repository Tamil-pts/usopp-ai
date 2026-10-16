import type {PLCConfig} from '../types';
export const targetMode=(plc:PLCConfig)=>plc.targetMode||(plc.isSimulated?'data-simulator':'plc');
export const targetModeLabel=(plc:PLCConfig)=>({'plc':'Real PLC · Network TCP','automation-studio':'Automation Studio simulation · TCP','data-simulator':'Data simulator · Virtual PLC TCP'})[targetMode(plc)];
export function migrateTarget(plc:PLCConfig):PLCConfig{
 if(plc.isSimulated)return {...plc,targetMode:'data-simulator',isSimulated:false,ip:'127.0.0.1',port:21210,name:plc.name.replace(/\(?simulator\)?/i,'Data simulator'),liveEnabled:false,storeLiveData:false};
 return {...plc,targetMode:targetMode(plc),isSimulated:false};
}
