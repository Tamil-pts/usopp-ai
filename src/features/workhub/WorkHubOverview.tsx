import {FileText,Plus,Settings2} from 'lucide-react';
import './workhub-simple.css';
export function WorkHubOverview({onCustomize,onNewProject,onNewDocument}:{onCustomize:()=>void;onNewProject:()=>void;onNewDocument:()=>void}){
 return <section className="wh-simple-overview"><header className="wh-simple-hero"><div><span className="workHubEyebrow">PROJECTS &middot; PEOPLE &middot; PROGRESS</span><h1>WorkHub</h1><p>A clear view of your projects, work and approvals.</p></div><div className="actions"><button className="btn" onClick={onCustomize}><Settings2 size={16}/>Customize dashboard</button><button className="btn" onClick={onNewDocument}><FileText size={16}/>Create document</button><button className="btn primary" onClick={onNewProject}><Plus size={16}/>New project</button></div></header></section>;
}
