import {useEffect,useState} from 'react';
import {Activity,ArrowDown,Clock3,History,RefreshCw,Users} from 'lucide-react';
import './workhub-activity.css';

type ActivityData={
  scope:'all'|'own';days:number;totalRuns:number;generatedAt:string;timezone:string;
  daily:{date:string;count:number}[];
  users:{id:number|string|null;username:string;count:number;lastRunAt:string;tools:string[]}[];
  tools:{kind:string;label:string;count:number}[];
  recent:{id:string;kind:string;toolLabel:string;projectName:string;machineDepartment:string;
    createdAt:string;completedAt:string|null;user:{id:number|string|null;username:string}|null;status:string;testId:string}[];
};

function localTimestamp(value:string|null|undefined){
  if(!value)return 'Time not recorded';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'Time not recorded':date.toLocaleString(undefined,
    {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}

function chartDate(value:string,short=false){
  const date=new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime())?value:date.toLocaleDateString(undefined,
    short?{day:'numeric',timeZone:'UTC'}:{month:'short',day:'numeric',timeZone:'UTC'});
}

function viewSavedHistory(){
  const history=document.querySelector<HTMLElement>('.workHubPage .adminHistory');
  if(!history)return;
  history.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
  const heading=history.querySelector<HTMLElement>('h2');
  if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}
}

