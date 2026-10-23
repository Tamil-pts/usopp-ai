import type {PLCConfig,SpinningMachineType} from '../types';

export type FrameProtocol=NonNullable<PLCConfig['frameProtocol']>;
export const frameProtocol=(plc:PLCConfig):FrameProtocol=>plc.frameProtocol??(plc.machineType==='YBS'?'ybs':'spinconnect');
export const isYbsTarget=(plc:PLCConfig)=>frameProtocol(plc)==='ybs';
export const frameProtocolLabel=(plc:PLCConfig)=>isYbsTarget(plc)?'Server → YBS':'Server → B&R';
export const metadataMachine=(plc:PLCConfig):SpinningMachineType=>isYbsTarget(plc)?'YBS':plc.machineType==='YBS'?'Carding':plc.machineType||'Carding';
export function frameProtocolUpdates(plc:PLCConfig,protocol:FrameProtocol):Partial<PLCConfig>{
 return {frameProtocol:protocol,...(protocol!==frameProtocol(plc)?{liveEnabled:false,liveGroupCodes:[]}:{}),
  ...(protocol==='ybs'?{endianness:'big',isSimulated:false,targetMode:'plc'}:{endianness:frameProtocol(plc)==='spinconnect'?plc.endianness:'little'})};
}
