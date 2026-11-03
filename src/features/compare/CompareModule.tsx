import {userStorage} from '../../shared/userStorage';
import {CompareReports} from './CompareReports';
import './compare.css';
import React,{useEffect,useState} from 'react';
import {LayoutDashboard,FolderOpen,ArrowRightLeft,Table2,SlidersHorizontal,MessageSquare,Settings,Download,FileText,ChevronRight,Clock3,Search,Sparkles,FolderTree,FileSpreadsheet,Play,Plus,Trash2,Save,RefreshCw,ShieldCheck,Upload,CheckCircle2,AlertTriangle,AlertCircle,XCircle,Eye,GitCompare,GitCompareArrows,BookOpen,ChevronDown,Minus,X,Monitor,Folder,FileCode2,ChevronsDownUp,ChevronsUpDown} from 'lucide-react';
import {downloadCSV} from '../../shared/download';
import {LocalFolderTree} from '../../shared/LocalFileBrowser';
import {ResizeHandle} from './ResizeHandle';
import {CompareView} from './CompareView';
import {matchesChange,type ChangeStatus} from './sourceRows';
import {FunctionFlow} from './FunctionFlow';
import {HmiScreenPreview} from './HmiScreenPreview';
import {HmiPropertyComparison} from './HmiPropertyComparison';
import {TextGroupComparison} from './TextGroupComparison';
import {ProjectObjectComparison} from './ProjectObjectComparison';
import {useLinkedScroll} from './useLinkedScroll';
import {LadderDiagram} from './LadderDiagram';
import {ProcessingTimePopup} from '../../shared/ProcessingTimePopup';
import {ChopperSummary} from './ChopperSummary';
import {filterHmiDifferences,skipHmiProperty} from './hmiDifferenceFilter';
import {TreeWidthHandle} from './TreeWidthHandle';

