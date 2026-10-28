import {lazy,Suspense,useEffect,useState} from 'react';
import {useAccount} from '../../account/AuthProvider';
import {api,type Row} from './api';
import './growth.css';
const Performance=lazy(()=>import('./PerformanceDashboard'));
const Passport=lazy(()=>import('./ContributionPassport'));

export default function WorkHubGrowth({view,articleId,evidenceId,revisionId,openToken,onView,onArticle,onProject}:{view:string;articleId?:string;evidenceId?:string;revisionId?:string;openToken?:number;onView:(view:string)=>void;onArticle:(id:string,revision?:string)=>void;onProject:(project:string,item?:string)=>void}){
  const {user}=useAccount(),[metadata,setMetadata]=useState<Row|null>(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;setMetadata(null);setError('');const controller=new AbortController();void api('/metadata',undefined,undefined,controller.signal).then(value=>{if(active)setMetadata(value);}).catch(problem=>{if(active&&problem.name!=='AbortError')setError(problem.message);});return()=>{active=false;controller.abort();};},[user.id]);
  if(error)return <section className="card"><p className="wh-error" role="alert">{error}</p></section>;
  if(!metadata)return <section className="card" role="status">Opening WorkHub contributions…</section>;
  return <Suspense fallback={<section className="card" role="status">Opening {['performance','teamperformance'].includes(view)?'Performance & Capability':'TechShare'}…</section>}>{['performance','teamperformance'].includes(view)?<Performance key={view} initialView={view==='teamperformance'?'team':'individual'} metadata={metadata} onProject={onProject} onArticle={(id,revision)=>{onArticle(id,revision);onView('passport');}}/>:<Passport metadata={metadata} initialArticle={articleId} initialEvidence={evidenceId} initialRevision={revisionId} openToken={openToken} onProject={onProject}/>}</Suspense>;
}
