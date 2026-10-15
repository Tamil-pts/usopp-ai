export const SKIPPED_HMI_PROPERTIES = ['Width','Top','Left','AlignmentVertical','AlignmentHorizontal'] as const;
const ignored = new Set(SKIPPED_HMI_PROPERTIES.map(name=>name.toLowerCase()));
export const skipHmiProperty=(name:string)=>ignored.has(String(name).toLowerCase());
export const skipHmiPageIndex=(name:string)=>String(name).toLowerCase()==='index';

/** Filter comparison records, while preserving actual screen geometry. */
export function filterHmiDifferences(data:any, enabled:boolean):any {
  if(!enabled||!data)return data;
  const filterChanges=(changes:any[],page=false)=>changes.filter(change=>!skipHmiProperty(change.prop)&&!(page&&skipHmiPageIndex(change.prop)));
  const controls=(data.controls||[]).map((control:any)=>{
    const page=String(control.name||'').toLowerCase()==='screen properties';
    const changes=filterChanges(control.changes||[],page);
    const status=control.status==='modified'&&control.changes?.length&&!changes.length?'unchanged':control.status;
    const next={...control,changes,status};
    if(page)for(const side of ['base','new'])if(next[side]?.properties)next[side]={...next[side],properties:Object.fromEntries(Object.entries(next[side].properties).filter(([key])=>!skipHmiPageIndex(key)))};
    return next;
  });
  const statuses=new Map(controls.map((control:any)=>[control.name,control.status]));
  const changes=(data.changes||[]).map((change:any)=>change.changes?{...change,changes:filterChanges(change.changes,String(change.name||'').toLowerCase()==='screen properties')}:change)
    .filter((change:any)=>!skipHmiProperty(change.prop)&&!(change.type==='control_modified'&&!change.changes?.length));
  const layouts=data.layouts?Object.fromEntries(Object.entries(data.layouts).map(([side,value])=>{
    const layout=value as any;
    return [side,layout?.layers?{...layout,layers:layout.layers.map((layer:any)=>({...layer,
      controls:(layer.controls||[]).map((control:any)=>({...control,status:statuses.get(control.id)||statuses.get(control.name)||control.status}))}))}:layout];
  })):data.layouts;
  const pageProperties=(values:any)=>Object.fromEntries(Object.entries(values||{}).filter(([key])=>!skipHmiPageIndex(key)));
  return {...data,controls,changes,layouts,base_page_properties:pageProperties(data.base_page_properties),new_page_properties:pageProperties(data.new_page_properties)};
}
