import {Boxes,Braces,CircuitBoard,ClipboardList,CloudCog,Cog,Cpu,Factory,FileText,FlaskConical,Gauge,Layers3,MonitorCog,Network,Radio,Settings2,Workflow,Zap} from 'lucide-react';
import type {HubRow} from './projectApi';

// A project keeps the same illustration through sorting, filtering and reloads.
const hash=(value:string)=>{let result=2166136261;for(const char of value){result^=char.charCodeAt(0);result=Math.imul(result,16777619);}return result>>>0;};
const accents=[Cog,Gauge,Boxes,Workflow,Network,Radio,Settings2,Layers3];
const general=[Factory,CloudCog,ClipboardList,Layers3];
function symbol(kind:string,seed:number){
 const value=kind.toLowerCase();
 if(/plc|automation|control/.test(value))return seed%2?Cpu:CircuitBoard;
 if(/electri|circuit|cad|wiring/.test(value))return Zap;
 if(/hmi|screen|panel/.test(value))return MonitorCog;
 if(/document|report|quality/.test(value))return FileText;
 if(/software|code|program/.test(value))return Braces;
 if(/research|test|laboratory/.test(value))return FlaskConical;
 return general[seed%general.length];
}
export function ProjectArtwork({project,size='banner'}:{project:HubRow;size?:'thumbnail'|'banner'|'feature'}){
 const seed=hash(String(project.id||project.project_number||project.title||''));
 const Main=symbol(String(project.kind||''),seed),Accent=accents[(seed>>>3)%accents.length];
 return <span className={`pp-art pp-art-${size} pp-art-palette-${seed%8} pp-art-pattern-${(seed>>>8)%4}`} aria-hidden="true"><span className="pp-art-orbit pp-art-orbit-one"/><span className="pp-art-orbit pp-art-orbit-two"/><span className="pp-art-grid"/><span className="pp-art-main"><Main strokeWidth={1.6}/></span><span className="pp-art-accent"><Accent strokeWidth={1.8}/></span><span className="pp-art-spark pp-art-spark-one"/><span className="pp-art-spark pp-art-spark-two"/></span>;
}