function generateCompareReport(result:any){
  const s=result?.summary||{};const kb=result?.knowledge||{};const diffs:any[]=result?.diffs||[];
  const base=result?.baseName||'Base';const dev=result?.newName||'Developed';
  const cCol:Record<string,string>={logic:'#3b82f6',screen:'#22c55e',hardware:'#f59e0b',config:'#94a3b8'};
  const sCol:Record<string,string>={added:'#22c55e',removed:'#ef4444',modified:'#f59e0b'};
  const esc=(s:string)=>String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const splitHunkHtml=(hunk:any)=>{
    const rows=(hunk.lines||[]).map((l:any)=>{
      const bg=l.t==='add'?'#f0fdf4':l.t==='del'?'#fef2f2':'';
      const pfx=l.t==='add'?'+':l.t==='del'?'-':' ';
      const pfxCol=l.t==='add'?'#16a34a':l.t==='del'?'#dc2626':'#94a3b8';
      return `<tr style="background:${bg}"><td style="color:#94a3b8;padding:0 5px;font-size:9px;user-select:none;min-width:30px;text-align:right">${l.bl??''}</td><td style="color:${pfxCol};padding:0 3px;font-weight:700">${pfx}</td><td style="white-space:pre-wrap;word-break:break-all;padding:0 6px">${esc(l.text)}</td><td style="color:#94a3b8;padding:0 5px;font-size:9px;user-select:none;min-width:30px;text-align:right">${l.nl??''}</td></tr>`;
    }).join('');
    return `<table style="width:100%;font-family:Consolas,monospace;font-size:10px;border-collapse:collapse"><thead><tr style="background:#f1f5f9"><td colspan="2" style="padding:2px 8px;font-size:9px;color:#64748b">BASE</td><td colspan="2" style="padding:2px 8px;font-size:9px;color:#64748b;text-align:right">NEW</td></tr></thead><tbody>${rows}</tbody></table>`;
  };
  const parsedScreenHtml=(ps:any)=>{
    if(!ps?.parsed||!ps.changes?.length)return '';
    const rows=ps.changes.map((c:any)=>{
      if(c.type==='control_added')return `<tr><td><span style="color:#16a34a;font-weight:700">+ Added</span></td><td><b>${esc(c.name)}</b> <span style="color:#94a3b8">${esc(c.class)}</span></td><td></td></tr>`;
      if(c.type==='control_removed')return `<tr><td><span style="color:#dc2626;font-weight:700">- Removed</span></td><td><b>${esc(c.name)}</b> <span style="color:#94a3b8">${esc(c.class)}</span></td><td></td></tr>`;
      const propRows=(c.changes||[]).map((p:any)=>`<tr style="font-size:9px"><td style="padding-left:16px;color:#94a3b8">Property: ${esc(p.prop)}</td><td style="color:#dc2626;text-decoration:line-through">${esc(String(p.from??''))}</td><td style="color:#16a34a">to ${esc(String(p.to??''))}</td></tr>`).join('');
      return `<tr><td><span style="color:#f59e0b;font-weight:700">~ Modified</span></td><td><b>${esc(c.name)}</b> <span style="color:#94a3b8">${esc(c.class)}</span></td><td></td></tr>${propRows}`;
    }).join('');
    return `<div style="font-family:system-ui;font-size:10px;margin:6px 0"><b style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.04em">HMI Control Changes</b><table style="width:100%;border-collapse:collapse;margin-top:4px"><thead><tr style="background:#f8fafc;font-size:9px;color:#64748b"><th style="text-align:left;padding:3px 6px">Change</th><th style="text-align:left;padding:3px 6px">Control</th><th style="text-align:left;padding:3px 6px">Value</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  };
  const parsedHwHtml=(ph:any)=>{
    if(!ph?.parsed||!ph.changes?.length)return '';
    const rows=ph.changes.map((c:any)=>{
      if(c.type==='module_added')return `<tr><td><span style="color:#16a34a;font-weight:700">+ Added</span></td><td><b>${esc(c.name)}</b> <span style="color:#94a3b8">${esc(c.module_type)}</span></td><td style="color:#16a34a">${esc(c.version)}</td></tr>`;
      if(c.type==='module_removed')return `<tr><td><span style="color:#dc2626;font-weight:700">- Removed</span></td><td><b>${esc(c.name)}</b></td><td></td></tr>`;
      const subRows=(c.changes||[]).map((p:any)=>`<tr style="font-size:9px"><td style="padding-left:16px;color:#94a3b8">Property: ${esc(p.field)}</td><td style="color:#dc2626;text-decoration:line-through">${esc(String(p.from??''))}</td><td style="color:#16a34a">to ${esc(String(p.to??''))}</td></tr>`).join('');
      return `<tr><td><span style="color:#f59e0b;font-weight:700">~ Modified</span></td><td><b>${esc(c.name)}</b> <span style="color:#94a3b8">${esc(c.module_type)}</span></td><td></td></tr>${subRows}`;
    }).join('');
    return `<div style="font-family:system-ui;font-size:10px;margin:6px 0"><b style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.04em">Module Changes</b><table style="width:100%;border-collapse:collapse;margin-top:4px"><thead><tr style="background:#f8fafc;font-size:9px;color:#64748b"><th style="text-align:left;padding:3px 6px">Change</th><th style="text-align:left;padding:3px 6px">Module</th><th style="text-align:left;padding:3px 6px">Version / Value</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  };
  const catSections=(['logic','screen','hardware','config'] as const).map(cat=>{
    const entries=diffs.filter(d=>d.category===cat);
    if(!entries.length)return '';
    const fileRows=entries.map(d=>{
      const folder=String(d.subroutine||'').split('/').slice(0,-1).join('/');
      const parsedHtml=d.parsed_screen?parsedScreenHtml(d.parsed_screen):d.parsed_hardware?parsedHwHtml(d.parsed_hardware):'';
      const hunkHtml=parsedHtml?parsedHtml:(d.hunks||[]).slice(0,20).map(splitHunkHtml).join('');
      const logicHtml=(d.logic_added?.length||d.logic_removed?.length)?`<div style="padding:6px 10px;background:#fffbeb;border-top:1px solid #fef9c3;font-size:10px">
        ${d.logic_added?.length?`<div style="font-weight:600;color:#15803d;margin-bottom:3px">+ ${d.logic_added.length} statement(s) added</div>${d.logic_added.slice(0,15).map((l:string)=>`<pre style="margin:1px 0;padding:1px 6px;font-family:Consolas,monospace;font-size:9px;color:#15803d;white-space:pre-wrap">${esc(l)}</pre>`).join('')}`:''}
        ${d.logic_removed?.length?`<div style="font-weight:600;color:#dc2626;margin-bottom:3px">- ${d.logic_removed.length} statement(s) removed</div>${d.logic_removed.slice(0,15).map((l:string)=>`<pre style="margin:1px 0;padding:1px 6px;font-family:Consolas,monospace;font-size:9px;color:#dc2626;white-space:pre-wrap">${esc(l)}</pre>`).join('')}`:''}
      </div>`:'';
      return `<div class="fe"><div class="fh">
        <span class="badge" style="color:${sCol[d.status]||'#64748b'}">${d.status.toUpperCase()}</span>
        <code class="fp">${esc(d.path)}</code>
        ${folder?`<span class="sub">Subroutine: ${esc(folder)}</span>`:''}
        <span class="cnt">+${d.added_lines?.length||0} / -${d.removed_lines?.length||0}</span>
      </div>${logicHtml}${hunkHtml?`<div class="db">${hunkHtml}</div>`:''}</div>`;
    }).join('');
    return `<section><h2 style="color:${cCol[cat]}">${cat.toUpperCase()} CHANGES - ${entries.length} file(s)</h2>${fileRows}</section>`;
  }).join('');
  const kbCard=(side:any,label:string)=>`<div class="kb"><h3>${esc(label)}</h3>
    <div class="ks"><span>${side?.total_files||0} files</span><span>${side?.logic_files||0} logic</span><span>${side?.screen_count||0} screens</span><span>${side?.hardware_files||0} hardware</span></div>
    <b style="font-size:10px">Subroutines:</b><div class="kl">${(side?.subroutines||[]).map((x:any)=>`<div>${esc(x.path)}: ${(x.files||[]).join(', ')}</div>`).join('')}</div>
    <b style="font-size:10px">HMI Screens (${(side?.screens||[]).length}):</b><div class="kl">${(side?.screens||[]).join(', ')}</div>
  </div>`;
  const html=`<!DOCTYPE html><html><head><meta charset="UTF-8"/><title>uSOPp.ai Comparison Report</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:system-ui,sans-serif;color:#1e293b;background:#fff;padding:32px;max-width:1200px;margin:0 auto;font-size:13px}
h1{font-size:22px;font-weight:800;margin-bottom:2px}h2{font-size:13px;font-weight:700;margin:24px 0 8px;padding-bottom:5px;border-bottom:2px solid currentColor}h3{font-size:11px;font-weight:700;margin-bottom:8px}
.meta{color:#64748b;font-size:11px;margin-bottom:20px}.prj-header{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:20px}
.prj-card{font-size:10px}.prj-badge{display:inline-block;border-radius:3px;padding:2px 6px;font-weight:700;font-size:9px;margin-bottom:4px}.prj-path{font-family:monospace;font-size:9px;color:#475569;word-break:break-all}
.prj-arrow{display:flex;align-items:center;justify-content:center;font-size:20px;color:#94a3b8}
.sbar{display:flex;gap:10px;flex-wrap:wrap;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin-bottom:20px}
.sc{text-align:center;min-width:65px}.sc b{display:block;font-size:18px;font-weight:800}.sc span{font-size:9px;color:#64748b;text-transform:uppercase}
.kbg{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px}
.kb{border:1px solid #e2e8f0;border-radius:6px;padding:12px}.ks{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}.ks span{font-size:10px;background:#f1f5f9;padding:2px 6px;border-radius:3px}.kl{font-size:9px;font-family:monospace;color:#475569;max-height:100px;overflow-y:auto;margin:3px 0 8px}
section{margin-bottom:28px}
.fe{border:1px solid #e2e8f0;border-radius:5px;margin-bottom:8px;overflow:hidden}
.fh{display:flex;align-items:center;gap:6px;padding:6px 10px;background:#f8fafc;font-size:10px;flex-wrap:wrap}
.badge{font-size:9px;font-weight:700;font-family:monospace;background:#f1f5f9;padding:1px 5px;border-radius:3px}.fp{flex:1;word-break:break-all;font-size:10px}.sub{color:#3b82f6;font-size:9px;font-family:monospace}.cnt{font-size:9px;font-family:monospace;color:#64748b;white-space:nowrap}
.db{border-top:1px solid #e2e8f0;overflow-x:auto}
@media print{.db{max-height:none!important}h2{page-break-before:always}}
</style></head><body>
<h1>uSOPp Project Comparison Report</h1>
<p class="meta">Generated ${new Date().toLocaleString()} &nbsp;|&nbsp; uSOPp.ai</p>
<div class="prj-header">
  <div class="prj-card"><span class="prj-badge" style="background:#dbeafe;color:#1d4ed8">BASE / ORIGINAL</span><div class="prj-path">${esc(base)}</div></div>
  <div class="prj-arrow">to</div>
  <div class="prj-card"><span class="prj-badge" style="background:#dcfce7;color:#15803d">NEW / DEVELOPED</span><div class="prj-path">${esc(dev)}</div></div>
</div>
<div class="sbar">
  <div class="sc"><b style="color:#f59e0b">${s.modified||0}</b><span>Modified</span></div>
  <div class="sc"><b style="color:#22c55e">${s.added||0}</b><span>Added</span></div>
  <div class="sc"><b style="color:#ef4444">${s.removed||0}</b><span>Removed</span></div>
  <div class="sc"><b>${s.unchanged||0}</b><span>Unchanged</span></div>
  <div class="sc"><b>${s.total_in_base||0}</b><span>Base files</span></div>
  <div class="sc"><b>${s.total_in_new||0}</b><span>New files</span></div>
  <div class="sc"><b style="color:#3b82f6">${s.by_category?.logic||0}</b><span>Logic changes</span></div>
  <div class="sc"><b style="color:#22c55e">${s.by_category?.screen||0}</b><span>Screen changes</span></div>
  <div class="sc"><b style="color:#f59e0b">${s.by_category?.hardware||0}</b><span>Hardware changes</span></div>
</div>
<h2 style="color:#1e293b">Project Knowledge Base</h2>
<div class="kbg">${kbCard(kb.base,'BASE / '+esc(base))}${kbCard(kb.developed,'DEVELOPED / '+esc(dev))}</div>
${catSections}
<p style="color:#94a3b8;font-size:10px;text-align:center;margin-top:24px;padding-top:10px;border-top:1px solid #e2e8f0">uSOPp.ai | B&amp;R Automation Studio Project Comparison</p>
</body></html>`;
  const blob=new Blob([html],{type:'text/html'});const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;
  a.download=`uSOPp_Compare_${String(base).replace(/[^a-z0-9]/gi,'_')}_vs_${String(dev).replace(/[^a-z0-9]/gi,'_')}_${new Date().toISOString().slice(0,10)}.html`;
  a.click();URL.revokeObjectURL(url);
}

// â”€â”€ Split-view hunk component (BASE left | NEW right) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function SplitDiffHunk({hunk,baseLabel,newLabel}:{hunk:any,baseLabel:string,newLabel:string}){
  const linkedLines=useLinkedScroll();
  const lines:(any[])=hunk.lines||[];
  const ctx=(hunk.lines||[]).filter((l:any)=>l.t==='ctx').length;
  const addCnt=(hunk.lines||[]).filter((l:any)=>l.t==='add').length;
  const delCnt=(hunk.lines||[]).filter((l:any)=>l.t==='del').length;
  const lineRange=(values:any[])=>{const numbers=values.filter((value:any)=>value!=null&&Number.isFinite(Number(value))&&Number(value)>0).map(Number);if(!numbers.length)return 'No lines';const first=Math.min(...numbers),last=Math.max(...numbers);return first===last?`L${first}`:`L${first}-L${last}`};
  const baseRange=lineRange(lines.map((line:any)=>line.bl));
  const developedRange=lineRange(lines.map((line:any)=>line.nl));
  return <div className="splitHunk">
    <div className="splitHunkHeader">
      <span className="splitHunkPos">@@ -{hunk.base_start} +{hunk.new_start} @@</span>
      <span className="splitHunkBase">BASE: {baseLabel} | {baseRange}</span>
      <span className="splitHunkStats">{addCnt>0&&<span className="splitStatAdd">+{addCnt}</span>}{delCnt>0&&<span className="splitStatDel">-{delCnt}</span>}{ctx>0&&<span className="splitStatCtx">{ctx} ctx</span>}</span>
      <span className="splitHunkNew">DEVELOPED: {newLabel} | {developedRange}</span>
    </div>
    <div className="splitHunkBody">
      <div className="splitSideHead"><span className="splitSideLabel base">BASE</span><small>Line number</small></div>
      <div className="splitSideHead"><span className="splitSideLabel new_">DEVELOPED</span><small>Line number</small></div>
      <div className="splitSide" ref={linkedLines.refs[0]} onScroll={linkedLines.onScroll(0)}>
        {lines.filter((l:any)=>l.t!=='add').map((l:any,i:number)=>(
          <div key={i} className={'splitLine '+(l.status==='modified'?'modified':l.t==='del'?'del':l.t==='ctx'?'ctx':'')}>
            <span className="splitLn">{l.bl!=null?`L${l.bl}`:''}</span>
            <span className="splitPfx">{l.t==='del'?'-':' '}</span>
            <pre className="splitCode">{l.text}</pre>
          </div>
        ))}
      </div>
      <div className="splitSide" ref={linkedLines.refs[1]} onScroll={linkedLines.onScroll(1)}>
        {lines.filter((l:any)=>l.t!=='del').map((l:any,i:number)=>(
          <div key={i} className={'splitLine '+(l.status==='modified'?'modified':l.t==='add'?'add':l.t==='ctx'?'ctx':'')}>
            <span className="splitLn">{l.nl!=null?`L${l.nl}`:''}</span>
            <span className="splitPfx">{l.t==='add'?'+':' '}</span>
            <pre className="splitCode">{l.text}</pre>
          </div>
        ))}
      </div>
    </div>
  </div>;
}