export function WorkHubActivity({active}:{active:boolean}){
  const [days,setDays]=useState<7|30>(7);
  const [revision,setRevision]=useState(0);
  const [data,setData]=useState<ActivityData|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();
    setLoading(true);setError('');
    void fetch(`/api/history/activity?days=${days}`,{cache:'no-store',credentials:'same-origin',signal:controller.signal})
      .then(async response=>{
        const payload=await response.json();
        if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:'Engineering activity could not be loaded.');
        if(!Array.isArray(payload.daily)||!Array.isArray(payload.recent)||!Array.isArray(payload.users)||!Array.isArray(payload.tools))throw new Error('The activity response is incomplete. Refresh to try again.');
        if(!controller.signal.aborted)setData(payload);
      }).catch((reason:unknown)=>{
        if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Engineering activity could not be loaded.');
      }).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[active,days,revision]);
  const current=data?.days===days?data:null;
  const maxDaily=Math.max(1,...(current?.daily||[]).map(point=>point.count));
  const maxTool=Math.max(1,...(current?.tools||[]).map(tool=>tool.count));
  return <section className="workHubActivity" aria-labelledby="workhub-activity" aria-busy={loading}>
    <header className="workHubActivityHeading">
      <div><span className="workHubEyebrow">THE WORK BEHIND THE WORKSPACE</span><h2 id="workhub-activity">{current?.scope==='own'?'Your engineering activity':'Engineering activity'}</h2><p>{current?.scope==='all'?'Saved activity across all users.':current?.scope==='own'?'Your saved work across the engineering tools.':'Saved runs, the people behind them and the tools they use.'}</p></div>
      <div className="workHubActivityControls"><div className="workHubActivityRange" role="group" aria-label="Activity period">{([7,30] as const).map(period=><button key={period} aria-pressed={days===period} onClick={()=>setDays(period)}>{period} days</button>)}</div><button className="workHubActivityRefresh" onClick={()=>setRevision(value=>value+1)} disabled={loading} aria-label="Refresh engineering activity"><RefreshCw size={17}/><span>{loading?'Loading':'Refresh'}</span></button></div>
    </header>
    {error?<div className="workHubActivityState workHubActivityError" role="alert"><History size={25}/><div><b>Activity is unavailable</b><p>{error}</p></div><button className="btn" onClick={()=>setRevision(value=>value+1)}>Try again</button></div>
      :!current?<div className="workHubActivityState" role="status"><Activity size={25}/><div><b>Loading engineering activity</b><p>Reading saved run history for the selected period.</p></div></div>
      :current.totalRuns===0?<div className="workHubActivityState"><History size={28}/><div><b>No saved activity in the last {days} days</b><p>Run ByteMap, DataInspect, MatchView or LogicScan to build an activity history. Metadata generation and data model reviews are included.</p></div></div>
      :<>
        <div className="workHubActivityOverview">
          <div className="workHubActivityChartPanel">
            <div className="workHubActivitySubheading"><div><h3>Activity over time</h3><p><b>{current.totalRuns}</b> saved {current.totalRuns===1?'run':'runs'} in the last {days} days</p></div><span><Clock3 size={13}/>Daily totals · {current.timezone||'UTC'}</span></div>
            <div className="workHubActivityChart" role="img" aria-label={`${current.totalRuns} saved engineering runs over ${days} days. Daily values are available below.`}>
              <div className="workHubActivityAxis" aria-hidden="true"><span>{maxDaily}</span><span>{maxDaily/2}</span><span>0</span></div>
              <div className="workHubActivityBars" style={{gridTemplateColumns:`repeat(${current.daily.length},minmax(0,1fr))`}} aria-hidden="true">{current.daily.map((point,index)=><div className="workHubActivityDay" key={point.date} title={`${chartDate(point.date)}: ${point.count} saved ${point.count===1?'run':'runs'}`}><div className="workHubActivityBarTrack"><span className={point.count?'workHubActivityBar':'workHubActivityBar workHubActivityBarZero'} style={{height:point.count?`${Math.max(3,point.count/maxDaily*100)}%`:'2px'}}/>{days===7&&point.count>0&&<small className="workHubActivityBarValue" style={{bottom:`calc(${point.count/maxDaily*100}% + 5px)`}}>{point.count}</small>}</div><span className="workHubActivityDayLabel">{days===7||index%5===0||index===current.daily.length-1?chartDate(point.date,days===30):' '}</span></div>)}</div>
            </div>
            <details className="workHubActivityDaily"><summary>View daily totals</summary><dl>{current.daily.map(point=><div key={point.date}><dt>{chartDate(point.date)}</dt><dd>{point.count} {point.count===1?'run':'runs'}</dd></div>)}</dl></details>
          </div>
          <aside className="workHubActivityBreakdown" aria-label="Engineering activity breakdown">
            <div className="workHubActivityTools"><h3>Tools in use</h3>{current.tools.map(tool=><div className="workHubActivityTool" key={tool.kind}><div><span>{tool.label}</span><b>{tool.count}</b></div><span className="workHubActivityToolTrack"><span style={{width:`${tool.count/maxTool*100}%`}}/></span></div>)}</div>
            <div className="workHubActivityPeople"><h3><Users size={16}/>{current.scope==='all'?'People contributing':'Your saved activity'}</h3>{current.users.slice(0,4).map(person=><div className="workHubActivityPerson" key={person.id??'unattributed'}><span aria-hidden="true">{person.username.slice(0,2).toUpperCase()}</span><div><b>{person.username}</b><small title={person.tools.join(', ')}>{person.tools.join(', ')||'Engineering tools'}</small></div><span>{person.count} {person.count===1?'run':'runs'}</span></div>)}{current.users.length>4&&<small className="workHubActivityPeopleMore">{current.users.length-4} more {current.users.length-4===1?'user':'users'} in this period</small>}{!current.users.length&&<p className="workHubActivityPeopleMore">User details were not recorded for these earlier runs.</p>}</div>
          </aside>
        </div>
        <div className="workHubActivityRecent"><div className="workHubActivityRecentHeading"><div><h3>Recent work</h3><p>{current.scope==='all'?'Who worked on what, and when.':'Your latest saved engineering runs.'}</p></div><button onClick={viewSavedHistory}>View saved history<ArrowDown size={15}/></button></div><ol>{current.recent.slice(0,6).map(run=><li key={run.id}><span className="workHubActivityAvatar" aria-hidden="true">{run.user?.username?.slice(0,2).toUpperCase()||'—'}</span><div className="workHubActivityRun"><div><b>{run.user?.username||'User not recorded'}</b><span>{run.toolLabel}</span></div><p title={run.projectName}>{run.projectName||'Untitled run'}{run.machineDepartment&&run.machineDepartment!=='All'&&<small>{run.machineDepartment}</small>}</p></div><div className="workHubActivityRunTime"><time dateTime={run.createdAt} title={run.createdAt}>{localTimestamp(run.createdAt)}</time><span>{({running:'Running',completed:'Saved',failed:'Processing failed',interrupted:'Interrupted'} as Record<string,string>)[run.status]||run.status||'Saved'}</span></div></li>)}</ol></div>
        <footer className="workHubActivityFooter"><span>Activity uses recorded run times; daily totals use {current.timezone||'UTC'}. Event times use your local timezone. Earlier imports without a recorded run time remain in saved history.</span><span>Updated {localTimestamp(current.generatedAt)}</span></footer>
      </>}
  </section>;
}
