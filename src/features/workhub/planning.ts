import type {HubRow} from './projectApi';
export const PHASE_NAMES:Record<string,string>={development:'Development',quality:'Quality check',release:'Release'};
export const METHODS:Record<string,string>={waterfall:'Waterfall',agile:'Agile',sprint:'Sprint',custom:'Custom'};
export const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const addDays=(day:string,days:number)=>{const date=new Date(day+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+days);return date.toISOString().slice(0,10);};
export function templatePlan(method:string,start:string,sprintDays=14,count=2){
  const sprintCount=method==='sprint'?1:Math.max(1,Math.min(24,count)),length=Math.max(3,Math.min(60,sprintDays));
  const developmentDays=['agile','sprint'].includes(method)?length*sprintCount:20;
  const phases=[{phase:'development',title:'Development',start_date:start,due_date:addDays(start,developmentDays-1)},
    {phase:'quality',title:'Quality check',start_date:addDays(start,developmentDays),due_date:addDays(start,developmentDays+4)},
    {phase:'release',title:'Release',start_date:addDays(start,developmentDays+5),due_date:addDays(start,developmentDays+6)}];
  const sprints=['agile','sprint'].includes(method)?Array.from({length:sprintCount},(_,index)=>({id:'draft-sprint-'+index,title:'Sprint '+(index+1),goal:'',start_date:addDays(start,index*length),due_date:addDays(start,(index+1)*length-1)})):[];
  return {phases,sprints};
}
export function timelineRows(detail:HubRow):HubRow[]{
  const phases=detail.phases||[],sprints=detail.sprints||[],tasks=detail.tasks||[],rows:HubRow[]=[detail.project];
  for(const code of Object.keys(PHASE_NAMES)){
    const planned=phases.find((row:HubRow)=>row.phase===code);if(planned)rows.push(planned);
    const work=tasks.filter((row:HubRow)=>(row.work_phase||'development')===code);
    rows.push(...work.filter((row:HubRow)=>!row.sprint_id||!sprints.some((sprint:HubRow)=>sprint.id===row.sprint_id)));
    if(code==='development')for(const sprint of sprints){rows.push(sprint,...work.filter((row:HubRow)=>row.sprint_id===sprint.id));}
  }
  return rows;
}