// â”€â”€ Parsed HMI screen changes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function ParsedScreenView({data,baseLabel,newLabel,skipLayout=false}:{data:any;baseLabel:string;newLabel:string;skipLayout?:boolean}){
  const [propertyHeight,setPropertyHeight]=React.useState(900);
  const [selectedControl,setSelectedControl]=React.useState<string>('');
  const [showAll,setShowAll]=React.useState(false);
  const allControls=data?.controls||[];
  const controls=showAll?allControls:allControls.filter((control:any)=>control.status!=='unchanged');
  React.useEffect(()=>setSelectedControl(controls[0]?.name||''),[data?.object_name,data?.controls?.length,showAll,skipLayout]);
  const selected=controls.find((control:any)=>control.name===selectedControl)||controls[0];
  const recordProperties=(record:any)=>record?{...(record.name?{Name:record.name}:{}),...(record.class_id?{ClassId:record.class_id}:{}),...record.properties}:{};
  const base=selected?recordProperties(selected.base):(data?.base_page_properties||{}),developed=selected?recordProperties(selected.new):(data?.new_page_properties||{});
  if(!data?.parsed)return <div className="parsedEmpty">No structured B&amp;R HMI records were found in this file.</div>;
  if(data.text_group||data.entity_label==='Text group values')return <TextGroupComparison data={data} baseLabel={baseLabel} newLabel={newLabel}/>;
  return <div className="hmiInspector hmiSplitInspector">
    <div className="hmiInspectorTabs"><strong>{data.object_name||'HMI object'}</strong><span>{data.entity_label||'Structured HMI records'}</span><button className={!showAll?'active':''} onClick={()=>setShowAll(false)}>Changed only</button><button className={showAll?'active':''} onClick={()=>setShowAll(true)}>Show all</button></div>
    {(data.datasource_availability||[]).filter((item:any)=>item.status!=='available' && (!selected || item.name===selected.name)).map((item:any)=><div className="hmiMappingNotice" key={`${item.side}-${item.name}`}>{item.side==='base'?'Base':'Developed'} ? {item.name}: {item.status==='missing'?`Missing in local data source for active HMI ${item.target}`:'Select an active HMI to check this mapping'}. ConnectingVisus: {item.connectingVisus||'Not configured'}</div>)}
    <div className="hmiCompareLayout" style={{height:propertyHeight,flexShrink:0}}><aside className="hmiControlList"><div className="hmiControlListHead">{String(data.entity_label||'HMI ITEMS').toUpperCase()} ({controls.length})</div>{controls.map((control:any)=><button key={control.name} className={selected?.name===control.name?'active':''} onClick={()=>setSelectedControl(control.name)}><span className="hmiControlType">{control.class_id||control.class}</span><span>{control.name}</span><small>{control.status==='added'?'+ Added':control.status==='removed'?'- Removed':control.status==='unchanged'?'= Same':`Modified (${(control.changes||[]).length})`}</small></button>)}{!controls.length&&<div className="hmiNoChanges">No changed items. Select Show all to inspect the complete screen.</div>}</aside><HmiPropertyComparison base={base} developed={developed} baseLabel={baseLabel} newLabel={newLabel} contextKey={`${baseLabel}:${newLabel}:${data.object_name}:${selected?.name||'screen'}`} skipLayout={skipLayout} skipPageIndex={!selected||selected.name==='Screen properties'} baseMissing={!!selected&&!selected.base} newMissing={!!selected&&!selected.new}/></div><ResizeHandle height={propertyHeight} onChange={setPropertyHeight} label="structured HMI properties"/>
  </div>;
}

// â”€â”€ Parsed hardware changes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const isHardwareSupportModule=(item:any)=>{
  const properties=item?.properties||item?.base?.properties||item?.new?.properties||{};
  const identity=`${item?.['Module type']||properties['Module type']||''} ${item?.['Object name']||properties['Object name']||item?.name||''}`.toUpperCase().replace(/[^A-Z0-9]/g,'');
  return identity.includes('X20BM')||identity.includes('X20TB');
};
const logicSummaryLines=(entry:any,side:'base'|'new')=>{
 if(entry.source_rows?.length)return entry.source_rows.filter((r:any)=>r.status!=='unchanged'&&r[side+'_line']!=null&&String(r[side]||'').trim()).map((r:any)=>({line:r[side+'_line'],text:r[side]}));
 return (entry[side==='base'?'removed_lines':'added_lines']||[]).map((row:any)=>({line:Array.isArray(row)?row[0]:null,text:Array.isArray(row)?row[1]:String(row)}));
};
const visibleHardwareModules=(items:any[])=>(items||[]).filter((item:any)=>!isHardwareSupportModule(item));

function ParsedHardwareView({data}:{data:any}){
  const [showAll,setShowAll]=React.useState(false);
  const [selectedName,setSelectedName]=React.useState('');
    const all=data?.controls||[];
  const records=showAll?all:all.filter((item:any)=>item.status!=='unchanged');
  React.useEffect(()=>setSelectedName(records[0]?.name||''),[data?.entity_label,data?.controls?.length,showAll]);
  const selected=records.find((item:any)=>item.name===selectedName)||records[0];
  const base=selected?.base?.properties||{},developed=selected?.new?.properties||{};
  const keys=Object.keys(base).concat(Object.keys(developed)).filter((value,index,array)=>array.indexOf(value)===index);
  if(!data?.parsed)return <div className="parsedEmpty">No structured physical configuration records were found.</div>;
  return <div className="engineeringInspector">
    <div className="engineeringInspectorHead"><div><b>{data.entity_label||'Physical configuration'}</b><span>Active configuration engineering comparison</span></div><div><button className={!showAll?'active':''} onClick={()=>setShowAll(false)}>Changed only</button><button className={showAll?'active':''} onClick={()=>setShowAll(true)}>Show all</button></div></div>
    <div className="engineeringInspectorBody"><aside><div className="engineeringListTitle">{records.length} item(s)</div>{records.map((item:any)=><button key={item.name} className={selected?.name===item.name?'active':''} onClick={()=>setSelectedName(item.name)}><span className={`statusDot ${item.status}`}/><b>{item.name}</b><small>{item.class}</small><em>{item.status}</em></button>)}{!records.length&&<p>No changed items. Select Show all to inspect the complete configuration.</p>}</aside><section>{selected?<><header><div><span>Item</span><b>{selected.name}</b></div><div><span>Type</span><b>{selected.class}</b></div><em>{selected.status}</em></header><div className="engineeringPropertyHead"><span>Property</span><span>Base project</span><span>Developed project</span></div>{keys.map(key=><div className={'engineeringProperty '+(base[key]!==developed[key]?'changed':'')} key={key}><b>{key}</b><code>{String(base[key]??'?')}</code><code>{String(developed[key]??'?')}</code></div>)}</>:<div className="compareDarkEmpty">Select an item to inspect its properties.</div>}</section></div>
  </div>;
}

function ParsedLadderView({data,baseLabel,newLabel,testId}:{data:any;baseLabel:string;newLabel:string;testId?:string}){
  const linkedNetworks=useLinkedScroll<HTMLElement>();
  const linkedDiagrams=useLinkedScroll<HTMLDivElement>();
  const [ladderZoom,setLadderZoom]=React.useState(.75);
  const [showAll,setShowAll]=React.useState(() => !(data?.controls||[]).some((item:any)=>item.status!=='unchanged'));
  const [selectedKey,setSelectedKey]=React.useState('');
  const all=visibleHardwareModules(data?.controls||[]);
  const records=showAll?all:all.filter((item:any)=>item.status!=='unchanged');
  React.useEffect(()=>setSelectedKey(records[0]?.id||''),[data?.base_network_count,data?.new_network_count,showAll]);
  const selected=records.find((item:any)=>item.id===selectedKey)||records[0];
  const pane=(record:any,label:string,side:'base'|'developed')=><section className={`ladderNetworkPane ${side}`} ref={linkedNetworks.refs[side==='base'?0:1]} onScroll={linkedNetworks.onScroll(side==='base'?0:1)}>
    <header><span>{side==='base'?'BASE / REFERENCE':'DEVELOPED / COMPARE'}</span><b>{label}</b><small>{record?`Network ${record.index}`:'Network not present'}</small></header>
    {!record?<div className="ladderMissing">Not present in this project.</div>:<>
      <div className="ladderNetworkFacts"><span><b>Label</b>{record.label||'No label'}</span><span><b>Comment</b>{record.comment||'No comment'}</span><span><b>Rows</b>{record.rows}</span><span><b>State</b>{record.commented?'Commented':'Active'}</span></div>
      <details className="ladderLogicSummary"><summary>Logic summary and XML layout</summary><span>{record.summary||'Empty ladder network'}</span><small>{record.layout||'No row layout'}</small></details>
      <LadderDiagram network={record} other={side==='base'?selected?.new:selected?.base} side={side} status={selected?.status} testId={testId} zoom={ladderZoom} onZoom={setLadderZoom} viewportRef={linkedDiagrams.refs[side==='base'?0:1]} onScroll={linkedDiagrams.onScroll(side==='base'?0:1)} networks={all.map((item:any)=>side==='base'?item.base:item.new).filter(Boolean)}/>
      <details><summary>Element names, types and pins</summary><div className="ladderElementHead"><span>Element</span><span>Name / instance</span><span>Type and pins</span></div>
      <div className="ladderElements">{(record.elements||[]).map((element:any,index:number)=><div className="ladderElement" key={`${element.kind}-${element.name}-${index}`}><span>{element.kind}{element.branch&&<i>{element.branch}</i>}</span><b>{element.name||'Not assigned'}</b><code>{[element.type,element.position,(element.pins||[]).join(', ')].filter(Boolean).join(' | ')||'No additional properties'}</code></div>)}{!record.elements?.length&&<div className="ladderMissing">This ladder network is empty.</div>}</div></details>
    </>}
  </section>;
  if(!data?.parsed)return <div className="parsedEmpty">The ladder XML networks could not be read.</div>;
  return <div className="ladderInspector">
    <div className="engineeringInspectorHead"><div><b>Ladder network comparison</b><span>Base {data.base_network_count||0} networks | Developed {data.new_network_count||0} networks</span></div><div><button className={!showAll?'active':''} onClick={()=>setShowAll(false)}>Changed only</button><button className={showAll?'active':''} onClick={()=>setShowAll(true)}>Show all</button></div></div>
    <div className="ladderInspectorBody"><aside><div className="engineeringListTitle">{records.length} network(s)</div>{records.map((item:any)=><button key={item.id||`${item.name}-${item.base?.index||0}-${item.new?.index||0}`} className={selected===item?'active':''} onClick={()=>setSelectedKey(item.id||item.name)}><span className={`treeStatusIcon ${item.status}`}>{item.status==='added'?'+':item.status==='removed'?'-':item.status==='modified'?String.fromCharCode(8594):'='}</span><b>{item.name}</b><small>{item.status==='modified'?`${item.changes?.length||1} change(s)`:item.status}</small></button>)}{!records.length&&<p>No changed ladder networks. Select Show all to inspect every network.</p>}</aside>
      <div className="ladderDualPanes">{pane(selected?.base,baseLabel,'base')}{pane(selected?.new,newLabel,'developed')}</div>
    </div>
  </div>;
}

