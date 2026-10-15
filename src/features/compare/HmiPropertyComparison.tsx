import {Fragment,useEffect,useState,type ReactNode} from 'react';
import {groupHmiProperties,type HmiPropertyGroup,type HmiPropertyRow} from './hmiPropertyGroups';
import {skipHmiPageIndex,skipHmiProperty} from './hmiDifferenceFilter';
import './hmi-property-comparison.css';

function valueText(value:unknown) {
 if(value===undefined||value===null)return 'Not set';
 return typeof value==='object'?JSON.stringify(value):String(value);
}

/** One paired table keeps category expansion and property rows aligned. */
export function HmiPropertyComparison({base,developed,baseLabel,newLabel,contextKey,skipLayout=false,skipPageIndex=false,baseMissing=false,newMissing=false}:{
 base:Record<string,unknown>;developed:Record<string,unknown>;baseLabel:string;newLabel:string;contextKey:string;
 skipLayout?:boolean;skipPageIndex?:boolean;baseMissing?:boolean;newMissing?:boolean;
}) {
 const groups=groupHmiProperties(base,developed,key=>skipLayout&&(skipHmiProperty(key)||(skipPageIndex&&skipHmiPageIndex(key))));
 const [overrides,setOverrides]=useState<Record<string,boolean>>({});
 useEffect(()=>setOverrides({}),[contextKey]);
 const expanded=(group:HmiPropertyGroup)=>overrides[group.id]??(group.id==='Identity'||group.changed>0);
 const toggle=(group:HmiPropertyGroup)=>setOverrides(old=>({...old,[group.id]:!expanded(group)}));
 const allGroups=groups.flatMap(group=>[group,...group.children]);
 const expandAll=(open:boolean)=>setOverrides(Object.fromEntries(allGroups.map(group=>[group.id,open])));
 const row=(property:HmiPropertyRow,depth:number)=><tr key={property.key} className={'hmiCategoryProperty '+(property.changed?'changed':'')} data-property={property.key}>
  <th scope="row" title={property.key} style={{paddingLeft:14+depth*18}}>{property.label}</th><td>{valueText(property.base)}</td>
  <th scope="row" title={property.key} style={{paddingLeft:14+depth*18}}>{property.label}</th><td>{valueText(property.developed)}</td>
 </tr>;
 const category=(group:HmiPropertyGroup,depth=0):ReactNode=><Fragment key={group.id}>
  <tr className={'hmiCategoryHeading '+(depth?'nested':'')} data-category={group.id}>
   {[baseLabel,newLabel].map((label,side)=><th colSpan={2} key={side}>
    <button type="button" aria-label={`${group.label} properties (${label})`} aria-expanded={expanded(group)} onClick={()=>toggle(group)} style={{paddingLeft:10+depth*18}}>
     <span className="hmiCategoryToggle" aria-hidden="true">{expanded(group)?'−':'+'}</span><b>{group.label}</b>
     <span className="hmiCategoryCount">{group.count} {group.count===1?'property':'properties'}</span>
     {group.changed>0&&<span className="hmiCategoryChanges">{group.changed} changed</span>}
    </button>
   </th>)}
  </tr>
  {expanded(group)&&<>
   {group.id==='Format'&&group.children.map(child=>category(child,depth+1))}
   {group.rows.map(property=>row(property,depth+1))}
   {group.id!=='Format'&&group.children.map(child=>category(child,depth+1))}
  </>}
 </Fragment>;
 return <div className="hmiGroupedProperties">
  <div className="hmiCategoryTools"><span>Changed sections open automatically. Expand or collapse either side.</span><button type="button" onClick={()=>expandAll(true)}>Expand all</button><button type="button" onClick={()=>expandAll(false)}>Collapse all</button></div>
  <div className="hmiGroupedPropertyScroll" tabIndex={0} aria-label="Base and Developed categorized properties scroll area">
   <table className="hmiGroupedPropertyTable"><colgroup><col style={{width:'19%'}}/><col style={{width:'31%'}}/><col style={{width:'19%'}}/><col style={{width:'31%'}}/></colgroup>
    <thead><tr><th colSpan={2}><span>BASE / REFERENCE</span>{baseLabel}{baseMissing&&<small>Control not present</small>}</th><th colSpan={2}><span>DEVELOPED / COMPARE</span>{newLabel}{newMissing&&<small>Control not present</small>}</th></tr><tr><th>Property</th><th>Value</th><th>Property</th><th>Value</th></tr></thead>
    <tbody>{groups.map(group=>category(group))}{!groups.length&&<tr><td colSpan={4}>No properties available for this selection.</td></tr>}</tbody>
   </table>
  </div>
 </div>;
}
