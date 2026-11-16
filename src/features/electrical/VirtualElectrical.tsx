import {useState} from 'react';
import {ReconstructionWorkspace} from './ReconstructionWorkspace';
import {IndustrialControl} from './IndustrialControl';
import {confirmNavigation} from '../../shared/navigation';
export function VirtualElectrical(){const [view,setView]=useState('control');return <div className="industrial-workspace"><header className="industrial-heading"><div><small>VIRTUAL ELECTRICAL</small><h1>Industrial control workspace</h1><p>Build and test control circuits. Review imported drawings with their source evidence.</p></div><nav aria-label="Industrial workspace views">{[['control','Control circuit'],['drawing','Drawing reconstruction']].map(([key,label])=><button className="btn" key={key} aria-pressed={view===key} onClick={()=>{if(confirmNavigation())setView(key)}}>{label}</button>)}</nav></header><div hidden={view!=='control'}><IndustrialControl/></div>{view==='drawing'&&<ReconstructionWorkspace/>}</div>}
