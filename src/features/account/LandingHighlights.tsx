import {Activity,ArrowRight,BookOpen,BriefcaseBusiness,CircuitBoard,ClipboardCheck,FilePenLine,GitCompare,MessageSquare,UsersRound} from 'lucide-react';
import './landing-highlights.css';

const modules=[
 {name:'WorkHub',Icon:BriefcaseBusiness,label:'Keep delivery connected',text:'Plan projects, assign work, manage documents and follow reviews through quality closure.'},
 {name:'ByteMap',Icon:ClipboardCheck,label:'Trace packet structure',text:'Check SpinConnect layouts, offsets, metadata and HMI mappings against source evidence.'},
 {name:'DataInspect',Icon:Activity,label:'Inspect communication data',text:'Decode live or captured PLC packets and YBS frames. Build dashboards around the selected target.'},
 {name:'MatchView',Icon:GitCompare,label:'Review every revision',text:'Compare PLC projects and electrical drawings, then export source-linked change reports.'},
 {name:'LogicScan',Icon:BookOpen,label:'Apply engineering checks',text:'Run configured rules and feature pipelines. Review findings, accepted alternatives and evidence.'},
 {name:'e-design',Icon:FilePenLine,label:'Mark up and review drawings',text:'Add revision clouds, highlights and reference-linked comments. Track corrections and export reviews.'},
 {name:'Chopper',Icon:MessageSquare,label:'Investigate with context',text:'Explore PLC source, machine names, settings and engineering documents. Review the evidence and unresolved checks.'},
 {name:'Virtual workspaces',Icon:CircuitBoard,label:'Explore a model before testing',text:'Inspect supported PLC models or edit native electrical circuits and run supported component simulations.'},
];
const stages=[
 ['Define','Capture projects, meetings and requirements.'],
 ['Plan','Assign resources, responsibilities and delivery dates.'],
 ['Develop','Complete development tasks and required deliverables.'],
 ['Validate','Review the saved report and revalidate corrections.'],
 ['Release','Check quality, applicable FAT and independent approval.'],
 ['Close','Verify final deliverables, handover and acceptance.'],
];
export function LandingHighlights(){return <>
 <section id="accountWorkHub" className="landingWorkHub" aria-labelledby="landingWorkHubTitle">
  <div className="landingSectionHeading"><span className="accountEyebrow">WORKHUB / PROJECT DELIVERY</span><h2 id="landingWorkHubTitle">From the first requirement to the final handover.</h2><p>Give every task an owner, every revision a history and every review a clear next step.</p></div>
  <ol className="landingWorkflow" aria-label="Project delivery workflow">{stages.map(([title,text],i)=><li key={title}><span className="landingStepNumber">0{i+1}</span><h3>{title}</h3><p>{text}</p>{i<stages.length-1&&<ArrowRight size={16} aria-hidden="true"/>}</li>)}</ol>
  <div className="landingWorkHubDetails"><article><UsersRound size={20}/><div><h3>People & capacity</h3><p>Team availability, resource assignments, workload and delivery progress in one view.</p></div></article><article><FilePenLine size={20}/><div><h3>Controlled documents</h3><p>MOM, FRD, revisions, review comments, requirement links and approval history.</p></div></article><article><ClipboardCheck size={20}/><div><h3>Quality & knowledge</h3><p>Test evidence, FAT, nonconformances, closure gates and reviewed reusable knowledge.</p></div></article></div>
 </section>
 <section id="accountFeatures" className="accountPlatform landingModules" aria-labelledby="accountPlatformHeading"><div className="landingSectionHeading"><span className="accountEyebrow">CONNECTED ENGINEERING TOOLS</span><h2 id="accountPlatformHeading">The tools for the work. The context to connect it.</h2><p>Move between project delivery, PLC checks, drawing reviews and investigation within your account's enabled modules.</p></div><div className="landingModuleGrid">{modules.map(({name,Icon,label,text})=><article key={name}><span className="landingModuleIcon"><Icon size={21}/></span><h3>{name}</h3><strong>{label}</strong><p>{text}</p></article>)}</div><p className="landingModelNote">AI suggestions and simulation models support engineering review. Physical tests, signatures and approvals remain with the responsible engineer.</p></section>
 </>;}
