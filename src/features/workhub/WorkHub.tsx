import {Activity,ArrowRight,ArrowUpRight,BookOpen,Bot,Cpu,FileCode2,GitCompare,HelpCircle,Layers,ShieldCheck} from 'lucide-react';
import type {EngineeringFeature} from '../../shared/features';
import './workhub.css';

type WorkHubProps={onOpen:(feature:EngineeringFeature|'help')=>void};

const tasks=[
  {id:'validation',name:'ByteMap',label:'Map your PLC data',description:'Review packet structures, byte offsets and HMI mappings. Generate and inspect metadata workbooks.',detail:'Source → metadata',Icon:Layers},
  {id:'plc',name:'DataInspect',label:'Inspect packet values',description:'Decode live or recorded PLC packets and compare values with the selected machine metadata.',detail:'Packets → values',Icon:Activity},
  {id:'compare',name:'MatchView',label:'Understand what changed',description:'Compare Automation Studio revisions and trace changes in logic, configuration and HMI screens.',detail:'Revisions → differences',Icon:GitCompare},
  {id:'rules',name:'LogicScan',label:'Review logic requirements',description:'Run your configured engineering rules and follow each finding back to its source evidence.',detail:'Requirements → evidence',Icon:ShieldCheck}
] as const;

export function WorkHub({onOpen}:WorkHubProps){
  return <div className="workHubDashboard">
    <header className="workHubHeading">
      <div><span className="workHubEyebrow">YOUR ENGINEERING WORKSPACE</span><h1>WorkHub</h1></div>
      <button className="workHubHelp" onClick={()=>onOpen('help')}><HelpCircle size={17}/><span>Workspace guide</span><ArrowUpRight size={15}/></button>
    </header>

    <section className="workHubHero" aria-labelledby="workhub-welcome">
      <div className="workHubHeroContent">
        <span className="workHubHeroEyebrow"><span/>FROM SOURCE TO INSIGHT</span>
        <h2 id="workhub-welcome">Engineering.<br/><em>Connected.</em></h2>
        <p>Map PLC data, inspect communication and understand your logic. Bring the evidence together for your next engineering decision.</p>
        <div className="workHubHeroActions">
          <button className="workHubPrimary" onClick={()=>onOpen('validation')}>Start with ByteMap<ArrowRight size={18}/></button>
          <button className="workHubSecondary" onClick={()=>onOpen('chatbot')}><Bot size={18}/>Ask Chopper<ArrowUpRight size={16}/></button>
        </div>
      </div>
      <div className="workHubIllustration" aria-hidden="true">
        <div className="workHubDiagramGrid"/>
        <svg className="workHubConnectors" viewBox="0 0 500 300" preserveAspectRatio="none"><path d="M125 67 H185 Q205 67 205 87 V115 Q205 135 225 135 H250 M375 67 H315 Q295 67 295 87 V115 Q295 135 275 135 H250 M125 230 H185 Q205 230 205 210 V180 Q205 160 225 160 H250 M375 230 H315 Q295 230 295 210 V180 Q295 160 275 160 H250"/></svg>
        <div className="workHubDiagramNode workHubDiagramSource"><FileCode2 size={20}/><div><b>PLC source</b><span>Logic & configuration</span></div></div>
        <div className="workHubDiagramNode workHubDiagramMetadata"><Layers size={20}/><div><b>Metadata</b><span>Mapping & structure</span></div></div>
        <div className="workHubDiagramCore"><Cpu size={30}/><span>Engineering<br/>context</span></div>
        <div className="workHubDiagramNode workHubDiagramPackets"><Activity size={20}/><div><b>Communication</b><span>Packets & values</span></div></div>
        <div className="workHubDiagramNode workHubDiagramRules"><BookOpen size={20}/><div><b>Requirements</b><span>Rules & evidence</span></div></div>
      </div>
    </section>

    <section className="workHubTools" aria-labelledby="workhub-tools">
      <div className="workHubSectionHeading"><div><span className="workHubEyebrow">PICK UP YOUR NEXT TASK</span><h2 id="workhub-tools">What would you like to work on?</h2></div><p>Purposeful tools. One connected workspace.</p></div>
      <div className="workHubToolLayout">
        <div className="workHubTaskGrid">{tasks.map(({id,name,label,description,detail,Icon})=><button className="workHubTask" key={id} onClick={()=>onOpen(id)}>
          <div className="workHubTaskTop"><span className="workHubToolIcon"><Icon size={22}/></span><span className="workHubToolName">{name}</span><ArrowUpRight className="workHubTaskArrow" size={20}/></div>
          <h3>{label}</h3><p>{description}</p><span className="workHubTaskDetail">{detail}<ArrowRight size={16}/></span>
        </button>)}</div>
        <aside className="workHubChopper" aria-labelledby="workhub-chopper">
          <div className="workHubChopperIdentity"><span><Bot size={25}/></span><div><b>Chopper</b><small>AI Assistant</small></div><span className="workHubChopperMark">SOURCE AWARE</span></div>
          <h3 id="workhub-chopper">Understand<br/> how it works.</h3>
          <p>Ask about machine functions, trace a subroutine or explain a finding using the selected project’s evidence.</p>
          <ul><li><FileCode2 size={16}/>Machine & subroutine explanations</li><li><GitCompare size={16}/>Changes & troubleshooting</li><li><BookOpen size={16}/>Rules & engineering knowledge</li></ul>
          <button onClick={()=>onOpen('chatbot')}>Open Chopper<ArrowRight size={18}/></button>
          <small className="workHubChopperHint">Attach a project or log to give your question context.</small>
        </aside>
      </div>
    </section>

    <div className="workHubClosing"><span>LESS GUESSWORK. MORE ENGINEERING.</span><p>Connected tools. Traceable results. Confident decisions.</p></div>
  </div>;
}
