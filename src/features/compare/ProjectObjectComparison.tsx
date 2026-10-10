import React, {useEffect, useMemo, useState} from 'react';
import {BookOpen, Boxes, FileCode2, FileText, Folder, Search} from 'lucide-react';
import './project-object-comparison.css';

type Status = 'unchanged'|'modified'|'added'|'removed';
type ObjectNode = {key:string;name:string;relative_path?:string;kind?:string;description?:string;extension?:string;descriptor?:boolean;children:ObjectNode[]};
type Pair = {key:string;base?:ObjectNode;developed?:ObjectNode;children:Pair[];status:Status;changed:number;files:number;entry?:any};
type Row = {pair:Pair;depth:number;last:boolean;lines:boolean[]};

function fallbackTree(result:any, side:'base'|'developed'):ObjectNode[] {
  const paths = new Map<string,ObjectNode>();
  const ensure=(key:string,actual:string,file=false):ObjectNode=>{
    const existing=paths.get(key);if(existing)return existing;
    const node:ObjectNode={key,name:actual.split('/').pop()||key,relative_path:actual,kind:file?'file':'package',children:[]};
    if(file)node.extension=actual.slice(actual.lastIndexOf('.')).toLowerCase();
    paths.set(key,node);
    const parent=key.slice(0,key.lastIndexOf('/'));const actualParent=actual.slice(0,actual.lastIndexOf('/'));
    if(key.includes('/'))ensure(parent,actualParent).children.push(node);
    return node;
  };
  for(const entry of [...(result.diffs||[]),...(result.same_logic_files||[]),...(result.same_screen_files||[]),...(result.same_project_files||[])]){
    const actual=side==='base'?entry.base_relative_path:entry.new_relative_path;
    if(!actual&&(side==='base'?entry.status==='added':entry.status==='removed'))continue;
    ensure(entry.path,actual||entry.path,true);
  }
  const roots=[...(paths.get('Logical')?.children||[])];
  if(paths.has('Physical'))roots.push(paths.get('Physical')!);
  const files=[...paths.values()].filter(node=>!node.key.includes('/')&&!['Logical','Physical'].includes(node.key));
  if(files.length)roots.push({key:'$project-files',name:'Project files',kind:'package',descriptor:true,children:files});
  return roots;
}

function mergeTrees(base:ObjectNode[],developed:ObjectNode[],entries:Map<string,any>):Pair[] {
  const left=new Map(base.map(node=>[node.key,node])),right=new Map(developed.map(node=>[node.key,node]));
  return [...new Set([...left.keys(),...right.keys()])].map(key=>{
    const b=left.get(key),d=right.get(key),entry=entries.get(key);
    const children=mergeTrees(b?.children||[],d?.children||[],entries);
    const file=!!(b?.extension||d?.extension);
    const ownChange=!!b&&!!d&&['name','description','kind'].some(prop=>b[prop as keyof ObjectNode]!==d[prop as keyof ObjectNode]);
    const files=children.reduce((n,pair)=>n+pair.files,0)+(file?1:0);
    const status:Status=!b?'added':!d?'removed':ownChange?'modified':(entry?.status||(children.some(child=>child.status!=='unchanged')?'modified':'unchanged'));
    const changed=children.reduce((n,pair)=>n+pair.changed,0)+(file&&status!=='unchanged'?1:0);
    return {key,base:b,developed:d,children,status,changed,files,entry};
  });
}

function NodeIcon({node}:{node:ObjectNode}) {
  if(node.extension)return <span className="projectObjectFileIcon"><FileCode2 size={15}/><small>{node.extension.slice(1).toUpperCase()}</small></span>;
  if(node.kind==='library'||node.kind==='libraries')return <BookOpen size={16} className="library"/>;
  if(node.kind==='program')return <Boxes size={16} className="program"/>;
  if(node.kind==='dataobject')return <FileText size={16} className="dataobject"/>;
  return <Folder size={16} className="package"/>;
}

