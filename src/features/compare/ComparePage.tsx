import {CompareModule} from './CompareModule';

import {type ComponentProps,type ReactNode} from 'react';
import {CircuitCompare} from './CircuitCompare';
import './circuit-compare.css';

export function ComparePage({type,projectLink,...props}:ComponentProps<typeof CompareModule>&{type:'plc'|'circuit';projectLink?:ReactNode}){
 return <div className="matchviewTypes"><div hidden={type!=='plc'}><CompareModule {...props} projectLink={type==='plc'?projectLink:undefined}/></div><div hidden={type!=='circuit'}><CircuitCompare projectLink={type==='circuit'?projectLink:undefined}/></div></div>;
}
