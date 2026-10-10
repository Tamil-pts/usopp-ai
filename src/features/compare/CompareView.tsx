import React from 'react';

type Props={entry:any;baseLabel:string;newLabel:string};
export function CompareView({entry,baseLabel,newLabel}:Props){
 const panes=[React.useRef<HTMLDivElement>(null),React.useRef<HTMLDivElement>(null)];
 const common=React.useRef<HTMLDivElement>(null),horizontal=React.useRef<HTMLDivElement>(null);
 const [scrollWidth,setScrollWidth]=React.useState(0);
 const sources=[String(entry?.base_source||''),String(entry?.new_source||'')];
 const rows=entry?.source_rows?.length?entry.source_rows:Array.from({length:Math.max(...sources.map(s=>s.split(/\r?\n/).length))},(_,i)=>({base:sources[0].split(/\r?\n/)[i],new:sources[1].split(/\r?\n/)[i],base_line:i<sources[0].split(/\r?\n/).length?i+1:null,new_line:i<sources[1].split(/\r?\n/).length?i+1:null,status:'unchanged'}));
 React.useLayoutEffect(()=>{
  const measure=()=>setScrollWidth(Math.max(...panes.map(p=>p.current?Math.max(0,p.current.scrollWidth-p.current.clientWidth):0))+(horizontal.current?.clientWidth||0));
  const observer=new ResizeObserver(measure);panes.forEach(p=>{if(p.current){observer.observe(p.current);if(p.current.firstElementChild)observer.observe(p.current.firstElementChild)}});if(horizontal.current)observer.observe(horizontal.current);measure();
  if(common.current)common.current.scrollTop=0;if(horizontal.current)horizontal.current.scrollLeft=0;panes.forEach(p=>{if(p.current)p.current.scrollLeft=0});
  return ()=>observer.disconnect();
 },[entry]);
 return <div className="compareSourceView">
  <div className="compareSourceNotice">Shared scrolling: the right scrollbar moves both projects vertically. The bottom scrollbar moves both source panes horizontally.</div>
  <div className="compareSourceCommonScroll" ref={common} tabIndex={0} aria-label="Base and Developed source vertical scroll">
   <div className="compareSourceSplit">{sources.map((source,side)=><section className={`compareSourcePane ${side?'developed':'base'}`} key={side}>
    <header><span>{side?'DEVELOPED PROJECT':'BASE PROJECT'}</span><b>{side?newLabel:baseLabel}</b><small>{source?source.split(/\r?\n/).length:0} lines</small></header>
    <div className="compareSourceScroller" ref={panes[side]}><code>{rows.map((row:any,index:number)=>{const number=side?row.new_line:row.base_line;return <span className={`compareSourceLine ${row.status} ${number==null?'alignmentGap':''}`} key={index}><i>{number==null?'':`L${number}`}</i><em>{(side?row.new:row.base)||' '}</em></span>})}</code></div>
   </section>)}</div>
  </div>
  <div className="compareSharedHorizontal" ref={horizontal} tabIndex={0} aria-label="Scroll both source panes horizontally" onScroll={e=>panes.forEach(p=>{if(p.current)p.current.scrollLeft=e.currentTarget.scrollLeft})}><div style={{width:scrollWidth,height:1}}/></div>
 </div>;
}
