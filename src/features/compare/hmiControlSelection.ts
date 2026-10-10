export type SelectableControl = {id:string;name:string;class:string;status:string;left:number;top:number;width:number;height:number};
export type SelectableLayer<C extends SelectableControl=SelectableControl> = {id:string;name:string;left:number;top:number;hidden:boolean;controls:C[]};

export function visiblePreviewLayers<L extends SelectableLayer>(layers:L[],filter:string):L[] {
  return layers.filter(layer=>filter==='all'||filter==='visible'&&!layer.hidden||layer.id===filter);
}

/** Work in source screen coordinates, including each layer's translation.
 * Reverse paint order so the directly clicked object appears first. */
export function controlsAtPoint<C extends SelectableControl>(layers:SelectableLayer<C>[],filter:string,x:number,y:number) {
  return visiblePreviewLayers(layers,filter).flatMap(layer=>layer.controls
    .filter(control=>control.width>0&&control.height>0&&x>=layer.left+control.left&&x<layer.left+control.left+control.width&&y>=layer.top+control.top&&y<layer.top+control.top+control.height)
    .map(control=>({control,layer}))).reverse();
}

/** Keep unchanged and covered controls; use IDs to pair each project's object. */
export function controlSelectionGroups<C extends SelectableControl>(layouts:({layers:SelectableLayer<C>[]} | undefined)[]) {
  const groups=new Map<string,{id:string;name:string;hidden:boolean;controls:{control:C;present:boolean[]}[]}>();
  layouts.forEach((layout,side)=>layout?.layers.forEach(layer=>{
    let group=groups.get(layer.id);
    if(!group){group={id:layer.id,name:layer.name,hidden:layer.hidden,controls:[]};groups.set(layer.id,group)}
    group.hidden=group.hidden&&layer.hidden;
    layer.controls.forEach(control=>{
      let item=group!.controls.find(item=>item.control.id===control.id);
      if(!item){item={control,present:layouts.map(()=>false)};group!.controls.push(item)}
      item.present[side]=true;
    });
  }));
  return [...groups.values()];
}