function HardwareProjectPane({kb,other,label,side,paneRef,onScroll}:{kb:any;other:any;label:string;side:'base'|'developed';paneRef:React.RefObject<HTMLElement|null>;onScroll:(event:React.UIEvent<HTMLElement>)=>void}){
  const modules=visibleHardwareModules(kb?.hardware_modules||[]);
  const otherModules=visibleHardwareModules(other?.hardware_modules||[]);
  const moduleKey=(module:any)=>String(module.Station||module['Object name']||module.name||'').toLowerCase();
  const otherByKey=new Map(otherModules.map((module:any)=>[moduleKey(module),module]));
  const mappingsFor=(module:any,source:any)=>{
    const objectName=String(module['Object name']||'').toLowerCase();
    const station=String(module.Station||'');
    const exact=(source?.io_mappings||[]).filter((mapping:any)=>String(mapping.Module||'').toLowerCase()===objectName);
    return exact.length?exact:(source?.io_mappings||[]).filter((mapping:any)=>station&&String(mapping.Station||'')===station);
  };
  const signature=(module:any,source:any)=>JSON.stringify({name:module?.['Object name'],type:module?.['Module type'],mappings:mappingsFor(module,source).map((mapping:any)=>[mapping.Channel,mapping['PLC tag'],mapping.Direction])});
  return <section className={`hardwareProjectPane ${side}`} ref={paneRef} onScroll={onScroll}>
    <header><span>{side==='base'?'BASE / REFERENCE':'DEVELOPED / COMPARE'}</span><b>{label}</b><small>{modules.length} hardware modules | {kb?.io_mappings?.length||0} mapped channels</small></header>
    <div className="hardwareModuleList">{modules.map((module:any)=>{
      const peer=otherByKey.get(moduleKey(module));
      const status=!peer?(side==='base'?'removed':'added'):(signature(module,kb)===signature(peer,other)?'unchanged':'modified');
      const mappings=mappingsFor(module,kb);
      return <details className={`hardwareModule ${status}`} key={`${module.Station}-${module['Object name']}`}>
        <summary><span className={`treeStatusIcon ${status}`}>{status==='added'?'+':status==='removed'?'-':status==='modified'?String.fromCharCode(8594):'='}</span><span className="hardwareStation">{module.Station||module.Order||'?'}</span><b>{module['Object name']||module.name}</b><code>{module['Module type']||'Unknown type'}</code><small>{mappings.length} mapped tags</small><ChevronRight size={14}/></summary>
        <div className="hardwareModuleBody"><div className="hardwareFacts"><span><b>Station</b>{module.Station||'Not assigned'}</span><span><b>Module type</b>{module['Module type']||'Not detected'}</span><span><b>Order</b>{module.Order||'Not detected'}</span></div>
          <div className="hardwareMappingHead"><span>Channel</span><span>Mapped PLC tag</span><span>Direction</span><span>Address</span></div>
          {mappings.map((mapping:any,index:number)=><div className="hardwareMappingRow" key={`${mapping.name}-${index}`}><code>{mapping.Channel||'Not available'}</code><b>{mapping['PLC tag']||'Not mapped'}</b><span>{mapping.Direction||'Not available'}</span><code>{mapping.Address||'Not available'}</code></div>)}
          {!mappings.length&&<div className="hardwareNoMappings">No mapped PLC tags were found for this module.</div>}
        </div>
      </details>;
    })}{!modules.length&&<div className="compareDarkEmpty">No hardware modules were found in the active configuration.</div>}</div>
  </section>;
}

function HardwareCompareView({base,new_,baseLabel,newLabel}:{base:any;new_:any;baseLabel:string;newLabel:string}){
  const linkedHardware=useLinkedScroll<HTMLElement>();
  return <div className="hardwareCompareView"><HardwareProjectPane kb={base} other={new_} label={baseLabel} side="base" paneRef={linkedHardware.refs[0]} onScroll={linkedHardware.onScroll(0)}/><HardwareProjectPane kb={new_} other={base} label={newLabel} side="developed" paneRef={linkedHardware.refs[1]} onScroll={linkedHardware.onScroll(1)}/></div>;
}

// â”€â”€ Updated DiffEntry with split view + project label â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function DiffEntry({entry,baseLabel,newLabel}:{entry:any,baseLabel:string,newLabel:string}){
  const [open,setOpen]=React.useState(false);
  const addedCount=entry.added_lines?.length||0;
  const removedCount=entry.removed_lines?.length||0;
  const folder=String(entry.subroutine||'').split('/').slice(0,-1).join('/');
  return <div className="diffEntry">
    <div className="diffEntryHead" onClick={()=>setOpen(o=>!o)}>
      <span style={{color:STATUS_COLOR[entry.status]||'var(--text)',fontWeight:700,minWidth:68,fontSize:9,fontFamily:'IBM Plex Mono'}}>{entry.status.toUpperCase()}</span>
      <span style={{color:CAT_COLOR[entry.category]||'var(--muted)',fontWeight:600,minWidth:60,fontSize:9,fontFamily:'IBM Plex Mono'}}>{entry.category}</span>
      <div style={{flex:1}}>
        <div style={{fontFamily:'IBM Plex Mono',fontSize:10,fontWeight:600}}>{entry.file_name||entry.path.split('/').pop()}</div>
        <div style={{fontSize:8.5,color:'var(--accent)',fontFamily:'IBM Plex Mono',marginTop:2}}>Folder: {entry.subroutine||folder}</div>
        <div style={{fontSize:8,color:'var(--faint)',fontFamily:'IBM Plex Mono',marginTop:1,display:'flex',gap:8}}>
          <span className="compareSideText base">BASE: {baseLabel}</span>
          <span>vs</span>
          <span className="compareSideText developed">DEVELOPED: {newLabel}</span>
        </div>
      </div>
      {addedCount>0&&<span className="diffStat add">+{addedCount}</span>}
      {removedCount>0&&<span className="diffStat del">-{removedCount}</span>}
      {entry.base_lines>0&&<span className="diffStat muted">{entry.base_lines} to {entry.new_lines||0} lines</span>}
      {open?<ChevronDown size={13}/>:<ChevronRight size={13}/>}
    </div>
    {open&&<div className="diffBody">
      {entry.logic_added?.length>0&&<div className="logicSummary add">
        <div className="logicSumTitle"><Plus size={10}/> {entry.logic_added.length} logic statement(s) added</div>
        {entry.logic_added.slice(0,20).map((l:string,i:number)=><div className="logicLine" key={i}>{l}</div>)}
      </div>}
      {entry.logic_removed?.length>0&&<div className="logicSummary del">
        <div className="logicSumTitle"><Minus size={10}/> {entry.logic_removed.length} logic statement(s) removed</div>
        {entry.logic_removed.slice(0,20).map((l:string,i:number)=><div className="logicLine" key={i}>{l}</div>)}
      </div>}
      {entry.parsed_screen&&<ParsedScreenView data={entry.parsed_screen} baseLabel={baseLabel} newLabel={newLabel}/>}
      {entry.parsed_hardware&&<ParsedHardwareView data={entry.parsed_hardware}/>}
      <div className="splitDiffWrap">
        {(entry.hunks||[]).slice(0,30).map((h:any,i:number)=>
          <SplitDiffHunk key={i} hunk={h} baseLabel={baseLabel} newLabel={newLabel}/>
        )}
        {entry.hunks?.length>30&&<div className="diffMore">... {entry.hunks.length-30} more sections; export JSON for the complete diff.</div>}
      </div>
    </div>}
  </div>;
}

