export const SKIPPED_HMI_PROPERTIES = ['Width','Top','Left','AlignmentVertical','AlignmentHorizontal'] as const;
const ignored = new Set(SKIPPED_HMI_PROPERTIES.map(name=>name.toLowerCase()));
export const skipHmiProperty=(name:string)=>ignored.has(String(name).toLowerCase());

/** Filter comparison records, while preserving actual screen geometry. */
export function filterHmiDifferences(data:any, enabled:boolean):any {
  if(!enabled||!data)return data;
  const filterChanges=(changes:any[])=>changes.filter(change=>!skipHmiProperty(change.prop));
  const controls=(data.controls||[]).map((control:any)=>{
    const changes=filterChanges(control.changes||[]);
    const status=control.status==='modified'&&control.changes?.length&&!changes.length?'unchanged':control.status;
    return {...control,changes,status};
  });
  const statuses=new Map(controls.map((control:any)=>[control.name,control.status]));
  const changes=(data.changes||[]).map((change:any)=>change.changes?{...change,changes:filterChanges(change.changes)}:change)
    .filter((change:any)=>!skipHmiProperty(change.prop)&&!(change.type==='control_modified'&&!change.changes?.length));
  const layouts=data.layouts?Object.fromEntries(Object.entries(data.layouts).map(([side,value])=>{
    const layout=value as any;
    return [side,layout?.layers?{...layout,layers:layout.layers.map((layer:any)=>({...layer,
      controls:(layer.controls||[]).map((control:any)=>({...control,status:statuses.get(control.id)||statuses.get(control.name)||control.status}))}))}:layout];
  })):data.layouts;
  return {...data,controls,changes,layouts};
}