export function ProjectObjectComparison({result,onOpen}:{result:any;onOpen:(entry:any)=>void}) {
  const [expanded,setExpanded]=useState<Set<string>>(()=>new Set(['$project','Logical/Libraries','Physical']));
  const [query,setQuery]=useState('');
  const [status,setStatus]=useState('all');
  const [descriptors,setDescriptors]=useState(false);
  const baseName=result.baseName||result.knowledge?.base?.project_name||'Base project';
  const newName=result.newName||result.knowledge?.developed?.project_name||'Developed project';
  const complete=!!result.knowledge?.base?.project_tree&&!!result.knowledge?.developed?.project_tree;
  const pairs=useMemo(()=>{
    const entries=new Map<string,any>([...(result.diffs||[]),...(result.same_logic_files||[]),...(result.same_screen_files||[]),...(result.same_project_files||[])].map(entry=>[entry.path,entry]));
    return mergeTrees(result.knowledge?.base?.project_tree?.children||fallbackTree(result,'base'),result.knowledge?.developed?.project_tree?.children||fallbackTree(result,'developed'),entries);
  },[result]);
  const allFolders=useMemo(()=>{
    const keys=['$project'];const visit=(nodes:Pair[])=>nodes.forEach(node=>{if(node.children.length){keys.push(node.key);visit(node.children)}});visit(pairs);return keys;
  },[pairs]);
  useEffect(()=>{if(query.trim()||status!=='all')setExpanded(new Set(allFolders))},[query,status,allFolders]);
  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    const visit=(nodes:Pair[],parentMatch=false):Pair[]=>nodes.flatMap(pair=>{
      if(/\.(pkg|prg)$/i.test(pair.base?.name||pair.developed?.name||''))return [];
      if(!descriptors&&(pair.base?.descriptor||pair.developed?.descriptor))return [];
      const text=[pair.base?.name,pair.developed?.name,pair.base?.relative_path,pair.developed?.relative_path,pair.base?.description,pair.developed?.description].join(' ').toLowerCase();
      const match=parentMatch||!!needle&&text.includes(needle);
      const children=visit(pair.children,match);
      const statusMatch=status==='all'||(status==='changed'?pair.status!=='unchanged':pair.status===status);
      return children.length||statusMatch&&(!needle||match)?[{...pair,children}]:[];
    });return visit(pairs);
  },[pairs,query,status,descriptors]);
  const rows:Row[]=[];
  const flatten=(nodes:Pair[],depth=1,lines:boolean[]=[])=>nodes.forEach((pair,index)=>{
    const last=index===nodes.length-1;rows.push({pair,depth,last,lines});
    if(expanded.has(pair.key))flatten(pair.children,depth+1,[...lines,!last]);
  });
  if(expanded.has('$project'))flatten(filtered);
  const toggle=(key:string)=>setExpanded(previous=>{const next=new Set(previous);next.has(key)?next.delete(key):next.add(key);return next});
  const statusLabel={unchanged:'Same',modified:'Modified',added:'Added',removed:'Removed'};
  const cell=(row:Row,side:'base'|'developed')=>{
    const {pair,last,lines}=row,node=pair[side];
    return <td className={`projectObjectName ${node?pair.status:'absent'}`} data-side={side}>
      <div className="projectObjectLine" title={node?.relative_path||'Object not present in this project'}>
        <span className="projectObjectIndent" aria-hidden="true">{lines.map((line,i)=><i key={i} className={line?'vertical':''}/>)}<i className={last?'elbow':'junction'}/></span>
        {pair.children.length?<button className="projectObjectToggle" aria-label={`${expanded.has(pair.key)?'Collapse':'Expand'} ${node?.name||(pair.base||pair.developed)?.name} (${side==='base'?baseName:newName})`} aria-expanded={expanded.has(pair.key)} onClick={()=>toggle(pair.key)}>{expanded.has(pair.key)?'−':'+'}</button>:<span className="projectObjectToggleSpacer"/>}
        {node?<><NodeIcon node={node}/>{pair.entry?<button className="projectObjectOpen" aria-label={`Open comparison for ${node.relative_path||pair.key} (${side==='base'?baseName:newName})`} onClick={()=>onOpen(pair.entry)}>{node.name}</button>:<span className="projectObjectLabel">{node.name}</span>}<span className={`projectObjectStatus ${pair.status}`} title={`${statusLabel[pair.status]}${pair.children.length?` · ${pair.changed} changed file(s)`:' — open to inspect'}`}>{pair.status==='unchanged'?'=':pair.status==='modified'?'→':pair.status==='added'?'+':'−'}{pair.children.length&&pair.changed>0?<small>{pair.changed}</small>:null}</span></>:<span className="projectObjectAbsent">Not present</span>}
      </div>
    </td>;
  };
  return <section className="projectObjectComparison" aria-label="Project object comparison">
    <div className="projectObjectHeading"><div><h2>Project objects</h2><p>Expand programs, packages and libraries. Open a file to inspect its comparison.</p></div><div className="projectObjectCounts"><span>{result.summary?.modified||0} modified</span><span>{result.summary?.added||0} added</span><span>{result.summary?.removed||0} removed</span></div></div>
    <div className="projectObjectToolbar"><label><Search size={15}/><input aria-label="Search project objects" placeholder="Find an object, file or description…" value={query} onChange={event=>setQuery(event.target.value)}/></label><label>Show <select aria-label="Project object status" value={status} onChange={event=>setStatus(event.target.value)}><option value="all">All objects</option><option value="changed">Changed only</option><option value="modified">Modified</option><option value="added">Added</option><option value="removed">Removed</option></select></label><label><input type="checkbox" checked={descriptors} onChange={event=>setDescriptors(event.target.checked)}/> Project descriptors</label><button onClick={()=>setExpanded(new Set(allFolders))}>Expand all</button><button onClick={()=>setExpanded(new Set(['$project']))}>Collapse all</button><span className="projectObjectLegend"><i>→ Modified</i><i>+ Added</i><i>− Removed</i><i>= Same</i></span></div>
    {!complete&&<p className="projectObjectNotice">This saved comparison contains a partial file inventory. Rerun it to load all project objects, library files and source descriptions.</p>}
    <div className="projectObjectScroll"><table aria-label="Base and Developed project objects"><colgroup><col style={{width:'31%'}}/><col style={{width:'19%'}}/><col style={{width:'31%'}}/><col style={{width:'19%'}}/></colgroup><thead><tr className="projectObjectProjects"><th colSpan={2} className="base"><span>BASE / REFERENCE</span>{baseName}<small>{result.projects?.base?.active_configuration||'No active configuration'}</small></th><th colSpan={2} className="developed"><span>DEVELOPED / COMPARE</span>{newName}<small>{result.projects?.developed?.active_configuration||'No active configuration'}</small></th></tr><tr><th>Object Name</th><th>Description</th><th>Object Name</th><th>Description</th></tr></thead><tbody>
      <tr className="projectObjectRoot">{(['base','developed'] as const).map(side=><React.Fragment key={side}><td><button className="projectObjectToggle" aria-label={`${expanded.has('$project')?'Collapse':'Expand'} project roots`} aria-expanded={expanded.has('$project')} onClick={()=>toggle('$project')}>{expanded.has('$project')?'−':'+'}</button><Folder size={17}/><b>{side==='base'?baseName:newName}</b></td><td>{side==='base'?result.knowledge?.base?.project_tree?.file_count:result.knowledge?.developed?.project_tree?.file_count} {complete?'scoped files':'project'}</td></React.Fragment>)}</tr>
      {rows.map(row=><tr key={row.pair.key} data-object-key={row.pair.key} data-depth={row.depth} data-status={row.pair.status}>{cell(row,'base')}<td className={(row.pair.base?.description||'')!==(row.pair.developed?.description||'')?'descriptionChanged':''}>{row.pair.base?.description||'—'}</td>{cell(row,'developed')}<td className={(row.pair.base?.description||'')!==(row.pair.developed?.description||'')?'descriptionChanged':''}>{row.pair.developed?.description||'—'}</td></tr>)}
      {!rows.length&&expanded.has('$project')&&<tr><td colSpan={4} className="projectObjectEmpty">No objects match the selected filters.</td></tr>}
    </tbody></table></div>
  </section>;
}