// â”€â”€ KbPanel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function KbPanel({kb,label,expanded,onExpand}:{kb:any,label:string,expanded:Record<string,boolean>,onExpand:(key:string,value:boolean)=>void}){
  const taskGroups=(kb.task_assignments||[]).reduce((groups:any,item:any)=>{(groups[item['Task class']]??=[]).push(item);return groups},{});
  const ioGroups=(kb.io_mappings||[]).reduce((groups:any,item:any)=>{(groups[item.Module]??=[]).push(item);return groups},{});
  const hardwareModules=visibleHardwareModules(kb.hardware_modules||[]);
  return <div className="kbPanel knowledgePanel">
    <div className="kbPanelTitle">{label}</div>
    <div className="knowledgeIdentity"><div><span>Automation Studio</span><b>{kb.automation_studio_version||'?'}</b></div><div><span>Active configuration</span><b>{kb.active_configuration||'?'}</b></div><div><span>Active HMI</span><b>{kb.active_hmi||'?'}</b></div></div>
    <div className="kbStats"><div className="kbStat"><b>{kb.logic_files??0}</b><span>Logic files</span></div><div className="kbStat"><b>{kb.task_assignments?.length??0}</b><span>Assigned tasks</span></div><div className="kbStat"><b>{hardwareModules.length}</b><span>Modules</span></div><div className="kbStat"><b>{kb.io_mappings?.length??0}</b><span>I/O mappings</span></div></div>
    <details open={!!expanded["tasks"]} onToggle={event=>onExpand("tasks",event.currentTarget.open)}><summary>Cyclic task assignments ({kb.task_assignments?.length??0})</summary><div className="knowledgeDetails">{Object.entries(taskGroups).map(([taskClass,items]:any)=><div className="taskClassGroup" key={taskClass}><b>{taskClass}</b>{items.map((item:any)=><div key={item.name}><span>{item.name}</span><code>{item.Source||'?'}</code><small>{item.Language} {item.Disabled==='true'?'? Disabled':''}</small></div>)}</div>)}</div></details>
    <details open={!!expanded["objects"]} onToggle={event=>onExpand("objects",event.currentTarget.open)}><summary>Active software objects ({kb.active_objects?.length??0})</summary><div className="knowledgeCompactList">{(kb.active_objects||[]).map((item:any)=><div key={item.name}><b>{item.name}</b><span>{item.Memory}</span><em>{item.Enabled==='true'?'Enabled':'Disabled'}</em></div>)}</div></details>
    <details open={!!expanded["hardware"]} onToggle={event=>onExpand("hardware",event.currentTarget.open)}><summary>Hardware by station ({hardwareModules.length})</summary><div className="knowledgeTable"><div className="knowledgeTableHead"><span>Station</span><span>Object</span><span>Module type</span><span>Order</span></div>{hardwareModules.map((item:any)=><div key={item.name}><code>{item.Station||'?'}</code><b>{item.name}</b><span>{item['Module type']}</span><span>{item.Order}</span></div>)}</div></details>
    <details open={!!expanded["io"]} onToggle={event=>onExpand("io",event.currentTarget.open)}><summary>I/O mappings by module ({kb.io_mappings?.length??0})</summary><div className="knowledgeDetails">{Object.entries(ioGroups).map(([module,items]:any)=><div className="ioModuleGroup" key={module}><b>{module}</b>{items.map((item:any)=><div key={item.name}><code>{item.Channel}</code><span>{item['PLC tag']}</span><small>{item.Direction}</small></div>)}</div>)}</div></details>
    <details open={!!expanded["permanent"]} onToggle={event=>onExpand("permanent",event.currentTarget.open)}><summary>Permanent variables ({kb.permanent_variables?.length??0})</summary><div className="knowledgeCompactList">{(kb.permanent_variables||[]).map((item:any)=><div key={item.name}><b>{item.name}</b><code>{item.Address}</code></div>)}</div></details>
    <details open={!!expanded["logic"]} onToggle={event=>onExpand("logic",event.currentTarget.open)}><summary>Logical subroutines ({kb.subroutines?.length??0})</summary><div className="kbList">{(kb.subroutines||[]).map((item:any)=><div className="kbItem" key={item.path}><span className="kbPath">{item.path}</span><span className="kbFiles">{(item.files||[]).join(', ')}</span></div>)}</div></details>
    <details open={!!expanded["hmi"]} onToggle={event=>onExpand("hmi",event.currentTarget.open)}><summary>HMI screens ({kb.screens?.length??0})</summary><div className="kbList">{(kb.screens||[]).map((screen:string,index:number)=><div className="kbItem" key={`${screen}-${index}`}>{screen}</div>)}</div></details>
  </div>;
}

// â”€â”€ Compare file tree -------------------------------------------------------
type CompareTreeNode={name:string,path:string,children:CompareTreeNode[],diff?:any};
function buildCompareTree(items:any[]):CompareTreeNode[]{
  const root:CompareTreeNode={name:'root',path:'',children:[]};
  for(const d of items){
    const raw=String(d.tree_path||d.path||d.file_name||'').replace(/\\/g,'/');
    const parts=raw.split('/').filter(Boolean);
    let node=root;
    parts.forEach((part:string,idx:number)=>{
      let child=node.children.find((x:any)=>x.name===part);
      if(!child){child={name:part,path:parts.slice(0,idx+1).join('/'),children:[]};node.children.push(child)}
      node=child;
    });
    node.diff=d;
  }
  const sort=(nodes:CompareTreeNode[])=>{nodes.sort((a,b)=>{const af=!!a.diff,bf=!!b.diff;if(af!==bf)return af?1:-1;return a.name.localeCompare(b.name)});nodes.forEach(n=>sort(n.children))};
  sort(root.children);return root.children;
}
function CompareTree({items,selectedIndex,onSelect,baseLabel,newLabel,searching=false}:{items:any[],selectedIndex:number,onSelect:(i:number)=>void;baseLabel:string;newLabel:string;searching?:boolean}){
  const [open,setOpen]=React.useState<Set<string>>(()=>new Set());
  const [selectedFolder,setSelectedFolder]=React.useState('');
  const tree=React.useMemo(()=>buildCompareTree(items),[items]);
  const normalizedPath=(entry:any)=>String(entry.tree_path||entry.path||entry.file_name||'').replace(/\\/g,'/');
  const flat=new Map(items.map((entry:any,index:number)=>[normalizedPath(entry),index]));
  const folders=React.useMemo(()=>{
    const paths:string[]=[];const visit=(nodes:CompareTreeNode[])=>nodes.forEach(node=>{if(!node.diff){paths.push(node.path);visit(node.children)}});visit(tree);return paths;
  },[tree]);
  const treeSignature=folders.join('|');
  React.useEffect(()=>{
    setOpen(previous=>searching?new Set(folders):new Set([...previous].filter(path=>folders.includes(path)).concat(tree.filter(node=>!node.diff).map(node=>node.path))));
  },[treeSignature,searching]);
  const selectedPath=items[selectedIndex]?normalizedPath(items[selectedIndex]):'';
  React.useEffect(()=>{
    if(!selectedPath)return;
    const parts=selectedPath.split('/');setOpen(previous=>{const next=new Set(previous);for(let i=1;i<parts.length;i++)next.add(parts.slice(0,i).join('/'));return next});
    setSelectedFolder('');
  },[selectedPath]);
  const toggle=(path:string)=>{setSelectedFolder(path);setOpen(previous=>{const next=new Set(previous);next.has(path)?next.delete(path):next.add(path);return next})};
  const countFiles=(node:CompareTreeNode):number=>node.diff?1:node.children.reduce((count,child)=>count+countFiles(child),0);
  const render=(nodes:CompareTreeNode[],depth=0):React.ReactNode=>nodes.map(node=>{
    const index=node.diff?flat.get(node.path):-1;
    const isOpen=open.has(node.path);
    if(node.diff){
      const entry=node.diff,status=entry.status||'unchanged';const count=(entry.added_lines?.length||0)+(entry.removed_lines?.length||0);
      const baseName=entry.base_file_name||(status==='added'?'Not present':node.name);
      const developedName=entry.new_file_name||(status==='removed'?'Not present':node.name);
      const provenanceDiffers=baseName!==developedName;
      return <button key={node.path} className={'compareTreeLeaf '+(index===selectedIndex&&!selectedFolder?'active':'')} style={{paddingLeft:12+depth*18}} aria-current={index===selectedIndex&&!selectedFolder?'true':undefined} title={`${node.path}\nBase: ${baseName}\nDeveloped: ${developedName}\n${status}`} onClick={()=>{setSelectedFolder('');onSelect(index??0)}}>
        <span className="compareTreeChevronSpacer"/>{/\.(var|typ)$/i.test(node.name)?<FileSpreadsheet size={15}/>:<FileCode2 size={15}/>}<span className="compareTreeLeafText"><span className="compareTreeLeafName">{node.name}</span>{provenanceDiffers&&<small><b>B:</b> {baseName} <b>D:</b> {developedName}</small>}</span><span className={`treeStatusIcon ${status}`} aria-label={status}>{status==='added'?'+':status==='removed'?'-':status==='modified'?'~':'='}</span>{count>0&&<span className="compareTreeCount" title={`${count} changed lines`}>{count}</span>}
      </button>;
    }
    return <div key={node.path} className="compareTreeNode">
      <button className={'compareTreeFolder '+(selectedFolder===node.path?'active':'')} aria-expanded={isOpen} aria-label={`${isOpen?'Collapse':'Expand'} ${node.path}`} title={node.path} style={{paddingLeft:12+depth*18}} onClick={()=>toggle(node.path)}>{isOpen?<ChevronDown size={14} className="compareTreeChevron"/>:<ChevronRight size={14} className="compareTreeChevron"/>}{isOpen?<FolderOpen size={17}/>:<Folder size={17}/>}<span className="compareTreeFolderName">{node.name}</span><span className="compareTreeCount">{countFiles(node)}</span></button>
      {isOpen&&<div className="compareTreeChildren">{render(node.children,depth+1)}</div>}
    </div>;
  });
  return <nav className="compareTree" aria-label="Comparison project explorer"><div className="compareTreeActions"><span><FolderTree size={16}/> Project explorer</span><button type="button" title="Expand all folders" aria-label="Expand all comparison folders" onClick={()=>setOpen(new Set(folders))}><ChevronsUpDown size={15}/></button><button type="button" title="Collapse all folders" aria-label="Collapse all comparison folders" onClick={()=>setOpen(new Set())}><ChevronsDownUp size={15}/></button></div><div className="compareTreeProjects"><span className="base" title={baseLabel}><b>BASE</b><span>{baseLabel}</span></span><span className="developed" title={newLabel}><b>DEVELOPED</b><span>{newLabel}</span></span></div><div className="compareTreeContent">{tree.length?render(tree):<div className="compareDarkEmpty">No files match this view.</div>}</div></nav>;
}

type CompareFilter='all'|'logic'|'screen'|'hardware'|'config';
const CAT_COLOR:Record<string,string>={logic:'var(--accent)',screen:'var(--pass)',hardware:'var(--warn)',config:'var(--muted)'};
const STATUS_COLOR:Record<string,string>={added:'var(--pass)',removed:'var(--fail)',modified:'var(--warn)'};

export function CompareModule({
  result, compareFiles, setCompareFiles, compareBasePath, setCompareBasePath,
  compareNewPath, setCompareNewPath, baseProjectInfo, newProjectInfo,
  baseHmi, setBaseHmi, newHmi, setNewHmi,
  runCompare, busy, progress, consoleOpen, setConsoleOpen, projectLink
}:{result:any,compareFiles:any,setCompareFiles:any,compareBasePath:string,setCompareBasePath:(s:string)=>void,
  compareNewPath:string,setCompareNewPath:(s:string)=>void,baseProjectInfo:any,newProjectInfo:any,
  baseHmi:string,setBaseHmi:(s:string)=>void,newHmi:string,setNewHmi:(s:string)=>void,
  runCompare:()=>void,busy:boolean,progress:any,
  consoleOpen:boolean,setConsoleOpen:(v:boolean)=>void,projectLink?:React.ReactNode}){

  const baseRef=React.useRef<HTMLInputElement>(null);
  const newRef=React.useRef<HTMLInputElement>(null);
  const [chopperSummaryOpen,setChopperSummaryOpen]=React.useState(false);
  const [workspacePages,setWorkspacePages]=React.useState(2),[workspaceHeight,setWorkspaceHeight]=React.useState<number|null>(null);
  const [baseBrowserOpen,setBaseBrowserOpen]=React.useState(false);
  const [newBrowserOpen,setNewBrowserOpen]=React.useState(false);
  const [filter,setFilter]=React.useState<CompareFilter>('logic');
  const [treeWidth,setTreeWidth]=useState(()=>{try{const width=Number(userStorage.getItem('usopp_compare_tree_width'));return width>=200&&width<=650?width:300}catch{return 300}});
  const resizeTree=(width:number)=>{setTreeWidth(width);try{userStorage.setItem('usopp_compare_tree_width',String(width))}catch{}};
  const [search,setSearch]=React.useState('');
  const [activeTab,setActiveTab]=React.useState<'changes'|'summary'|'knowledge'>('changes');
  const [fileStatus,setFileStatus]=React.useState<ChangeStatus>('all');
  const [workspaceStatus,setWorkspaceStatus]=React.useState<ChangeStatus>('all');
  const [treeScope,setTreeScope]=React.useState<'all'|'base'|'developed'>('all');
  const [selectedIndex,setSelectedIndex]=React.useState(0);
  const [hmiView,setHmiView]=React.useState<'structured'|'preview'>('structured');
  const [skipHmiLayout,setSkipHmiLayout]=React.useState(false);
  const [sourceView,setSourceView]=React.useState<'difference'|'source'|'diagram'|'flow'>('difference');

  const summary=result?.summary||{};
  const knowledge=result?.knowledge||{};
  const knowledgeScroll=useLinkedScroll<HTMLDivElement>();
  const [expandedKnowledge,setExpandedKnowledge]=React.useState<Record<string,boolean>>({tasks:true});
  const expandKnowledge=(key:string,value:boolean)=>setExpandedKnowledge(previous=>previous[key]===value?previous:{...previous,[key]:value});
  React.useEffect(()=>{
    const frame=requestAnimationFrame(()=>{
      const left=knowledgeScroll.refs[0].current?.querySelectorAll('details'),right=knowledgeScroll.refs[1].current?.querySelectorAll('details');
      if(!left||!right)return;
      left.forEach((item,index)=>{if(right[index]){item.style.minHeight='';right[index].style.minHeight='';const height=Math.max(item.getBoundingClientRect().height,right[index].getBoundingClientRect().height);item.style.minHeight=`${height}px`;right[index].style.minHeight=`${height}px`;}});
    });return()=>cancelAnimationFrame(frame);
  },[expandedKnowledge,result,activeTab]);
  const baseLabel=result?.baseName||'Base Project';
  const newLabel=result?.newName||'Developed Project';
  const projectInfo=result?.projects||{};
  const cats:CompareFilter[]=['all','logic','screen','hardware','config'];

  const viewItems:any[]=[...(result?.diffs||[]),...(['all','unchanged'].includes(fileStatus)?[...(result?.same_logic_files||[]),...(result?.same_screen_files||[]),...(result?.same_project_files||[])]:[])];
  const diffs:any[]=viewItems.filter((d:any)=>
    !/\.(pkg|prg)$/i.test(String(d.path||''))&&(filter==='all'||d.category===filter)&&
    matchesChange(d.status,fileStatus)&&
    (!search||String(d.path||'').toLowerCase().includes(search.toLowerCase())||String(d.subroutine||'').toLowerCase().includes(search.toLowerCase())||String(d.file_name||'').toLowerCase().includes(search.toLowerCase()))
  );
  const treeItems=diffs.filter((d:any)=>treeScope==='all'||(treeScope==='base'&&d.base_file_name)||(treeScope==='developed'&&d.new_file_name)).map((d:any)=>({...d,tree_path:treeScope==='base'?(d.base_relative_path||d.path):treeScope==='developed'?(d.new_relative_path||d.path):d.path}));

  const openProjectObject=(entry:any)=>{
    setTreeScope('all');setFileStatus('all');setSearch('');setFilter(entry.category as CompareFilter);
    const entries=[...(result?.diffs||[]),...(result?.same_logic_files||[]),...(result?.same_screen_files||[]),...(result?.same_project_files||[])].filter(item=>item.category===entry.category&&!/\.(pkg|prg)$/i.test(item.path||''));
    setSelectedIndex(Math.max(0,entries.findIndex(item=>item.path===entry.path)));
    setSourceView(/\.ld$/i.test(entry.path||'')?'diagram':entry.status==='unchanged'&&entry.source_view_available?'source':'difference');
    setActiveTab('changes');
  };

  React.useEffect(()=>{
    if(!treeItems.length){setSelectedIndex(0);return;}
    if(selectedIndex>=treeItems.length)setSelectedIndex(0);
  },[filter,fileStatus,search,treeScope,result?.diffs?.length,result?.same_logic_files?.length]);

  const selectedRaw=treeItems[selectedIndex]||null;
  const isLadder=/\.ld$/i.test(selectedRaw?.path||'');
  const supportsFlow=selectedRaw?.category==='logic'&&/\.(st|ab|src|ld)$/i.test(selectedRaw?.path||'');
  React.useEffect(()=>{
    setSourceView(isLadder?'diagram':selectedRaw?.status==='unchanged'&&selectedRaw?.source_view_available?'source':'difference');
  },[result?.sessionId,selectedRaw?.path]);
  const [screenDetail,setScreenDetail]=React.useState<{key:string;data?:any;error?:string}|null>(null);
  const needsLadderDetail=isLadder&&!(selectedRaw?.parsed_ladder?.controls||[]).some((control:any)=>control.base?.diagram||control.new?.diagram);
  const detailKey=`${result?.sessionId||''}/${needsLadderDetail?`ladder:${selectedRaw.path}`:selectedRaw?.screen_detail_id||selectedRaw?.project_detail_id||''}`;
  React.useEffect(()=>{
    if(!(selectedRaw?.screen_detail_id||selectedRaw?.project_detail_id||needsLadderDetail)||!result?.sessionId)return;
    const controller=new AbortController();
    setScreenDetail(null);
    const url=needsLadderDetail?`/api/local/compare/ladder/${result.sessionId}?path=${encodeURIComponent(selectedRaw.path)}`:`/api/local/compare/detail/${detailKey}`;
    fetch(url,{signal:controller.signal})
      .then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not load source details. Run comparison again if the cache was cleared.');return data})
      .then(data=>setScreenDetail({key:detailKey,data}))
      .catch(error=>{if(error.name!=='AbortError')setScreenDetail({key:detailKey,error:error.message})});
    return ()=>controller.abort();
  },[detailKey]);
  const loadedDetail=screenDetail?.key===detailKey?screenDetail.data:undefined;
  const selected=selectedRaw?{...selectedRaw,...(selectedRaw.project_detail_id?loadedDetail:{}),parsed_ladder:needsLadderDetail?loadedDetail:selectedRaw.parsed_ladder,parsed_screen:filterHmiDifferences(selectedRaw.parsed_screen||(selectedRaw.screen_detail_id?loadedDetail:undefined),skipHmiLayout)}:null;
  const selectedHunks=(selected?.hunks||[]).filter((h:any)=>workspaceStatus==='all'||(h.lines||[]).some((line:any)=>(line.status|| (line.t==='add'?'added':line.t==='del'?'removed':'unchanged'))===workspaceStatus));

  const selectLocal=(which:'base'|'new',path:string,name:string)=>{
    if(which==='base'){
      setCompareBasePath(path);setCompareFiles((p:any)=>({...p,base:[]}));setBaseBrowserOpen(false);
      userStorage.setItem('usopp_compare_base_path_v4.31',path);
      userStorage.setItem('usopp_compare_base_name_v4.31',name);
    }else{
      setCompareNewPath(path);setCompareFiles((p:any)=>({...p,new_:[]}));setNewBrowserOpen(false);
      userStorage.setItem('usopp_compare_new_path_v4.31',path);
      userStorage.setItem('usopp_compare_new_name_v4.31',name);
    }
  };

  const selectUpload=(which:'base'|'new',fs:File[])=>{
    fs=fs.filter(file=>!file.webkitRelativePath.replace(/\\/g,'/').split('/').slice(1,-1).some(part=>['temp','as','binaries','diagnosis','.git','__pycache__'].includes(part.toLowerCase())));
    if(which==='base'){setCompareBasePath('');setCompareFiles((p:any)=>({...p,base:fs}));}
    else{setCompareNewPath('');setCompareFiles((p:any)=>({...p,new_:fs}));}
  };

  const projectDetails=(info:any,hmi:string,setHmi:(value:string)=>void)=>{
    if(!info)return <div className="compareProjectMeta pending">Project details appear after a folder is selected.</div>;
    return <div className="compareProjectMeta">
      <div><span>Automation Studio</span><b>{info.automation_studio_version||'Not detected'}</b></div>
      <div><span>Active configuration</span><b>{info.active_configuration||'Not detected'}</b></div>
      <div><span>PLC type</span><b>{info.plc_type||'Not detected'}</b></div>
      <label><span>Screen folder</span><select value={hmi} onChange={event=>setHmi(event.target.value)} disabled={busy||!(info.screen_folders||[]).length}>
        {!(info.screen_folders||[]).length&&<option value="">No visualization folder detected</option>}
        {(info.screen_folders||[]).map((folder:string)=><option value={folder} key={folder}>{folder}</option>)}
      </select></label>
    </div>;
  };

  return <div className="compareDarkWorkspace">
    <ChopperSummary open={chopperSummaryOpen} result={result} onClose={()=>setChopperSummaryOpen(false)}/>
    <ProcessingTimePopup active={busy} label="Project comparison" progress={Number(progress?.percent||0)} defaultEstimate={45}/>
    <LocalFolderTree open={baseBrowserOpen} onClose={()=>setBaseBrowserOpen(false)} onSelect={(path,name)=>selectLocal('base',path,name)}/>
    <LocalFolderTree open={newBrowserOpen} onClose={()=>setNewBrowserOpen(false)} onSelect={(path,name)=>selectLocal('new',path,name)}/>

    <div className="compareDarkTop">
      <div>
        <div className="compareDarkEyebrow">PROJECT COMPARISON</div>
        <h1>MatchView</h1>
        <div className="compareDarkSubtitle">Base project vs Developed project | PLC logic, HMI screens, configuration and physical hardware</div>
        {result?.testId&&<small>Test ID: {result.testId}</small>}
      </div>
      <div className="compareHeadingAside">{projectLink}<div className="compareDarkActions">
        {result?.sessionId&&<button className="compareDarkBtn primary" onClick={()=>setChopperSummaryOpen(true)}>Chopper summary</button>}
        <CompareReports sessionId={result?.sessionId} projectName={newProjectInfo?.project_name||compareFiles.new_?.[0]?.webkitRelativePath?.split('/')[0]||compareNewPath.split(/[\\/]/).filter(Boolean).at(-1)||result?.newName||'Comparison'} busy={busy} skipLayout={skipHmiLayout}/>
        {progress&&<button className="compareDarkBtn primary" onClick={()=>setConsoleOpen(true)}>Console</button>}
      </div></div>
    </div>

    <div className="compareDarkInputs">
      <div className="compareDarkProject base">
        <div className="compareDarkProjectTitle"><span className="darkBadge base">BASE PROJECT</span><span>Original / Reference</span></div>
        <div className="compareDarkPath">{compareBasePath||compareFiles.base[0]?.webkitRelativePath?.split('/')[0]||'No project selected'}</div>
        {projectDetails(baseProjectInfo,baseHmi,setBaseHmi)}
        <div className="compareDarkInputActions">
          <button className="compareDarkBtn primary" disabled={busy} onClick={()=>setBaseBrowserOpen(true)}><FolderTree size={13}/> Browse This PC</button>
          <button className="compareDarkBtn" disabled={busy} onClick={()=>baseRef.current?.click()}><Upload size={13}/> Upload Project</button>
        </div>
        <input ref={baseRef} className="inputFile" type="file" multiple {...({webkitdirectory:'',directory:''} as any)} onChange={e=>selectUpload('base',Array.from(e.target.files||[]))}/>
      </div>
      <div className="compareDarkVs">VS</div>
      <div className="compareDarkProject developed">
        <div className="compareDarkProjectTitle"><span className="darkBadge new_">DEVELOPED PROJECT</span><span>Modified / New</span></div>
        <div className="compareDarkPath">{compareNewPath||compareFiles.new_[0]?.webkitRelativePath?.split('/')[0]||'No project selected'}</div>
        {projectDetails(newProjectInfo,newHmi,setNewHmi)}
        <div className="compareDarkInputActions">
          <button className="compareDarkBtn primary" disabled={busy} onClick={()=>setNewBrowserOpen(true)}><FolderTree size={13}/> Browse This PC</button>
          <button className="compareDarkBtn" disabled={busy} onClick={()=>newRef.current?.click()}><Upload size={13}/> Upload Project</button>
        </div>
        <input ref={newRef} className="inputFile" type="file" multiple {...({webkitdirectory:'',directory:''} as any)} onChange={e=>selectUpload('new',Array.from(e.target.files||[]))}/>
      </div>
      <button className="compareRunBtn" disabled={busy||(!compareBasePath&&!compareFiles.base.length)||(!compareNewPath&&!compareFiles.new_.length)} onClick={runCompare}>
        {busy?<RefreshCw className="spin" size={14}/>:<GitCompareArrows size={14}/>} {busy?'Comparing...':'Run Comparison'}
      </button>
    </div>

    {progress&&<div className="compareDarkProgress">
      <div className="compareDarkProgressHead"><span>{progress.phase==='complete'?'Comparison complete':progress.phase==='error'?'Comparison failed':'Comparing projects...'}</span><b>{Number(progress.percent||0).toFixed(1)}%</b></div>
      <div className="compareDarkProgressTrack"><div style={{width:`${Math.max(0,Math.min(100,Number(progress.percent||0)))}%`}}/></div>
      <div className="compareDarkCurrent"><span>BASE: {progress.baseFile||progress.currentBase||'Waiting for file'}</span><span>DEVELOPED: {progress.newFile||progress.currentNew||'Waiting for file'}</span></div>
    </div>}

    {result&&<div className="compareDarkSummary">
      <div><b>{summary.modified||0}</b><span>MODIFIED</span></div>
      <div><b className="green">{summary.added||0}</b><span>ADDED</span></div>
      <div><b className="red">{summary.removed||0}</b><span>REMOVED</span></div>
      <div><b>{summary.unchanged||0}</b><span>UNCHANGED</span></div>
      <div><b className="blue">{summary.by_category?.logic||0}</b><span>LOGIC CHANGES</span></div>
      <div><b className="cyan">{summary.by_category?.screen||0}</b><span>SCREEN CHANGES</span></div>
      <div><b className="amber">{summary.by_category?.hardware||0}</b><span>HARDWARE CHANGES</span></div>
    </div>}

    {result&&<div className="compareDarkTabs compareViewTabs">
      <button className={activeTab==='changes'&&filter==='logic'?'active':''} onClick={()=>{setActiveTab('changes');setFilter('logic')}}>Logical View</button>
      <button className={activeTab==='changes'&&filter==='screen'?'active':''} onClick={()=>{setActiveTab('changes');setFilter('screen')}}>Screen View</button>
      <button className={activeTab==='summary'?'active':''} onClick={()=>setActiveTab('summary')}>Project View</button>
      <button className={activeTab==='changes'&&filter==='hardware'?'active':''} onClick={()=>{setActiveTab('changes');setFilter('hardware')}}>HW View</button>
      <button className={activeTab==='changes'&&filter==='config'?'active':''} onClick={()=>{setActiveTab('changes');setFilter('config')}}>Config View</button>
      <button className={activeTab==='knowledge'?'active':''} onClick={()=>setActiveTab('knowledge')}>Knowledge based</button>
    </div>}

    {result&&<div style={{display:activeTab==='summary'?undefined:'none'}}><ProjectObjectComparison key={result.sessionId||result.testId||baseLabel+'|'+newLabel} result={result} onOpen={openProjectObject}/></div>}

    {result&&activeTab==='changes'&&<><div className="compareSizeToolbar"><label>Workspace height <select value={workspacePages} onChange={e=>{setWorkspacePages(Number(e.target.value));setWorkspaceHeight(null);}}><option value={1}>1 screen</option><option value={2}>2 screens</option><option value={3}>3 screens</option></select></label><label>Tree width <input aria-label="Project tree width" type="range" min="200" max="650" step="10" value={treeWidth} onChange={event=>resizeTree(Number(event.target.value))}/><output>{treeWidth}px</output></label><span>Drag the tree divider to adjust width; use the resize bar below the workspace to adjust height.</span></div><div className="compareDarkWorkspaceBody compareAdjustableTree" style={{height:workspaceHeight??`min(4000px, ${workspacePages*85}vh)`,gridTemplateColumns:`${treeWidth}px 7px minmax(0,1fr)`}}>
      <aside className="compareDarkFilePane">
        <div className="compareDarkSearch"><Search size={13}/><input aria-label="Search comparison project" placeholder="Search project files and folders" value={search} onChange={e=>setSearch(e.target.value)}/></div>
        <label className="compareStatusSelect compareTreeScope"><span>Tree</span><select value={treeScope} onChange={event=>{setTreeScope(event.target.value as typeof treeScope);setSelectedIndex(0)}}><option value="all">All projects</option><option value="base">Base project</option><option value="developed">Developed project</option></select></label>
        <label className="compareStatusSelect"><span>Tree filter</span><select aria-label="Tree file status" value={fileStatus} onChange={e=>setFileStatus(e.target.value as typeof fileStatus)}><option value="all">All files</option><option value="differences">Differences (added, modified, removed)</option><option value="modified">Modified only</option><option value="removed">Removed</option><option value="added">Added</option><option value="unchanged">Unchanged</option></select></label>
        <div className="compareDarkFilterRow">{cats.map(c=><button key={c} className={filter===c?'active':''} onClick={()=>setFilter(c)}>{c==='all'?'All':c==='logic'?'Logic':c==='screen'?'HMI':c==='hardware'?'HW':'Config'}</button>)}</div>
        <div className="compareTreeLegend"><span><i className="treeStatusIcon added">+</i>Added</span><span><i className="treeStatusIcon modified">{String.fromCharCode(8594)}</i>Modified</span><span><i className="treeStatusIcon removed">-</i>Removed</span><span><i className="treeStatusIcon unchanged">=</i>Same</span></div>
        <div className="compareDarkFileCount">{treeItems.length} file(s) | {treeScope==='all'?'combined':treeScope} tree</div>
        <div className="compareDarkFiles compareTreeFiles">
          <CompareTree items={treeItems} selectedIndex={selectedIndex} onSelect={setSelectedIndex} baseLabel={baseLabel} newLabel={newLabel} searching={!!search.trim()}/>
        </div>
      </aside>
      <TreeWidthHandle width={treeWidth} onChange={resizeTree}/>
      <section className="compareDarkDetail">
        {filter==='hardware'?<HardwareCompareView base={knowledge.base||{}} new_={knowledge.developed||{}} baseLabel={baseLabel} newLabel={newLabel}/>:!selected?<div className="compareDarkEmpty">Select a file to view the Base and Developed comparison.</div>:<>
          <div className="compareDarkDetailHead">
            <div><div className="compareDarkDetailTitle">{selected.file_name||String(selected.path).split('/').pop()} <span className={`detailStatus ${selected.status}`}>{String(selected.status).toUpperCase()}</span></div><div className="compareDarkDetailPath">{selected.path}</div></div>
            <div className="compareDarkDetailActions">{isLadder&&<button className={sourceView==='diagram'?'selected':''} onClick={()=>setSourceView('diagram')}>Ladder diagram</button>}{selected.category!=='screen'&&selected.source_view_available&&<><button className={sourceView==='difference'?'selected':''} onClick={()=>{setSourceView('difference');setWorkspaceStatus('all');}} title="Added, modified and removed changes with five surrounding lines">Differences</button><button className={sourceView==='source'?'selected':''} onClick={()=>{setSourceView('source');setWorkspaceStatus('all');}}>Show all source</button></>}{selected.category==='screen'&&<><button className={hmiView==='structured'?'selected':''} onClick={()=>setHmiView('structured')}>Structured HMI</button>{(selected.parsed_screen?.layouts?.base?.layers||selected.parsed_screen?.layouts?.new?.layers)&&<button className={hmiView==='preview'?'selected':''} title="View HMI screen layout" onClick={()=>setHmiView('preview')}><Monitor size={15}/> Screen preview</button>}</>}{selected.category!=='screen'&&!selected.parsed_hardware&&(sourceView==='difference'||sourceView==='source')&&<><span className="detailActionDivider"/><span className="compareWorkspaceFilterLabel">Workspace filter</span>{(['all','modified','removed','added'] as const).map(status=><button key={status} aria-pressed={workspaceStatus===status} className={workspaceStatus===status?'selected':''} onClick={()=>setWorkspaceStatus(status)}>{status==='all'?'All changes':status[0].toUpperCase()+status.slice(1)}</button>)}</>}</div>
          </div>
          <div className="compareDarkProjectHeaders"><div className="base"><span>BASE / REFERENCE</span><b>{baseLabel}</b><small>AS {projectInfo.base?.automation_studio_version||'Not detected'} | {projectInfo.base?.active_configuration||'No active configuration'} | PLC {projectInfo.base?.plc_type||'Not detected'} | Screen {projectInfo.base?.active_hmi||'Not detected'}</small></div><div className="developed"><span>DEVELOPED / COMPARE</span><b>{newLabel}</b><small>AS {projectInfo.developed?.automation_studio_version||'Not detected'} | {projectInfo.developed?.active_configuration||'No active configuration'} | PLC {projectInfo.developed?.plc_type||'Not detected'} | Screen {projectInfo.developed?.active_hmi||'Not detected'}</small></div></div>
          {selected.category==='screen'&&<label className="hmiSkipLayout"><input type="checkbox" checked={skipHmiLayout} onChange={event=>setSkipHmiLayout(event.target.checked)}/> Skip layout properties in screen differences <small>Width, Top, Left, AlignmentVertical, AlignmentHorizontal, and screen Index</small></label>}
          {selected.category==='logic'&&<div className="compareDarkSubroutine">Subroutine / Task: <b>{selected.subroutine||'Not available'}</b></div>}
          {supportsFlow&&<div className="compareDarkDetailActions" style={{padding:'8px 14px'}}><button className={sourceView==='flow'?'selected':''} onClick={()=>setSourceView('flow')}>Function flow</button><small>Step-by-step working sequence with source or ladder alongside</small></div>}
          {supportsFlow&&sourceView==='flow'&&<FunctionFlow key={`${result.sessionId}/${selected.path}`} sessionId={result.sessionId} path={selected.path} baseLabel={baseLabel} newLabel={newLabel}/>}
          {selected.project_detail_id&&!loadedDetail&&<div className="compareDarkEmpty">{screenDetail?.key===detailKey&&screenDetail.error?screenDetail.error:'Loading file source…'}</div>}
          {selected.screen_detail_id&&!selected.parsed_screen&&<div className="compareDarkEmpty">{screenDetail?.key===detailKey&&screenDetail.error?screenDetail.error:'Loading HMI details...'}</div>}
          {selected.parsed_screen&&(hmiView==='preview'&&(selected.parsed_screen.layouts?.base?.layers||selected.parsed_screen.layouts?.new?.layers)?<HmiScreenPreview key={selected.path} data={selected.parsed_screen} baseLabel={baseLabel} newLabel={newLabel} skipLayout={skipHmiLayout}/>:<ParsedScreenView key={selected.path} data={selected.parsed_screen} baseLabel={baseLabel} newLabel={newLabel} skipLayout={skipHmiLayout}/>)}
          {selected.parsed_hardware&&<ParsedHardwareView data={selected.parsed_hardware}/>}
          {isLadder&&sourceView==='diagram'&&!selected.parsed_ladder&&<div className="compareDarkEmpty" role="status">{screenDetail?.key===detailKey&&screenDetail.error?screenDetail.error:'Reading ladder networks...'}</div>}
          {selected.parsed_ladder&&sourceView==='diagram'&&<ParsedLadderView key={selected.path} data={selected.parsed_ladder} baseLabel={baseLabel} newLabel={newLabel} testId={result.testId}/>}
          {sourceView==='difference'&&!selected.source_rows?.length&&(selected.logic_added?.length>0||selected.logic_removed?.length>0)?<details className="compareDarkLogicSummary"><summary>PLC logic summary</summary>
            <div className="logicSummaryTitle">PLC LOGIC SUMMARY</div>
            <div className="logicSummaryCols">{(['new','base'] as const).map(side=><div key={side}><b className={side==='new'?'green':'red'}>{side==='new'?'Developed ? added / modified':'Base ? removed / modified'} ({logicSummaryLines(selected,side).length})</b>{logicSummaryLines(selected,side).map((row:any,i:number)=><pre key={i}><span className="summaryLineNumber">{row.line?`L${row.line}`:'?'}</span>{row.text}</pre>)}</div>)}</div>
          </details>:null}
          {selected.category!=='screen'&&(sourceView==='source'||sourceView==='difference'&&selected.source_rows?.length)?<CompareView entry={selected} baseLabel={baseLabel} newLabel={newLabel} mode={sourceView==='difference'?'difference':'source'} status={workspaceStatus}/>:selected.category!=='screen'&&sourceView==='difference'&&<div className="compareDarkDiff">
            {(selectedHunks.length?selectedHunks:[]).map((h:any,i:number)=><SplitDiffHunk key={i} hunk={h} baseLabel={baseLabel} newLabel={newLabel}/>)}
            {!selectedHunks.length&&<div className="compareDarkEmpty">No line-level detail is available for this file. The file status is <b>{selected.status}</b>.</div>}
            {selected.hunks?.length>selectedHunks.length&&<div className="compareDarkMore">Showing {selectedHunks.length} of {selected.hunks.length} diff sections. Select Full File Split to inspect more context.</div>}
          </div>}
        </>}
      </section>
    </div><ResizeHandle height={workspaceHeight??Math.min(4000,Math.round(window.innerHeight*.85*workspacePages))} onChange={setWorkspaceHeight} minHeight={window.innerWidth<=760?500:360} maxHeight={4000} label="comparison workspace"/></>}

    {result&&activeTab==='knowledge'&&<div className="compareDarkKnowledge"><div className="linkedKnowledgePane" ref={knowledgeScroll.refs[0]} onScroll={knowledgeScroll.onScroll(0)}><KbPanel kb={knowledge.base||{}} label={`BASE / ${baseLabel}`} expanded={expandedKnowledge} onExpand={expandKnowledge}/></div><div className="linkedKnowledgePane" ref={knowledgeScroll.refs[1]} onScroll={knowledgeScroll.onScroll(1)}><KbPanel kb={knowledge.developed||{}} label={`DEVELOPED / ${newLabel}`} expanded={expandedKnowledge} onExpand={expandKnowledge}/></div></div>}

    {consoleOpen&&<div className="compareConsoleOverlay" onClick={()=>setConsoleOpen(false)}><div className="compareConsole compareConsoleDark" onClick={e=>e.stopPropagation()}>
      <div className="compareConsoleHead"><div><b>Compare Console</b><span>{baseLabel} to {newLabel}</span></div><button className="iconBtn" onClick={()=>setConsoleOpen(false)}><X size={16}/></button></div>
      <div className="consoleProjects"><div><b>BASE PROJECT</b><span>{compareBasePath||compareFiles.base[0]?.webkitRelativePath?.split('/')[0]||baseLabel}</span></div><div><b>DEVELOPED PROJECT</b><span>{compareNewPath||compareFiles.new_[0]?.webkitRelativePath?.split('/')[0]||newLabel}</span></div></div>
      <div className="consoleLog">{(progress?.logs||[]).map((line:string,i:number)=><div key={i}>{line}</div>)}{busy&&<div className="consoleCursor">|</div>}</div>
      <div className="compareConsoleFoot"><span>{progress?.phase||'idle'}</span><span>{Number(progress?.percent||0).toFixed(1)}%</span></div>
    </div></div>}
  </div>;
}


